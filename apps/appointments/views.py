"""
UH Care - Complete Appointments System
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from datetime import datetime, timedelta

from .models import ServiceBooking
from django.db.models import Q
from apps.services.models import Service
from apps.payments.models import Payment
from .forms import AppointmentBookingForm


@login_required
def book_appointment(request, service_id):
    """
    Book a new appointment for a service
    """
    # Only patients can book appointments
    if request.user.role != 'patient':
        messages.error(request, 'Only patients can book appointments.')
        return redirect('services:list')
    
    service = get_object_or_404(Service, id=service_id, is_active=True)

    # If the user already has an active (pending/confirmed/in_progress) appointment
    # for this same service in the future, block creating another one from this
    # booking page and direct them to their appointments page or the existing
    # confirmation. This enforces that a booking is 'permanent' unless cancelled.
    existing_user_appt = ServiceBooking.objects.filter(
        patient=request.user,
        service=service,
        status__in=['pending', 'confirmed', 'in_progress']
    ).filter(appointment_date__gte=timezone.now().date()).first()

    if existing_user_appt:
        messages.info(
            request,
            f"You already have an active booking for this service (Ref #{existing_user_appt.id}). To make a new booking please use the booking page after this appointment is completed or cancelled."
        )
        return redirect('appointments:detail', appointment_id=existing_user_appt.id)
    
    if request.method == 'POST':
        form = AppointmentBookingForm(request.POST, service=service)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create appointment
                    appointment = form.save(commit=False)
                    appointment.patient = request.user
                    appointment.service = service
                    # If patient provided a requested price (validated by the form), honor it
                    requested_price = form.cleaned_data.get('requested_price')
                    if requested_price:
                        appointment.service_price = requested_price
                    else:
                        appointment.service_price = service.base_price
                    appointment.status = 'pending'
                    
                    # Calculate total
                    appointment.total_amount = (
                        appointment.service_price + 
                        appointment.additional_charges
                    )
                    
                    appointment.save()
                    
                    # Create payment record and link to ServiceBooking via service_booking FK.
                    Payment.objects.create(
                        service_booking=appointment,
                        patient=request.user,
                        amount=appointment.total_amount,
                        payment_status='unpaid'
                    )
                    
                    # Update patient balance
                    patient_profile = request.user.patient_profile
                    patient_profile.total_balance += appointment.total_amount
                    patient_profile.save()
                    
                    messages.success(
                        request,
                        f'Appointment booked successfully! Reference: #{appointment.id}'
                    )
                    return redirect('appointments:confirmation', appointment_id=appointment.id)
                    
            except Exception as e:
                messages.error(request, f'Error booking appointment: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Initialize form with default values
        initial_data = {
            'appointment_date': (timezone.now() + timedelta(days=1)).date(),
            'duration_hours': 1.0,
            'additional_charges': 0.00,
        }
        form = AppointmentBookingForm(initial=initial_data, service=service)
    
    context = {
        'form': form,
        'service': service,
    }
    
    return render(request, 'appointments/book_appointment.html', context)


@login_required
def appointment_confirmation(request, appointment_id):
    """
    Show appointment confirmation page
    """
    appointment = get_object_or_404(
        ServiceBooking.objects.select_related('service', 'patient'),
        id=appointment_id,
        patient=request.user
    )
    
    # Get payment info (appointment is a ServiceBooking, so only check service_booking FK)
    payment = Payment.objects.filter(service_booking=appointment).first()
    # Compute a simple boolean for template logic to avoid complex template
    # expressions (Django template 'if' has limited parsing for parentheses).
    payment_pending_or_unpaid = False
    if payment and payment.payment_status in ('unpaid', 'pending'):
        payment_pending_or_unpaid = True

    context = {
        'appointment': appointment,
        'payment': payment,
        'payment_pending_or_unpaid': payment_pending_or_unpaid,
    }
    
    return render(request, 'appointments/confirmation.html', context)


@login_required
def my_appointments(request):
    """
    View all user appointments (patient or provider)
    """
    if request.user.role == 'patient':
        appointments = ServiceBooking.objects.filter(
            patient=request.user
        ).select_related('service', 'provider').order_by('-appointment_date', '-appointment_time')
        
    elif request.user.role == 'provider':
        appointments = ServiceBooking.objects.filter(
            provider=request.user
        ).select_related('service', 'patient').order_by('-appointment_date', '-appointment_time')
        
    else:
        messages.error(request, 'Invalid user role.')
        return redirect('dashboard:home')
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        appointments = appointments.filter(status=status_filter)
    
    context = {
        'appointments': appointments,
        'status_filter': status_filter,
    }
    
    return render(request, 'appointments/my_appointments.html', context)


@login_required
def appointment_detail(request, appointment_id):
    """
    View detailed appointment information
    """
    # Get appointment based on user role
    if request.user.role == 'patient':
        appointment = get_object_or_404(
            ServiceBooking.objects.select_related('service', 'provider'),
            id=appointment_id,
            patient=request.user
        )
    elif request.user.role == 'provider':
        appointment = get_object_or_404(
            ServiceBooking.objects.select_related('service', 'patient'),
            pk=appointment_id,
            provider=request.user
        )
    else:
        raise PermissionDenied("You don't have permission to view this appointment.")
    
    # Get payment info (appointment is a ServiceBooking, so only check service_booking FK)
    payment = Payment.objects.filter(service_booking=appointment).first()
    
    context = {
        'appointment': appointment,
        'payment': payment,
    }
    
    return render(request, 'appointments/detail.html', context)


@login_required
def cancel_appointment(request, appointment_id):
    """
    Cancel an appointment (patient only)
    """
    if request.user.role != 'patient':
        raise PermissionDenied("Only patients can cancel appointments.")
    
    appointment = get_object_or_404(
        ServiceBooking,
        id=appointment_id,
        patient=request.user
    )
    
    # Only allow cancellation when status is 'pending'
    if appointment.status != 'pending':
        messages.error(request, 'This appointment cannot be cancelled.')
        return redirect('appointments:detail', appointment_id=appointment.id)
    
    # Check cancellation window (24 hours before)
    # Build an aware datetime for the appointment (compare against timezone.now())
    appointment_datetime = datetime.combine(
        appointment.appointment_date,
        appointment.appointment_time
    )
    # If the combined datetime is naive, make it timezone-aware using current timezone
    try:
        if appointment_datetime.tzinfo is None:
            appointment_datetime = timezone.make_aware(appointment_datetime, timezone.get_current_timezone())
    except Exception:
        # Fallback: if make_aware fails for any reason, assume naive and compare using naive now
        appointment_datetime = appointment_datetime

    now = timezone.now()
    # If now is aware and appointment_datetime is naive, make now naive for comparison
    if (now.tzinfo is not None) and (appointment_datetime.tzinfo is None):
        # convert now to naive in current timezone
        now = now.replace(tzinfo=None)

    hours_until_appointment = (appointment_datetime - now).total_seconds() / 3600
    
    if hours_until_appointment < 24:
        messages.warning(
            request,
            'Cancellation within 24 hours may incur charges. Please contact support.'
        )
    
    if request.method == 'POST':
        cancellation_reason = request.POST.get('cancellation_reason', '') or request.POST.get('reason', '')
        # Server-side validation: require a non-empty cancellation reason
        if not cancellation_reason or not cancellation_reason.strip():
            messages.error(request, 'Please provide a reason for cancellation.')
            return redirect('appointments:my_appointments')

        with transaction.atomic():
            appointment.status = 'cancelled'
            appointment.cancellation_reason = cancellation_reason
            appointment.save()

            # Update patient balance (remove charge if cancelled in time)
            if hours_until_appointment >= 24:
                patient_profile = request.user.patient_profile
                patient_profile.total_balance -= appointment.total_amount
                patient_profile.save()

                # Update payment status (appointment is a ServiceBooking, so only update service_booking FK)
                Payment.objects.filter(service_booking=appointment).update(
                    payment_status='refunded'
                )

        messages.success(request, 'Appointment cancelled successfully.')
        return redirect('appointments:my_appointments')
    
    context = {
        'appointment': appointment,
        'hours_until_appointment': hours_until_appointment,
    }
    
    return render(request, 'appointments/cancel.html', context)


# =====================================================
# PROVIDER VIEWS
# =====================================================

@login_required
def provider_pending_appointments(request):
    """
    View pending appointment requests for providers
    """
    if request.user.role != 'provider':
        raise PermissionDenied("Only providers can access this page.")
    
    # Get pending appointments (unassigned or assigned to this provider)
    pending_appointments = ServiceBooking.objects.filter(
        status='pending'
    ).filter(
        provider__isnull=True  # Unassigned
    ) | ServiceBooking.objects.filter(
        status='pending',
        provider=request.user  # Assigned to this provider
    )
    
    pending_appointments = pending_appointments.select_related(
        'service', 'patient'
    ).order_by('appointment_date', 'appointment_time')
    
    context = {
        'appointments': pending_appointments,
    }
    
    return render(request, 'appointments/provider_pending.html', context)


@login_required
def accept_appointment(request, appointment_id):
    """
    Provider accepts an appointment
    """
    if request.user.role != 'provider':
        raise PermissionDenied("Only providers can accept appointments.")
    
    appointment = get_object_or_404(
        ServiceBooking,
        id=appointment_id,
        status='pending'
    )
    
    # Check if provider is available
    # (Add availability check logic here if implemented)
    
    with transaction.atomic():
        appointment.provider = request.user
        appointment.status = 'confirmed'
        appointment.confirmed_at = timezone.now()
        appointment.save()
    
    messages.success(
        request,
        f'Appointment #{appointment.id} accepted successfully!'
    )
    return redirect('appointments:my_appointments')


@login_required
def reject_appointment(request, appointment_id):
    """
    Provider rejects an appointment
    """
    if request.user.role != 'provider':
        raise PermissionDenied("Only providers can reject appointments.")
    
    appointment = get_object_or_404(
        ServiceBooking,
        id=appointment_id,
        status='pending'
    )
    
    if request.method == 'POST':
        rejection_reason = request.POST.get('rejection_reason', 'Provider unavailable')
        
        with transaction.atomic():
            appointment.provider = None
            appointment.status = 'rejected'
            appointment.cancellation_reason = rejection_reason
            appointment.save()
        
        messages.success(request, 'Appointment rejected.')
        return redirect('appointments:provider_pending')
    
    context = {
        'appointment': appointment,
    }
    
    return render(request, 'appointments/reject.html', context)


@login_required
def complete_appointment(request, appointment_id):
    """
    Mark appointment as completed (provider only)
    """
    if request.user.role != 'provider':
        raise PermissionDenied("Only providers can complete appointments.")
    
    appointment = get_object_or_404(
        ServiceBooking,
        id=appointment_id,
        provider=request.user,
        status__in=['confirmed', 'in_progress']
    )
    
    if request.method == 'POST':
        provider_notes = request.POST.get('provider_notes', '')

        with transaction.atomic():
            appointment.status = 'completed'
            appointment.provider_notes = provider_notes
            appointment.completed_at = timezone.now()
            appointment.save()

            # Update service total bookings
            appointment.service.total_bookings += 1
            appointment.service.save()

        messages.success(request, 'Appointment marked as completed!')
        return redirect('appointments:my_appointments')
    
    context = {
        'appointment': appointment,
    }
    
    return render(request, 'appointments/complete.html', context)