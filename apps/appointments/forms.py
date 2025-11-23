from django import forms
from datetime import date, time, datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import ServiceBooking
from apps.payments.models import Payment
from .models import PersonalAppointment


class AppointmentBookingForm(forms.ModelForm):
    """
    Form for booking marketplace service bookings.
    Uses the new `ServiceBooking` model (mirrors old `Appointment`).
    """
    
    class Meta:
        model = ServiceBooking
        fields = [
            'appointment_date',
            'appointment_time',
            'duration_hours',
            'service_address',
            'patient_notes',
            'additional_charges',
        ]
        widgets = {
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'min': date.today().isoformat()
            }),
            'appointment_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control'
            }),
            'duration_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '0.5'
            }),
            'service_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter the full address where service is needed'
            }),
            'patient_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any special instructions or requirements (optional)'
            }),
            'additional_charges': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'readonly': True
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.service = kwargs.pop('service', None)
        super().__init__(*args, **kwargs)
        
        # Set initial additional charges to 0
        self.fields['additional_charges'].initial = Decimal('0.00')
        self.fields['additional_charges'].disabled = True
        # Allow patient to optionally request a preferred price (validated against service range)
        from django.core.validators import MinValueValidator
        self.fields['requested_price'] = forms.DecimalField(
            required=False,
            max_digits=10,
            decimal_places=2,
            widget=forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.00'
            })
        )

        if self.service:
            # If service advertises a min/max, communicate it via help_text and widget attrs
            if self.service.price_min is not None:
                self.fields['requested_price'].widget.attrs['min'] = str(self.service.price_min)
                self.fields['requested_price'].help_text = f"Minimum allowed: {self.service.price_min}"
            if self.service.price_max is not None:
                self.fields['requested_price'].widget.attrs['max'] = str(self.service.price_max)
                extra = self.fields['requested_price'].help_text or ''
                self.fields['requested_price'].help_text = (extra + f" Maximum allowed: {self.service.price_max}").strip()
    
    def clean_appointment_date(self):
        appointment_date = self.cleaned_data.get('appointment_date')
        
        if appointment_date < date.today():
            raise forms.ValidationError('Appointment date cannot be in the past.')
        
        # Check minimum booking notice (24 hours)
        if appointment_date == date.today():
            raise forms.ValidationError(
                'Please book at least 24 hours in advance.'
            )
        
        return appointment_date
    
    def clean_appointment_time(self):
        appointment_time = self.cleaned_data.get('appointment_time')
        
        # Validate business hours (6 AM to 10 PM)
        if appointment_time < time(6, 0) or appointment_time > time(22, 0):
            raise forms.ValidationError(
                'Please select a time between 6:00 AM and 10:00 PM.'
            )
        
        return appointment_time
    
    def clean(self):
        cleaned_data = super().clean()
        # Validate requested_price against service range if provided
        requested_price = cleaned_data.get('requested_price')
        if requested_price is not None and self.service:
            if self.service.price_min is not None and requested_price < self.service.price_min:
                self.add_error('requested_price', f'Requested price cannot be less than {self.service.price_min}.')
            if self.service.price_max is not None and requested_price > self.service.price_max:
                self.add_error('requested_price', f'Requested price cannot be greater than {self.service.price_max}.')
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')
        
        if appointment_date and appointment_time:
            # Combine date and time for validation
            appointment_datetime = datetime.combine(appointment_date, appointment_time)

            # Make appointment_datetime timezone-aware if necessary so it can be
            # compared against timezone-aware `timezone.now()` (avoids TypeError
            # "can't compare offset-naive and offset-aware datetimes").
            try:
                if timezone.is_naive(appointment_datetime):
                    appointment_datetime = timezone.make_aware(
                        appointment_datetime, timezone.get_current_timezone()
                    )
            except Exception:
                # Fallback: if timezone utilities aren't available or conversion
                # fails, leave as-is; comparison will raise and surface in tests.
                pass

            # Check if datetime is at least 24 hours from now
            if appointment_datetime < (timezone.now() + timedelta(hours=24)):
                raise forms.ValidationError(
                    'Appointments must be booked at least 24 hours in advance.'
                )

            # Check for existing appointment for the same service at same slot
            service = getattr(self, 'service', None)
            if service:
                conflict_qs = ServiceBooking.objects.filter(
                    service=service,
                    appointment_date=appointment_date,
                    appointment_time=appointment_time,
                    status__in=['pending', 'confirmed', 'in_progress']
                )
                # If editing an existing appointment, exclude self
                if self.instance and self.instance.pk:
                    conflict_qs = conflict_qs.exclude(pk=self.instance.pk)

                if conflict_qs.exists():
                    raise forms.ValidationError('Selected time slot is no longer available.')
        
        return cleaned_data


class PersonalAppointmentForm(forms.ModelForm):
    """Form for booking a personal appointment with a specific provider."""
    class Meta:
        model = PersonalAppointment
        fields = [
            'appointment_type', 'appointment_date', 'appointment_time', 'duration_minutes',
            'location_type', 'location_address', 'video_link', 'patient_phone', 'reason', 'symptoms',
            'patient_notes', 'consultation_fee', 'additional_charges',
        ]
        widgets = {
            'appointment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'appointment_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'location_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'patient_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your phone number'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'symptoms': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'patient_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'consultation_fee': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'additional_charges': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        # Expect provider to be passed in so we can set consultation_fee
        self.provider = kwargs.pop('provider', None)
        super().__init__(*args, **kwargs)

        # If provider supplied, set consultation_fee initial and make it readonly
        if self.provider and hasattr(self.provider, 'provider_profile'):
            rate = getattr(self.provider.provider_profile, 'hourly_rate', None)
            if rate is not None:
                self.fields['consultation_fee'].initial = rate
                # keep the visible field readonly for UX, but also include a
                # hidden field in the template (or rely on save()) because
                # disabled inputs are not submitted. We still mark as
                # disabled here to prevent user edits in the UI.
                self.fields['consultation_fee'].disabled = True

        # Ensure video link is optional at form level (model has blank=True
        # but make explicit here for clarity)
        if 'video_link' in self.fields:
            self.fields['video_link'].required = False

        # Default additional charges
        self.fields['additional_charges'].initial = Decimal('0.00')
        self.fields['additional_charges'].disabled = False

    def clean_appointment_date(self):
        appointment_date = self.cleaned_data.get('appointment_date')
        if appointment_date < date.today():
            raise forms.ValidationError('Appointment date cannot be in the past.')

        # Allow same-day only if after current time + minimal lead (optional)
        return appointment_date

    def clean(self):
        cleaned = super().clean()
        appointment_date = cleaned.get('appointment_date')
        appointment_time = cleaned.get('appointment_time')

        if appointment_date and appointment_time:
            appointment_dt = datetime.combine(appointment_date, appointment_time)
            try:
                if timezone.is_naive(appointment_dt):
                    appointment_dt = timezone.make_aware(appointment_dt, timezone.get_current_timezone())
            except Exception:
                pass

            if appointment_dt < (timezone.now() + timedelta(hours=1)):
                # require at least 1 hour notice for personal appointments
                raise forms.ValidationError('Please select a slot at least 1 hour from now.')

            # Check provider availability / existing bookings collisions
            provider = self.provider or getattr(self.instance, 'provider', None)
            if provider:
                conflict_qs = PersonalAppointment.objects.filter(
                    provider=provider,
                    appointment_date=appointment_date,
                    appointment_time=appointment_time,
                    status__in=['pending', 'confirmed']
                )
                # If editing existing appointment, exclude self
                if self.instance and self.instance.pk:
                    conflict_qs = conflict_qs.exclude(pk=self.instance.pk)

                if conflict_qs.exists():
                    raise forms.ValidationError('Selected time slot is no longer available.')

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Ensure fees are set correctly
        if self.provider and hasattr(self.provider, 'provider_profile'):
            rate = getattr(self.provider.provider_profile, 'hourly_rate', None)
            if rate is not None:
                instance.consultation_fee = rate

        instance.total_fee = (instance.consultation_fee or Decimal('0.00')) + (instance.additional_charges or Decimal('0.00'))

        if commit:
            instance.save()
        return instance