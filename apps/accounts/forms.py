from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, PatientProfile, ProviderProfile

class PatientRegistrationForm(UserCreationForm):
    """
    Form for patient registration
    """
    medical_history = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        help_text="Please list any medical conditions, allergies, or current medications"
    )
    blood_group = forms.CharField(
        max_length=5,
        required=False,
        help_text="e.g., A+, B-, O+, AB+"
    )
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone_number',
            'address', 'date_of_birth', 'emergency_contact',
            'password1', 'password2'
        ]

    # Override date_of_birth to accept several common input formats and
    # use an HTML5 date input so browsers show a date picker.
    date_of_birth = forms.DateField(
        required=False,
        input_formats=['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y'],
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    def save(self, commit=True):
        user = super().save(commit=False)
        # Normalize email and use it as username
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
            user.email = email
            user.username = email
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add bootstrap-friendly classes and placeholders to widgets
        for name, field in self.fields.items():
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css + ' form-control').strip()
            # Provide helpful placeholders for common fields
            if name == 'email':
                field.widget.attrs['placeholder'] = 'you@example.com'
                field.help_text = 'We will use this email as your username. Enter a valid email address.'
            if name == 'first_name':
                field.widget.attrs['placeholder'] = 'Given name'
            if name == 'last_name':
                field.widget.attrs['placeholder'] = 'Family name'
            if name == 'phone_number':
                field.widget.attrs['placeholder'] = '+977-9800000000'
            if name in ('password1', 'password2'):
                field.widget.attrs['autocomplete'] = 'new-password'

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with this email already exists. Please use a different email or sign in.')
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            # Basic validation: allow digits, spaces, + and -; length check
            import re
            if not re.match(r'^[0-9 +\-()]{7,20}$', phone):
                raise forms.ValidationError('Enter a valid phone number (digits, spaces, +, - allowed).')
        return phone

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            from django.utils import timezone
            today = timezone.localdate()
            if dob > today:
                raise forms.ValidationError('Date of birth cannot be in the future.')
        return dob


class ProviderRegistrationForm(UserCreationForm):
    """
    Form for healthcare provider registration
    """
    specialization = forms.ChoiceField(
        choices=ProviderProfile.SPECIALIZATION_CHOICES,
        help_text="Select your area of specialization"
    )
    license_number = forms.CharField(
        max_length=50,
        help_text="Your professional license number"
    )
    years_of_experience = forms.IntegerField(
        min_value=0,
        help_text="Years of professional experience"
    )
    bio = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        help_text="Brief professional bio and expertise"
    )
    hourly_rate = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=0,
        help_text="Your hourly rate in NPR"
    )
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone_number',
            'address', 'date_of_birth', 'password1', 'password2'
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
            user.email = email
            user.username = email
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """
    User login form — accept either username or email as identifier.
    """
    identifier = forms.CharField(
        label='Username or email',
        widget=forms.TextInput(attrs={
            'placeholder': 'Username or email',
            'class': 'form-control',
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Password',
            'class': 'form-control',
            'autocomplete': 'current-password',
        })
    )


class ProfileUpdateForm(forms.ModelForm):
    """
    Form for updating user profile
    """
    # Explicitly expose an ImageField so the form renders a file input
    # and validates uploaded image files. Required=False so users can keep
    # an existing image or remove it via admin.
    profile_image = forms.ImageField(required=False, widget=forms.ClearableFileInput)
    def __init__(self, *args, user_role=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_role = user_role
        
        # Add profile-specific fields based on user role
        if user_role == 'patient':
            self.fields['medical_history'] = forms.CharField(
                widget=forms.Textarea(attrs={'rows': 4}),
                required=False
            )
            self.fields['blood_group'] = forms.CharField(
                max_length=5,
                required=False
            )
        elif user_role == 'provider':
            self.fields['specialization'] = forms.ChoiceField(
                choices=ProviderProfile.SPECIALIZATION_CHOICES
            )
            self.fields['license_number'] = forms.CharField(max_length=50)
            # Allow leaving years_of_experience blank when updating profile
            # (registration still requires the value). Use initial value from
            # the existing ProviderProfile if available so the form shows the
            # current value on GET requests.
            self.fields['years_of_experience'] = forms.IntegerField(min_value=0, required=False)
            self.fields['bio'] = forms.CharField(
                widget=forms.Textarea(attrs={'rows': 4}),
                required=False
            )
            self.fields['hourly_rate'] = forms.DecimalField(
                max_digits=8,
                decimal_places=2,
                min_value=0
            )
            # Populate initial values from the related profile when editing
            try:
                if self.instance and hasattr(self.instance, 'provider_profile'):
                    prof = self.instance.provider_profile
                    self.fields['specialization'].initial = prof.specialization
                    self.fields['license_number'].initial = prof.license_number
                    # years_of_experience may be zero; set initial explicitly
                    self.fields['years_of_experience'].initial = prof.years_of_experience
                    self.fields['bio'].initial = prof.bio
                    self.fields['hourly_rate'].initial = prof.hourly_rate
            except Exception:
                # If the related profile is missing or access fails, leave defaults
                pass
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number',
            'address', 'profile_image', 'emergency_contact'
        ]
        
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            
            # Update profile-specific fields
            if self.user_role == 'patient':
                profile = user.patient_profile
                profile.medical_history = self.cleaned_data.get('medical_history', '')
                profile.blood_group = self.cleaned_data.get('blood_group', '')
                profile.save()
            elif self.user_role == 'provider':
                profile = user.provider_profile
                profile.specialization = self.cleaned_data.get('specialization') or profile.specialization
                profile.license_number = self.cleaned_data.get('license_number') or profile.license_number
                # Preserve existing years_of_experience when the field is left blank
                yoe = self.cleaned_data.get('years_of_experience')
                if yoe is not None:
                    profile.years_of_experience = yoe
                profile.bio = self.cleaned_data.get('bio', profile.bio)
                profile.hourly_rate = self.cleaned_data.get('hourly_rate') or profile.hourly_rate
                profile.save()
                
        return user