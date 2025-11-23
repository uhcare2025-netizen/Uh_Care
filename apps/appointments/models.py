from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.accounts.models import User
from apps.services.models import Service
from decimal import Decimal

class Appointment(models.Model):
    """
    DEPRECATED: Legacy appointment/booking model - no longer used for marketplace bookings.
    Kept for backward compatibility and historical data. Use ServiceBooking for new marketplace bookings.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    )
    
    # References
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patient_appointments')
    provider = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='provider_appointments'
    )
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='appointments')
    
    # Scheduling
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)
    
    # Location
    service_address = models.TextField(help_text="Where the service will be provided")
    
    # Pricing
    service_price = models.DecimalField(max_digits=10, decimal_places=2)
    additional_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Admin-confirmed final price after assessment (optional)
    final_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final price set by admin/provider after assessment (overrides service_price in totals)",
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Notes
    patient_notes = models.TextField(blank=True, help_text="Special instructions from patient")
    provider_notes = models.TextField(blank=True, help_text="Provider notes after service")
    cancellation_reason = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'appointments'
        indexes = [
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['appointment_date', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-appointment_date', '-appointment_time']
    
    def __str__(self):
        return f"Appointment #{self.id} - {self.service.name} on {self.appointment_date}"

    def clean(self):
        """Validate that any provided prices fall within the service's advertised range."""
        errors = {}
        svc = getattr(self, 'service', None)
        # Only validate if service is present
        if svc:
            # Validate service_price
            if self.service_price is not None:
                if svc.price_min is not None and self.service_price < svc.price_min:
                    errors['service_price'] = ValidationError('Service price cannot be less than the service minimum price.')
                if svc.price_max is not None and self.service_price > svc.price_max:
                    errors['service_price'] = ValidationError('Service price cannot be greater than the service maximum price.')

            # Validate final_price if present
            if self.final_price is not None:
                if svc.price_min is not None and self.final_price < svc.price_min:
                    errors['final_price'] = ValidationError('Final price cannot be less than the service minimum price.')
                if svc.price_max is not None and self.final_price > svc.price_max:
                    errors['final_price'] = ValidationError('Final price cannot be greater than the service maximum price.')

        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        # Calculate total amount. If admin has set a final_price, use it for totals.
        effective_price = self.final_price if (self.final_price is not None) else self.service_price
        self.total_amount = (effective_price or Decimal('0.00')) + (self.additional_charges or Decimal('0.00'))
        # Prevent editing critical appointment details after confirmation unless allowed
        if self.pk:
            try:
                old = Appointment.objects.get(pk=self.pk)
            except Appointment.DoesNotExist:
                old = None

            if old and old.status != 'pending' and not getattr(self, '_allow_modification', False):
                locked_fields = ['appointment_date', 'appointment_time', 'service', 'service_address', 'patient']
                for f in locked_fields:
                    if getattr(old, f) != getattr(self, f):
                        raise ValidationError('Appointments cannot be changed after confirmation/processing. To schedule a new appointment, please create a new booking.')

        super().save(*args, **kwargs)


class ServiceBooking(models.Model):
    """
    Non-destructive new model for marketplace service bookings.
    Initially mirrors the existing `Appointment` table; we will migrate data
    from `Appointment` into `ServiceBooking` via a data migration.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    )

    # References
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patient_service_bookings')
    provider = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_service_bookings'
    )
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='service_bookings')

    # Scheduling
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    # Location
    service_address = models.TextField(help_text="Where the service will be provided")

    # Pricing
    service_price = models.DecimalField(max_digits=10, decimal_places=2)
    additional_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final price set by admin/provider after assessment (overrides service_price in totals)",
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Notes
    patient_notes = models.TextField(blank=True, help_text="Special instructions from patient")
    provider_notes = models.TextField(blank=True, help_text="Provider notes after service")
    cancellation_reason = models.TextField(blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'service_bookings'
        verbose_name = 'Service Booking'
        verbose_name_plural = 'Service Bookings'
        indexes = [
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['appointment_date', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-appointment_date', '-appointment_time']

    def __str__(self):
        return f"ServiceBooking #{self.id} - {self.service.name} on {self.appointment_date}"

    def save(self, *args, **kwargs):
        # Calculate total amount: prefer final_price when set
        effective_price = self.final_price if (self.final_price is not None) else self.service_price
        self.total_amount = (effective_price or Decimal('0.00')) + (self.additional_charges or Decimal('0.00'))
        super().save(*args, **kwargs)


class ProviderAvailability(models.Model):
    """
    Provider working hours and availability
    """
    WEEKDAYS = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )
    
    provider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='availability_slots')
    day_of_week = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'provider_availability'
        unique_together = ('provider', 'day_of_week', 'start_time')
        ordering = ['day_of_week', 'start_time']
    
    def __str__(self):
        return f"{self.provider.get_full_name()} - {self.get_day_of_week_display()}"


class ProviderSchedule(models.Model):
    """
    Provider's availability schedule for personal appointments
    """
    WEEKDAYS = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )
    
    provider = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='schedule_slots',
        limit_choices_to={'role': 'provider'}
    )
    day_of_week = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration = models.IntegerField(default=30, help_text="Duration in minutes")
    is_available = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'provider_schedules'
        unique_together = ('provider', 'day_of_week', 'start_time')
        ordering = ['day_of_week', 'start_time']
    
    def __str__(self):
        return f"{self.provider.get_full_name()} - {self.get_day_of_week_display()}"


class PersonalAppointment(models.Model):
    """
    Personal appointments between patient and provider
    Separate from service bookings
    """
    APPOINTMENT_TYPES = (
        ('consultation', 'General Consultation'),
        ('follow_up', 'Follow-up'),
        ('emergency', 'Emergency'),
        ('screening', 'Health Screening'),
        ('counseling', 'Counseling'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled_by_patient', 'Cancelled by Patient'),
        ('cancelled_by_provider', 'Cancelled by Provider'),
        ('no_show', 'No Show'),
    )
    
    # Participants
    patient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='personal_appointments',
        limit_choices_to={'role': 'patient'}
    )
    provider = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='provider_personal_appointments',
        limit_choices_to={'role': 'provider'}
    )
    
    # Appointment details
    appointment_type = models.CharField(max_length=50, choices=APPOINTMENT_TYPES)
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    duration_minutes = models.IntegerField(default=30)
    
    # Location
    # Removed 'home' and 'clinic' delivery types per product decision.
    LOCATION_TYPE = (
        ('video', 'Video Call'),
        ('phone', 'Phone Call'),
    )
    # Default to 'video' to reflect most common remote appointments
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE, default='video')
    # Address is optional for remote appointments; keep field for backward compatibility
    location_address = models.TextField(blank=True, help_text="Optional address (only needed for in-person bookings)")
    video_link = models.URLField(blank=True, help_text="For video appointments")
    
    # Reason & Notes
    reason = models.TextField(help_text="Reason for appointment")
    symptoms = models.TextField(blank=True, help_text="Current symptoms if any")
    # Patient contact captured at booking time
    patient_phone = models.CharField(max_length=32, blank=True, help_text="Phone number provided by patient for this appointment")
    patient_notes = models.TextField(blank=True)
    provider_notes = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    prescription = models.TextField(blank=True)
    
    # Fees
    consultation_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('500.00')
    )
    additional_charges = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_fee = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    
    # Cancellation
    cancellation_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Reminders
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'personal_appointments'
        ordering = ['-appointment_date', '-appointment_time']
        indexes = [
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['appointment_date', 'status']),
        ]
    
    def __str__(self):
        return f"Personal Appointment #{self.id} - {self.patient.get_full_name()} with {self.provider.get_full_name()}"
    
    def save(self, *args, **kwargs):
        # Calculate total fee
        self.total_fee = self.consultation_fee + self.additional_charges
        # Prevent editing personal appointment details after confirmation unless allowed
        if self.pk:
            try:
                old = PersonalAppointment.objects.get(pk=self.pk)
            except PersonalAppointment.DoesNotExist:
                old = None

            if old and old.status != 'pending' and not getattr(self, '_allow_modification', False):
                locked_fields = ['appointment_date', 'appointment_time', 'location_type', 'location_address', 'patient', 'provider']
                for f in locked_fields:
                    if getattr(old, f) != getattr(self, f):
                        raise ValidationError('Appointments cannot be modified after confirmation/processing. To change your booking, please create a new appointment.')

        super().save(*args, **kwargs)


class AppointmentReview(models.Model):
    """
    Patient reviews for completed personal appointments
    """
    appointment = models.OneToOneField(
        PersonalAppointment,
        on_delete=models.CASCADE,
        related_name='review'
    )
    rating = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)],
        help_text="Rating from 1 to 5 stars"
    )
    review_text = models.TextField()
    would_recommend = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'appointment_reviews'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Review for Appointment #{self.appointment.id} - {self.rating} stars"