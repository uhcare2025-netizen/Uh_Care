from django.db import models
from apps.accounts.models import User
from apps.appointments.models import Appointment
from apps.appointments.models import ServiceBooking
from django.conf import settings
from apps.accounts.models import User

class Payment(models.Model):
    """
    Payment tracking for all transactions
    """
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash After Service'),
        ('online', 'Online Payment (QR)'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('unpaid', 'Unpaid'),
        ('pending', 'Pending verification'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('partial', 'Partially Paid'),
    )
    
    # Reference (can be expanded for equipment, pharmacy later)
    appointment = models.ForeignKey(
        Appointment, 
        on_delete=models.CASCADE, 
        related_name='payments',
        null=True,
        blank=True
    )

    # New: reference to ServiceBooking for migrated/new service payments
    service_booking = models.ForeignKey(
        ServiceBooking,
        on_delete=models.CASCADE,
        related_name='payments_as_service_booking',
        null=True,
        blank=True
    )

    # Link to other order types (pharmacy, equipment) for unified payments
    pharmacy_order = models.ForeignKey(
        'pharmacy.PharmacyOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )

    equipment_purchase = models.ForeignKey(
        'equipment.EquipmentPurchase',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )

    equipment_rental = models.ForeignKey(
        'equipment.EquipmentRental',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )
    
    # Payment Details
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Allow null/blank so the method is chosen explicitly on the payment detail page
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, null=True, blank=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    
    # Online payment details
    transaction_id = models.CharField(max_length=100, blank=True, help_text="Bank/QR transaction ID")
    payment_proof_url = models.URLField(blank=True, null=True, help_text="Screenshot of payment")
    # Optional uploaded proof file (stored in MEDIA_ROOT/payments/proofs/)
    payment_proof_file = models.ImageField(upload_to='payments/proofs/', blank=True, null=True)
    
    # Verification
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='verified_payments'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'payments'
        indexes = [
            models.Index(fields=['patient', 'payment_status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment #{self.id} - NPR {self.amount} ({self.payment_status})"

    def save(self, *args, **kwargs):
        """
        Prevent changing the payment_method once it has been set. Views that
        legitimately need to set the payment method on first-write should do so
        when creating the Payment (or set the `_allow_payment_method_change`
        attribute on the instance to True to permit overriding, which the admin
        UI will do for staff users).
        """
        # Only enforce immutability when this is an update to an existing record
        if self.pk:
            try:
                old = Payment.objects.get(pk=self.pk)
            except Payment.DoesNotExist:
                old = None

            if old and old.payment_method and self.payment_method != old.payment_method:
                # Allow override if explicitly requested by caller (admin or special flow)
                if getattr(self, '_allow_payment_method_change', False):
                    # proceed with save
                    pass
                else:
                    # Revert the attempted change by keeping old value and avoid saving
                    from django.core.exceptions import ValidationError
                    raise ValidationError('Payment method is locked and cannot be changed once set.')

        return super().save(*args, **kwargs)


class UserPaymentMethod(models.Model):
    """Store user-specific payment preferences (QR, bank details, default method).

    This lets providers and patients store a preferred payment method that can
    be used to prefill payment records during checkout.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods')
    method = models.CharField(max_length=20, choices=Payment.PAYMENT_METHOD_CHOICES)
    qr_code_url = models.URLField(blank=True, null=True, help_text='Optional QR image or payment link')
    bank_info = models.TextField(blank=True, null=True, help_text='Bank account / UPI / other details')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_payment_methods'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_method_display()}" 