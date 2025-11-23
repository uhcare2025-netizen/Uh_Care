from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

class User(AbstractUser):
    """
    Extended User model with role-based access
    """
    USER_ROLES = (
        ('patient', 'Patient'),
        ('provider', 'Healthcare Provider'),
        ('admin', 'Administrator'),
    )
    
    role = models.CharField(max_length=20, choices=USER_ROLES, default='patient')
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    # Allow uploading profile images (ImageField). In production this can
    # be backed by S3 when USE_S3=True; in development it uses the local
    # filesystem storage configured by MEDIA_ROOT.
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=15, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"


class PatientProfile(models.Model):
    """
    Additional information specific to patients
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    medical_history = models.TextField(blank=True, help_text="Known conditions, allergies, medications")
    blood_group = models.CharField(max_length=5, blank=True)
    total_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text="Total outstanding balance in NPR"
    )
    
    class Meta:
        db_table = 'patient_profiles'
    
    def __str__(self):
        return f"Patient: {self.user.get_full_name()}"


class ProviderProfile(models.Model):
    """
    Healthcare provider specific information
    """
    SPECIALIZATION_CHOICES = (
        ('nursing', 'Skilled Nursing'),
        ('physiotherapy', 'Physiotherapy'),
        ('geriatric', 'Elderly & Geriatric Care'),
        ('respiratory', 'Respiratory Care'),
        ('wound_care', 'Wound Care'),
        ('general', 'General Care'),
        ('general_counciller', 'General counciller'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='provider_profile')
    specialization = models.CharField(max_length=50, choices=SPECIALIZATION_CHOICES)
    license_number = models.CharField(max_length=50, unique=True)
    years_of_experience = models.PositiveIntegerField(default=0)
    bio = models.TextField(blank=True)
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=500.00)
    is_available = models.BooleanField(default=True)
    
    # Ratings (for future)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'provider_profiles'
        indexes = [
            models.Index(fields=['specialization']),
            models.Index(fields=['is_available']),
        ]
    
    def __str__(self):
        return f"Provider: {self.user.get_full_name()} - {self.get_specialization_display()}"