"""
UH Care - Dashboard Views
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal

from apps.accounts.models import User, PatientProfile, ProviderProfile
from apps.appointments.models import ServiceBooking, PersonalAppointment
from apps.payments.models import Payment
from apps.services.models import Service
from apps.services.wishlist import Wishlist
from apps.equipment.models import EquipmentPurchase, EquipmentRental
from apps.pharmacy.models import PharmacyOrderActivity, PharmacyOrder


@login_required
def dashboard_home(request):
    """
    Main dashboard - routes to appropriate dashboard based on user role
    """
    if request.user.role == 'patient':
        return patient_dashboard(request)
    elif request.user.role == 'provider':
        return provider_dashboard(request)
    elif request.user.is_staff or request.user.is_superuser:
        return admin_dashboard(request)
    else:
        return redirect('accounts:home')


@login_required
def patient_dashboard(request):
    """
    Patient dashboard with overview of appointments, payments, and balance
    """
    user = request.user
    # Ensure a PatientProfile exists for the user. Some users (imported or created
    # indirectly) may have role='patient' but missing the related PatientProfile
    # record. Create a minimal profile if missing to avoid RelatedObjectDoesNotExist.
    try:
        profile = user.patient_profile
    except Exception:
        # Lazily create a PatientProfile with sensible defaults
        profile, _ = PatientProfile.objects.get_or_create(
            user=user,
            defaults={
                'medical_history': '',
                'blood_group': '',
                'total_balance': Decimal('0.00')
            }
        )
    
    # Get date ranges
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    
    # Upcoming marketplace service bookings
    upcoming_appointments = ServiceBooking.objects.filter(
        patient=user,
        appointment_date__gte=today,
        status__in=['pending', 'confirmed']
    ).select_related('service', 'provider').order_by('appointment_date', 'appointment_time')[:5]
    
    # Recent marketplace service bookings
    recent_appointments = ServiceBooking.objects.filter(
        patient=user
    ).select_related('service', 'provider').order_by('-appointment_date', '-appointment_time')[:5]
    
    # Marketplace booking statistics
    total_appointments = ServiceBooking.objects.filter(patient=user).count()
    completed_appointments = ServiceBooking.objects.filter(
        patient=user, 
        status='completed'
    ).count()
    pending_appointments = ServiceBooking.objects.filter(
        patient=user,
        status='pending'
    ).count()
    cancelled_appointments = ServiceBooking.objects.filter(
        patient=user,
        status='cancelled'
    ).count()
    
    # Payment statistics
    total_spent = Payment.objects.filter(
        patient=user,
        payment_status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    pending_payments = Payment.objects.filter(
        patient=user,
        payment_status='unpaid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    this_month_spent = Payment.objects.filter(
        patient=user,
        payment_status='paid',
        payment_date__gte=this_month_start
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Recent payments (include both legacy appointment and new service_booking links)
    recent_payments = Payment.objects.filter(
        patient=user
    ).select_related('appointment', 'service_booking').order_by('-created_at')[:5]

    # Recent equipment orders
    recent_purchases = EquipmentPurchase.objects.filter(customer=user).select_related('equipment').order_by('-created_at')[:5]
    recent_rentals = EquipmentRental.objects.filter(customer=user).select_related('equipment').order_by('-created_at')[:5]

    # Recent pharmacy order activities for this user (delivery timeline, status updates, etc.)
    recent_pharmacy_activities = PharmacyOrderActivity.objects.filter(
        order__customer=user
    ).select_related('order', 'actor').order_by('-created_at')[:6]

    # Recent pharmacy orders (show recent order summaries)
    recent_pharmacy_orders = PharmacyOrder.objects.filter(
        customer=user
    ).order_by('-created_at')[:5]

    # Personal appointments (direct patient-provider bookings)
    upcoming_personal = PersonalAppointment.objects.filter(
        patient=user,
        appointment_date__gte=today,
        status__in=['pending', 'confirmed']
    ).select_related('provider').order_by('appointment_date', 'appointment_time')[:5]

    recent_personal = PersonalAppointment.objects.filter(
        patient=user,
        appointment_date__lt=today
    ).select_related('provider').order_by('-appointment_date', '-appointment_time')[:5]
    
    # Wishlist count
    wishlist_count = Wishlist.objects.filter(user=user).count()
    
    # Quick stats
    stats = {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'pending_appointments': pending_appointments,
        'cancelled_appointments': cancelled_appointments,
        'total_spent': total_spent,
        'pending_payments': pending_payments,
        'this_month_spent': this_month_spent,
        # placeholder; we'll compute a dashboard-friendly balance below
        'current_balance': None,
        'wishlist_count': wishlist_count,
        'equipment_purchases_count': EquipmentPurchase.objects.filter(customer=user).count(),
        'equipment_rentals_count': EquipmentRental.objects.filter(customer=user).count(),
        'personal_appointments_count': PersonalAppointment.objects.filter(patient=user).count(),
        'prescriptions_count': PharmacyOrder.objects.filter(customer=user).count(),
        'outstanding_amount': Decimal('0.00'),
    }

    # Compute gross obligation from domain records (same approach as patient_balance)
    appointments_total = ServiceBooking.objects.filter(patient=user).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    personal_appointments_total = PersonalAppointment.objects.filter(patient=user).aggregate(total=Sum('total_fee'))['total'] or Decimal('0.00')
    pharmacy_total = PharmacyOrder.objects.filter(customer=user).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    equipment_purchases_total = EquipmentPurchase.objects.filter(customer=user).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    equipment_rentals_total = EquipmentRental.objects.filter(customer=user).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    gross_total = appointments_total + personal_appointments_total + pharmacy_total + equipment_purchases_total + equipment_rentals_total
    total_paid = Payment.objects.filter(patient=user, payment_status='paid').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    # Compute unpaid similarly to patient_balance view: exclude cash commitments
    # and online pending verification so the dashboard quick balance matches
    # the detailed balance page.
    # Cash commitments (cash & unpaid)
    cash_committed_qs = Payment.objects.filter(
        patient=user,
        payment_status='unpaid',
        payment_method='cash'
    )
    cash_committed = cash_committed_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Online pending verification (online & unpaid but with proof submitted)
    online_pending_qs = Payment.objects.filter(
        patient=user,
        payment_status='unpaid',
        payment_method='online'
    ).filter(
        Q(payment_proof_file__isnull=False) | ~Q(transaction_id='') | ~Q(payment_proof_url='')
    )
    online_pending = online_pending_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Total paid and gross_total already computed; compute total_unpaid as
    # unpaid payments excluding cash commitments and online_pending, also
    # excluding payments tied to cancelled domain objects for safety.
    total_unpaid_qs = Payment.objects.filter(
        patient=user,
        payment_status='unpaid'
    ).exclude(
        Q(payment_method='cash') & Q(payment_status='unpaid')
    ).exclude(
        Q(payment_method='online') & Q(payment_status='unpaid') & (
            Q(payment_proof_file__isnull=False) | ~Q(transaction_id='') | ~Q(payment_proof_url='')
        )
    ).exclude(
        Q(appointment__status='cancelled') | Q(service_booking__status='cancelled') |
        Q(pharmacy_order__status='cancelled') |
        Q(equipment_purchase__status='cancelled') |
        Q(equipment_rental__status='cancelled')
    )
    total_unpaid = total_unpaid_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Update stats to reflect aggregated view-level totals.
    # Use the same 'net_unpaid' value (gross_total - total_paid) that
    # `patient_balance` displays as the Unpaid Amount (Net Balance). This
    # ensures both pages show the same high-level unpaid amount.
    net_unpaid = gross_total - total_paid

    stats['gross_total'] = gross_total
    stats['paid_amount'] = total_paid
    stats['current_balance'] = net_unpaid
    stats['outstanding_amount'] = net_unpaid
    # keep a separate actionable unpaid amount (excludes cash commitments and
    # online-pending) for the 'pending' label — this is still useful as a
    # measure of immediately payable amount in the quick card.
    stats['pending_payments'] = total_unpaid
    context = {
        'stats': stats,
        'upcoming_appointments': upcoming_appointments,
        'recent_appointments': recent_appointments,
        'upcoming_personal': upcoming_personal,
        'recent_personal': recent_personal,
        'recent_payments': recent_payments,
        'profile': profile,
        'recent_purchases': recent_purchases,
        'recent_rentals': recent_rentals,
        'recent_pharmacy_activities': recent_pharmacy_activities,
        'recent_pharmacy_orders': recent_pharmacy_orders,
    }
    
    return render(request, 'dashboard/patient_dashboard.html', context)


@login_required
def patient_balance(request):
    """
    Detailed view of patient's financial balance and payment history
    """
    user = request.user
    profile = user.patient_profile
    
    # Get all payments
    payments = Payment.objects.filter(
        patient=user
    ).select_related(
        'appointment', 'appointment__service',
        'pharmacy_order', 'equipment_purchase', 'equipment_rental'
    ).order_by('-created_at')
    # Exclude unpaid payments where the patient explicitly chose cash-after-service
    # These are treated as commitments (will be paid later) and should not be
    # shown in the actionable payments list on the balance page.
    payments = payments.exclude(Q(payment_method='cash') & Q(payment_status='unpaid'))

    # Exclude any payments tied to domain objects that are cancelled. We don't
    # want cancelled appointments/orders/purchases to appear in actionable
    # payments or affect totals on this page.
    payments = payments.exclude(
        Q(appointment__status='cancelled') |
        Q(pharmacy_order__status='cancelled') |
        Q(equipment_purchase__status='cancelled') |
        Q(equipment_rental__status='cancelled')
    )
    
    # Payment summary
    # Define amounts to exclude from 'total charges' and 'unpaid' when the patient
    # has committed to pay by cash after service, or when they have submitted
    # an online proof (so it's pending verification).

    # Cash commitments: cash method but still unpaid
    cash_committed_qs = Payment.objects.filter(
        patient=user,
        payment_status='unpaid',
        payment_method='cash'
    )
    cash_committed = cash_committed_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Online payments where proof has been submitted (treat as pending and exclude from unpaid)
    online_pending_qs = Payment.objects.filter(
        patient=user,
        payment_status='unpaid',
        payment_method='online'
    ).filter(
        Q(payment_proof_file__isnull=False) | ~Q(transaction_id='') | ~Q(payment_proof_url='')
    )
    online_pending = online_pending_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Total charges (raw) and adjusted (exclude commitments/pending)
    total_charges_raw = Payment.objects.filter(patient=user).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_charges_adjusted = total_charges_raw - cash_committed - online_pending

    # --- Additional aggregate: Gross obligation from domain records ---
    # Sum charges from services (appointments), pharmacy orders, equipment purchases and rentals.
    # Exclude cancelled domain records when computing gross obligation
    appointments_total = ServiceBooking.objects.filter(patient=user).exclude(status='cancelled').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    # PersonalAppointment uses `total_fee` as the computed amount. Personal
    # appointments have multiple cancel statuses; exclude any that start with
    # 'cancel' to be safe.
    personal_appointments_total = PersonalAppointment.objects.filter(patient=user).exclude(status__startswith='cancel').aggregate(total=Sum('total_fee'))['total'] or Decimal('0.00')
    pharmacy_total = PharmacyOrder.objects.filter(customer=user).exclude(status='cancelled').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    equipment_purchases_total = EquipmentPurchase.objects.filter(customer=user).exclude(status='cancelled').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    equipment_rentals_total = EquipmentRental.objects.filter(customer=user).exclude(status='cancelled').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    gross_total = appointments_total + personal_appointments_total + pharmacy_total + equipment_purchases_total + equipment_rentals_total

    # Total paid (already completed)
    total_paid = Payment.objects.filter(
        patient=user,
        payment_status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Total unpaid excludes cash_committed and online_pending
    # Total unpaid excludes cash_committed and online_pending, and also any
    # payments related to cancelled domain objects (those were removed above
    # from the `payments` queryset but we compute again for totals to be safe).
    total_unpaid_qs = Payment.objects.filter(
        patient=user,
        payment_status='unpaid'
    ).exclude(
        Q(payment_method='cash') & Q(payment_status='unpaid')
    ).exclude(
        Q(payment_method='online') & Q(payment_status='unpaid') & (
            Q(payment_proof_file__isnull=False) | ~Q(transaction_id='') | ~Q(payment_proof_url='')
        )
    ).exclude(
        Q(appointment__status='cancelled') |
        Q(pharmacy_order__status='cancelled') |
        Q(equipment_purchase__status='cancelled') |
        Q(equipment_rental__status='cancelled')
    )
    total_unpaid = total_unpaid_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context = {
        'profile': profile,
        'payments': payments,
        'total_charges': total_charges_adjusted,
        'total_charges_raw': total_charges_raw,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        # New fields per requested calculation
        'gross_total': gross_total,
        'paid_amount': total_paid,
        'net_unpaid': gross_total - total_paid,
        'cash_committed': cash_committed,
        'cash_committed_qs': cash_committed_qs,
        'online_pending': online_pending,
        'online_pending_qs': online_pending_qs,
    }
    
    return render(request, 'dashboard/patient_balance.html', context)


@login_required
def provider_dashboard(request):
    """
    Healthcare provider dashboard with appointments and earnings
    """
    user = request.user
    # Ensure provider_profile exists. Some provider users may be missing the
    # related ProviderProfile (e.g., imported users). Create a minimal one so
    # the dashboard can render and the user can complete their profile.
    try:
        profile = user.provider_profile
    except Exception:
        # Create a temporary provider profile with safe defaults. We generate
        # a non-conflicting temporary license_number so the unique constraint
        # is satisfied; admins/providers should update this via the profile
        # page.
        temp_license = f"pending-{user.id}-{int(timezone.now().timestamp())}"
        profile, _ = ProviderProfile.objects.get_or_create(
            user=user,
            defaults={
                'specialization': ProviderProfile.SPECIALIZATION_CHOICES[0][0],
                'license_number': temp_license,
                'years_of_experience': 0,
                'bio': '',
                'hourly_rate': Decimal('500.00'),
                'is_available': False,
            }
        )
    
    # Get date ranges
    today = timezone.now().date()
    this_week_start = today - timedelta(days=today.weekday())
    this_month_start = today.replace(day=1)
    
    # Today's marketplace service bookings
    todays_appointments = ServiceBooking.objects.filter(
        provider=user,
        appointment_date=today
    ).select_related('service', 'patient').order_by('appointment_time')
    
    # Upcoming marketplace service bookings
    upcoming_appointments = ServiceBooking.objects.filter(
        provider=user,
        appointment_date__gt=today,
        status__in=['confirmed', 'in_progress']
    ).select_related('service', 'patient').order_by('appointment_date', 'appointment_time')[:10]
    
    # Pending marketplace service requests (unassigned bookings matching provider specialization)
    pending_requests = ServiceBooking.objects.filter(
        status='pending',
        provider__isnull=True,
        service__category__name__icontains=profile.get_specialization_display()
    ).select_related('service', 'patient').order_by('appointment_date', 'appointment_time')[:5]
    
    # Statistics
    total_appointments = ServiceBooking.objects.filter(provider=user).count()
    completed_appointments = ServiceBooking.objects.filter(
        provider=user,
        status='completed'
    ).count()
    
    this_week_appointments = ServiceBooking.objects.filter(
        provider=user,
        appointment_date__gte=this_week_start,
        appointment_date__lte=today
    ).count()
    
    this_month_appointments = ServiceBooking.objects.filter(
        provider=user,
        appointment_date__gte=this_month_start
    ).count()
    
    # Earnings calculation
    total_hours = ServiceBooking.objects.filter(
        provider=user,
        status='completed'
    ).aggregate(total=Sum('duration_hours'))['total'] or Decimal('0')
    
    estimated_earnings = total_hours * profile.hourly_rate
    
    this_month_hours = ServiceBooking.objects.filter(
        provider=user,
        status='completed',
        appointment_date__gte=this_month_start
    ).aggregate(total=Sum('duration_hours'))['total'] or Decimal('0')
    
    this_month_earnings = this_month_hours * profile.hourly_rate
    
    # Rating
    average_rating = profile.rating
    
    stats = {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'this_week_appointments': this_week_appointments,
        'this_month_appointments': this_month_appointments,
        'estimated_earnings': estimated_earnings,
        'this_month_earnings': this_month_earnings,
        'average_rating': average_rating,
        'total_reviews': profile.total_reviews,
        'pending_requests_count': pending_requests.count(),
    }
    
    context = {
        'stats': stats,
        'todays_appointments': todays_appointments,
        'today_appointments_count': todays_appointments.count(),
        'upcoming_appointments': upcoming_appointments,
        'pending_requests': pending_requests,
        'pending_count': pending_requests.count(),
        'earnings_month': this_month_earnings,
        'profile': profile,
    }
    # Recent related activity: prefer activity from patients who booked with
    # this provider recently (90 days); fall back to any appointments, and
    # finally fall back to site-wide recent activity if the provider has no
    # patients yet. This avoids showing an empty area for new providers and
    # gives a sensible default.
    recent_window = timezone.now() - timedelta(days=90)
    # Activity scoped strictly to patients who booked with this provider.
    # Do NOT fallback to site-wide activity for providers; if there are no
    # patients, show empty lists so the provider sees only related activity.
    recent_patient_ids = list(ServiceBooking.objects.filter(provider=user).values_list('patient', flat=True).distinct())
    scoped_activity = bool(recent_patient_ids)

    if scoped_activity:
        recent_purchases = EquipmentPurchase.objects.filter(customer__in=recent_patient_ids).select_related('equipment', 'customer').order_by('-created_at')[:6]
        recent_rentals = EquipmentRental.objects.filter(customer__in=recent_patient_ids).select_related('equipment', 'customer').order_by('-created_at')[:6]

        recent_pharmacy_orders = PharmacyOrder.objects.filter(customer__in=recent_patient_ids).order_by('-created_at')[:6]
        recent_pharmacy_activities = PharmacyOrderActivity.objects.filter(order__customer__in=recent_patient_ids).select_related('order', 'actor').order_by('-created_at')[:8]

        recent_payments = Payment.objects.filter(
            Q(patient__in=recent_patient_ids) | Q(appointment__provider=user) | Q(service_booking__provider=user)
        ).select_related('appointment', 'service_booking', 'pharmacy_order', 'equipment_purchase', 'equipment_rental', 'patient').order_by('-created_at')[:8]
    else:
        # No patients for this provider yet — present empty querysets (no site-wide fallback)
        recent_purchases = EquipmentPurchase.objects.none()
        recent_rentals = EquipmentRental.objects.none()
        recent_pharmacy_orders = PharmacyOrder.objects.none()
        recent_pharmacy_activities = PharmacyOrderActivity.objects.none()
        recent_payments = Payment.objects.none()

    # Additionally, include provider's own recent orders/payments so providers
    # can see equipment/pharmacy activity they initiated themselves.
    provider_recent_purchases = EquipmentPurchase.objects.filter(customer=user).select_related('equipment').order_by('-created_at')[:6]
    provider_recent_rentals = EquipmentRental.objects.filter(customer=user).select_related('equipment').order_by('-created_at')[:6]
    provider_recent_pharmacy_orders = PharmacyOrder.objects.filter(customer=user).order_by('-created_at')[:6]
    provider_recent_payments = Payment.objects.filter(
        patient=user
    ).select_related('appointment', 'service_booking', 'pharmacy_order', 'equipment_purchase', 'equipment_rental').order_by('-created_at')[:8]

    # Merge into context so the provider dashboard template can render activity lists.
    context.update({
        'recent_purchases': recent_purchases,
        'recent_rentals': recent_rentals,
        'recent_pharmacy_orders': recent_pharmacy_orders,
        'recent_pharmacy_activities': recent_pharmacy_activities,
        'recent_payments': recent_payments,
        'recent_activity_scoped': scoped_activity,
        'provider_recent_purchases': provider_recent_purchases,
        'provider_recent_rentals': provider_recent_rentals,
        'provider_recent_pharmacy_orders': provider_recent_pharmacy_orders,
        'provider_recent_payments': provider_recent_payments,
    })
    
    return render(request, 'dashboard/provider_dashboard.html', context)


@login_required
def provider_schedule(request):
    """
    Provider's schedule view - calendar of all appointments
    """
    if request.user.role != 'provider':
        return redirect('dashboard:home')
    
    user = request.user
    
    # Get month and year from query params
    current_date = timezone.now()
    month = int(request.GET.get('month', current_date.month))
    year = int(request.GET.get('year', current_date.year))
    
    # Get marketplace service bookings for the selected month
    appointments = ServiceBooking.objects.filter(
        provider=user,
        appointment_date__year=year,
        appointment_date__month=month
    ).select_related('service', 'patient').order_by('appointment_date', 'appointment_time')
    
    context = {
        'appointments': appointments,
        'current_month': month,
        'current_year': year,
    }
    
    return render(request, 'dashboard/provider_schedule.html', context)


@login_required
def admin_dashboard(request):
    """
    Admin dashboard with system-wide statistics
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard:home')
    
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    last_30_days = today - timedelta(days=30)
    
    # User statistics
    total_users = User.objects.count()
    total_patients = User.objects.filter(role='patient').count()
    total_providers = User.objects.filter(role='provider', is_active=True).count()
    pending_providers = User.objects.filter(role='provider', is_active=False).count()
    
    # Marketplace booking statistics
    total_appointments = ServiceBooking.objects.count()
    this_month_appointments = ServiceBooking.objects.filter(
        created_at__gte=this_month_start
    ).count()
    
    pending_appointments = ServiceBooking.objects.filter(status='pending').count()
    completed_appointments = ServiceBooking.objects.filter(status='completed').count()
    
    # Financial statistics
    total_revenue = Payment.objects.filter(
        payment_status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    this_month_revenue = Payment.objects.filter(
        payment_status='paid',
        payment_date__gte=this_month_start
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    pending_payments_total = Payment.objects.filter(
        payment_status='unpaid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Service statistics
    total_services = Service.objects.filter(is_active=True).count()
    most_booked_services = Service.objects.filter(
        is_active=True
    ).order_by('-total_bookings')[:5]
    
    # Recent activity
    recent_appointments = ServiceBooking.objects.select_related(
        'patient', 'provider', 'service'
    ).order_by('-created_at')[:10]
    
    recent_payments = Payment.objects.select_related(
        'patient', 'appointment', 'service_booking'
    ).order_by('-created_at')[:10]
    
    stats = {
        'total_users': total_users,
        'total_patients': total_patients,
        'total_providers': total_providers,
        'pending_providers': pending_providers,
        'total_appointments': total_appointments,
        'this_month_appointments': this_month_appointments,
        'pending_appointments': pending_appointments,
        'completed_appointments': completed_appointments,
        'total_revenue': total_revenue,
        'this_month_revenue': this_month_revenue,
        'pending_payments_total': pending_payments_total,
        'total_services': total_services,
    }
    
    context = {
        # Provide both machine-friendly stats and aliases expected by templates
        'stats': stats,
        'most_booked_services': most_booked_services,
        'recent_appointments': recent_appointments,
        'recent_payments': recent_payments,
        'recent_activity': [
            f"Appointment: {a.patient.get_full_name()} booked {a.service.name} on {a.appointment_date.strftime('%Y-%m-%d')}" for a in recent_appointments
        ] + [
            f"Payment: {p.patient.get_full_name()} - रू {p.amount} ({p.get_payment_status_display() if hasattr(p, 'get_payment_status_display') else p.payment_status})" for p in recent_payments
        ],
        # Aliases expected by admin template
        'stats': {
            **stats,
            'users_count': total_users,
            'services_count': total_services,
            'pending_payments_total': pending_payments_total,
        },
    }
    
    return render(request, 'dashboard/admin_dashboard.html', context)