from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Avg
from django.core.exceptions import PermissionDenied
from datetime import datetime, timedelta, time
from .models import PersonalAppointment, ProviderSchedule, AppointmentReview
from .forms import PersonalAppointmentForm
from apps.accounts.models import User, ProviderProfile
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone as dj_timezone


@login_required
def provider_directory(request):
    """
    Browse available healthcare providers
    """
    providers = User.objects.filter(
        role='provider',
        is_active=True
    ).select_related('provider_profile')
    
    # Filter by specialization
    specialization = request.GET.get('specialization')
    if specialization:
        providers = providers.filter(provider_profile__specialization=specialization)
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        providers = providers.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(provider_profile__bio__icontains=search_query)
        )
    
    # Sort
    sort_by = request.GET.get('sort', 'rating')
    if sort_by == 'rating':
        providers = providers.order_by('-provider_profile__rating')
    elif sort_by == 'experience':
        providers = providers.order_by('-provider_profile__years_of_experience')
    elif sort_by == 'price_low':
        providers = providers.order_by('provider_profile__hourly_rate')
    elif sort_by == 'price_high':
        providers = providers.order_by('-provider_profile__hourly_rate')
    
    context = {
        'providers': providers,  # will be replaced with paginated list below
        'search_query': search_query,
        'sort_by': sort_by,
        'specializations': getattr(ProviderProfile, 'SPECIALIZATION_CHOICES', []),
    }
    # Paginate providers (12 per page)
    paginator = Paginator(providers, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context.update({
        'providers': page_obj.object_list,
        'page_obj': page_obj,
    })

    return render(request, 'appointments/provider_directory.html', context)


@login_required
def provider_detail(request, provider_id):
    """
    View provider profile and book personal appointment
    """
    provider = get_object_or_404(
        User.objects.select_related('provider_profile'),
        id=provider_id,
        role='provider',
        is_active=True
    )
    
    # Get provider reviews
    reviews = AppointmentReview.objects.filter(
        appointment__provider=provider,
        appointment__status='completed'
    ).select_related('appointment__patient').order_by('-created_at')[:10]
    
    # Get provider schedule
    schedules = ProviderSchedule.objects.filter(
        provider=provider,
        is_available=True
    ).order_by('day_of_week', 'start_time')
    
    # Calculate stats
    total_reviews = reviews.count()
    avg_rating = AppointmentReview.objects.filter(
        appointment__provider=provider
    ).aggregate(Avg('rating'))['rating__avg'] or 0
    
    completed_appointments = PersonalAppointment.objects.filter(
        provider=provider,
        status='completed'
    ).count()
    
    context = {
        'provider': provider,
        'reviews': reviews,
        'schedules': schedules,
        'total_reviews': total_reviews,
        'avg_rating': avg_rating,
        'completed_appointments': completed_appointments,
    }
    
    return render(request, 'appointments/provider_detail.html', context)


@login_required
def book_personal_appointment(request, provider_id):
    """
    Book a personal appointment with provider
    """
    if request.user.role != 'patient':
        messages.error(request, 'Only patients can book appointments.')
        return redirect('appointments:provider_directory')
    
    provider = get_object_or_404(
        User,
        id=provider_id,
        role='provider',
        is_active=True
    )
    
    if request.method == 'POST':
        form = PersonalAppointmentForm(request.POST, provider=provider)
        if form.is_valid():
            try:
                with transaction.atomic():
                    appointment = form.save(commit=False)
                    appointment.patient = request.user
                    appointment.provider = provider
                    appointment.save()

                    # Create payment record
                    from apps.payments.models import Payment
                    Payment.objects.create(
                        patient=request.user,
                        amount=appointment.total_fee,
                        payment_status='unpaid',
                        appointment=None,
                    )

                    messages.success(
                        request,
                        f'Appointment request sent to {provider.get_full_name()}. Reference: #{appointment.id}'
                    )
                    return redirect('appointments:personal_appointment_detail', appointment_id=appointment.id)

            except Exception as e:
                messages.error(request, f'Error booking appointment: {str(e)}')
        else:
            # Surface form errors to the user (helpful during local debugging)
            try:
                err_text = form.errors.as_text()
            except Exception:
                err_text = str(form.errors)
            messages.error(request, 'Please correct the errors below: ' + err_text)
            # Also print to console for developer visibility
            print('PersonalAppointmentForm invalid:', err_text)
    else:
        form = PersonalAppointmentForm(provider=provider)
    
    # Get available time slots
    today = timezone.now().date()
    # Build a list of available dates (next 30 days) where provider has schedule
    available_dates = []
    for i in range(30):  # Next 30 days
        date = today + timedelta(days=i)
        if ProviderSchedule.objects.filter(
            provider=provider,
            day_of_week=date.weekday(),
            is_available=True
        ).exists():
            available_dates.append(date)

    # Determine the next available date (first in the ordered list)
    next_available_date = available_dates[0] if available_dates else None

    # Try to determine provider timezone from profile, fall back to project/timezone
    provider_tz = None
    try:
        provider_tz = getattr(provider.provider_profile, 'timezone', None)
    except Exception:
        provider_tz = None
    if not provider_tz:
        # fallback to Django settings or active timezone
        provider_tz = getattr(settings, 'TIME_ZONE', dj_timezone.get_current_timezone_name())

    # Serialize available_dates to ISO strings for safe JSON usage in templates
    available_dates_str = [d.isoformat() for d in available_dates]
    # Build a mapping of date (ISO) -> available slot count so the frontend can decorate calendar days
    available_dates_info = {}
    for d in available_dates:
        appointment_date = d
        weekday = appointment_date.weekday()
        schedules = ProviderSchedule.objects.filter(
            provider=provider,
            day_of_week=weekday,
            is_available=True
        )
        slot_count = 0
        for schedule in schedules:
            current_time = schedule.start_time
            end_time = schedule.end_time
            # iterate slots for this schedule and count unbooked slots
            while current_time < end_time:
                is_booked = PersonalAppointment.objects.filter(
                    provider=provider,
                    appointment_date=appointment_date,
                    appointment_time=current_time,
                    status__in=['pending', 'confirmed']
                ).exists()
                if not is_booked:
                    slot_count += 1
                # increment by slot duration
                current_time = (
                    datetime.combine(appointment_date, current_time) + 
                    timedelta(minutes=schedule.slot_duration)
                ).time()
        available_dates_info[appointment_date.isoformat()] = slot_count
    
    context = {
        'provider': provider,
        'available_dates': available_dates,
        'form': form,
        'available_dates_str': available_dates_str,
        'available_dates_info': available_dates_info,
        'next_available_date': next_available_date,
        'provider_time_zone': provider_tz,
    }
    
    return render(request, 'appointments/book_personal_appointment.html', context)


@login_required
def get_available_slots(request, provider_id, date):
    """
    AJAX endpoint to get available time slots for a specific date
    """
    from django.http import JsonResponse
    
    provider = get_object_or_404(User, id=provider_id, role='provider')
    appointment_date = datetime.strptime(date, '%Y-%m-%d').date()
    weekday = appointment_date.weekday()
    
    # Get provider schedule for this day
    schedules = ProviderSchedule.objects.filter(
        provider=provider,
        day_of_week=weekday,
        is_available=True
    )
    
    slots = []
    for schedule in schedules:
        # Generate time slots
        current_time = schedule.start_time
        end_time = schedule.end_time
        
        while current_time < end_time:
            # Check if slot is already booked
            is_booked = PersonalAppointment.objects.filter(
                provider=provider,
                appointment_date=appointment_date,
                appointment_time=current_time,
                status__in=['pending', 'confirmed']
            ).exists()
            
            if not is_booked:
                slots.append({
                    'time': current_time.strftime('%H:%M'),
                    'display': current_time.strftime('%I:%M %p')
                })
            
            # Move to next slot
            current_time = (
                datetime.combine(appointment_date, current_time) + 
                timedelta(minutes=schedule.slot_duration)
            ).time()
    
    return JsonResponse({'slots': slots})


@login_required
def my_personal_appointments(request):
    """
    View all personal appointments (patient or provider view)
    """
    if request.user.role == 'patient':
        appointments = PersonalAppointment.objects.filter(
            patient=request.user
        ).select_related('provider', 'provider__provider_profile').order_by('-appointment_date')
    elif request.user.role == 'provider':
        appointments = PersonalAppointment.objects.filter(
            provider=request.user
        ).select_related('patient', 'patient__patient_profile').order_by('-appointment_date')
    else:
        messages.error(request, 'Invalid user role.')
        return redirect('dashboard:home')
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        appointments = appointments.filter(status=status_filter)
    
    # Determine whether each appointment can be reviewed by the current user.
    # We avoid calling reverse relations directly in templates to prevent
    # TemplateSyntaxError when the related object is missing.
    from django.core.exceptions import ObjectDoesNotExist
    for appt in appointments:
        try:
            _ = appt.review
            has_review = True
        except ObjectDoesNotExist:
            has_review = False

        appt.can_review = (appt.status == 'completed' and not has_review and request.user.role == 'patient')

    context = {
        'appointments': appointments,
        'status_filter': status_filter,
    }
    
    return render(request, 'appointments/my_personal_appointments.html', context)


@login_required
def personal_appointment_detail(request, appointment_id):
    """
    View personal appointment details
    """
    if request.user.role == 'patient':
        appointment = get_object_or_404(
            PersonalAppointment,
            id=appointment_id,
            patient=request.user
        )
    elif request.user.role == 'provider':
        appointment = get_object_or_404(
            PersonalAppointment,
            id=appointment_id,
            provider=request.user
        )
    else:
        raise PermissionDenied()
    
    context = {
        'appointment': appointment,
    }
    
    return render(request, 'appointments/personal_appointment_detail.html', context)


@login_required
def confirm_personal_appointment(request, appointment_id):
    """
    Provider confirms personal appointment
    """
    if request.user.role != 'provider':
        raise PermissionDenied()
    
    appointment = get_object_or_404(
        PersonalAppointment,
        id=appointment_id,
        provider=request.user,
        status='pending'
    )
    
    appointment.status = 'confirmed'
    appointment.confirmed_at = timezone.now()
    appointment.save()
    
    messages.success(request, 'Appointment confirmed!')
    return redirect('appointments:personal_appointment_detail', appointment_id=appointment.id)


@login_required
def complete_personal_appointment(request, appointment_id):
    """
    Provider marks appointment as completed and adds notes
    """
    if request.user.role != 'provider':
        raise PermissionDenied()
    
    appointment = get_object_or_404(
        PersonalAppointment,
        id=appointment_id,
        provider=request.user
    )
    
    if request.method == 'POST':
        appointment.status = 'completed'
        appointment.completed_at = timezone.now()
        appointment.provider_notes = request.POST.get('provider_notes', '')
        appointment.diagnosis = request.POST.get('diagnosis', '')
        appointment.prescription = request.POST.get('prescription', '')
        appointment.save()
        
        messages.success(request, 'Appointment completed successfully!')
        return redirect('appointments:personal_appointment_detail', appointment_id=appointment.id)
    
    context = {
        'appointment': appointment,
    }
    
    return render(request, 'appointments/complete_personal_appointment.html', context)


@login_required
def cancel_personal_appointment(request, appointment_id):
    """
    Cancel personal appointment
    """
    if request.user.role == 'patient':
        appointment = get_object_or_404(
            PersonalAppointment,
            id=appointment_id,
            patient=request.user
        )
        cancel_status = 'cancelled_by_patient'
    elif request.user.role == 'provider':
        appointment = get_object_or_404(
            PersonalAppointment,
            id=appointment_id,
            provider=request.user
        )
        cancel_status = 'cancelled_by_provider'
    else:
        raise PermissionDenied()
    
    if request.method == 'POST':
        appointment.status = cancel_status
        appointment.cancellation_reason = request.POST.get('cancellation_reason', '')
        appointment.cancelled_at = timezone.now()
        appointment.save()
        
        messages.success(request, 'Appointment cancelled.')
        return redirect('appointments:my_personal_appointments')
    
    context = {
        'appointment': appointment,
    }
    
    return render(request, 'appointments/cancel_personal_appointment.html', context)


@login_required
def add_appointment_review(request, appointment_id):
    """
    Patient adds review after completed appointment
    """
    if request.user.role != 'patient':
        raise PermissionDenied()
    
    appointment = get_object_or_404(
        PersonalAppointment,
        id=appointment_id,
        patient=request.user,
        status='completed'
    )
    
    if hasattr(appointment, 'review'):
        messages.info(request, 'You have already reviewed this appointment.')
        return redirect('appointments:personal_appointment_detail', appointment_id=appointment.id)
    
    if request.method == 'POST':
        AppointmentReview.objects.create(
            appointment=appointment,
            rating=int(request.POST.get('rating')),
            review_text=request.POST.get('review_text'),
            would_recommend=request.POST.get('would_recommend') == 'yes'
        )
        
        # Update provider rating
        provider = appointment.provider
        avg_rating = AppointmentReview.objects.filter(
            appointment__provider=provider
        ).aggregate(Avg('rating'))['rating__avg']
        
        provider.provider_profile.rating = avg_rating
        provider.provider_profile.total_reviews = AppointmentReview.objects.filter(
            appointment__provider=provider
        ).count()
        provider.provider_profile.save()
        
        messages.success(request, 'Thank you for your review!')
        return redirect('appointments:personal_appointment_detail', appointment_id=appointment.id)
    
    context = {
        'appointment': appointment,
    }
    
    return render(request, 'appointments/add_review.html', context)
