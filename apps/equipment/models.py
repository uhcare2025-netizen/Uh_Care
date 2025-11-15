from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class EquipmentCategory(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'equipment_categories'
        ordering = ['name']

    def __str__(self):
        return self.name
    


class Equipment(models.Model):
    CONDITION_CHOICES = (
        ('new', 'New'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
    )

    category = models.ForeignKey(EquipmentCategory, on_delete=models.SET_NULL, null=True, related_name='equipments')
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=300, blank=True, help_text="Brief description for listings")
    image_url = models.URLField(blank=True, null=True)
    # Local image upload for equipment
    image = models.ImageField(upload_to='equipment/', blank=True, null=True)
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'))
    rent_price_daily = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'), help_text="Alias for price_per_day")
    rent_price_weekly = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'))
    rent_price_monthly = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'))
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'))
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'))
    brand = models.CharField(max_length=100, blank=True, help_text="Equipment brand/manufacturer")
    model_number = models.CharField(max_length=100, blank=True, help_text="Model number or identifier")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='excellent')
    specifications = models.TextField(blank=True, help_text="Technical specifications")
    usage_instructions = models.TextField(blank=True, help_text="How to use this equipment")
    
    @property
    def is_available(self):
        """Return True when equipment is active and there are available units.

        Templates and views sometimes check `equipment.is_available`; provide
        a property here so views/templates behave consistently.
        """
        return bool(self.is_active and (self.available_units or 0) > 0)

    @property
    def availability(self):
        """Infer availability tag used by templates: 'rent', 'buy', 'both', or 'none'.

        Infer from price fields so older templates that check
        `equipment.availability` work without a DB field.
        """
        has_rent = any([
            bool(self.price_per_day),
            bool(getattr(self, 'rent_price_weekly', None)),
            bool(getattr(self, 'rent_price_monthly', None)),
        ])
        has_buy = bool(getattr(self, 'purchase_price', None))

        if has_rent and has_buy:
            return 'both'
        if has_rent:
            return 'rent'
        if has_buy:
            return 'buy'
        return 'none'
    total_units = models.PositiveIntegerField(default=0)
    available_units = models.PositiveIntegerField(default=0)
    total_rentals = models.PositiveIntegerField(default=0)
    total_purchases = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        db_table = 'equipments'
        ordering = ['name']

    def __str__(self):
        return self.name



class EquipmentRental(models.Model):
    RENTAL_PERIOD_CHOICES = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    )

    rental_number = models.CharField(max_length=50, unique=True, editable=False)
    customer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='equipment_rentals')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='rentals')
    rental_period = models.CharField(max_length=20, choices=RENTAL_PERIOD_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField()
    rental_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_address = models.TextField()
    delivery_phone = models.CharField(max_length=20)
    delivery_instructions = models.TextField(blank=True)
    customer_notes = models.TextField(blank=True)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    damage_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deposit_paid = models.BooleanField(default=False)
    deposit_refunded = models.BooleanField(default=False)
    condition_at_delivery = models.TextField(blank=True)
    condition_at_return = models.TextField(blank=True)
    damage_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    actual_return_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'equipment_rentals'
        ordering = ['-created_at']

    def __str__(self):
        return f"Rental #{self.rental_number}"

    @property
    def rental_days(self):
        return (self.end_date - self.start_date).days + 1

    def save(self, *args, **kwargs):
        # Prevent modifying critical rental fields once rental is no longer pending
        if self.pk:
            try:
                old = EquipmentRental.objects.get(pk=self.pk)
            except EquipmentRental.DoesNotExist:
                old = None

            if old and old.status != 'pending' and not getattr(self, '_allow_modification', False):
                # Fields that must not change after confirmation/processing
                locked_fields = [
                    'rental_period', 'quantity', 'start_date', 'end_date',
                    'delivery_address', 'delivery_phone', 'delivery_instructions', 'customer_notes'
                ]
                for f in locked_fields:
                    if getattr(old, f) != getattr(self, f):
                        raise ValidationError('This rental cannot be modified after it has been confirmed/processed. To change your booking, please create a new rental.')

        if not self.rental_number:
            import uuid
            self.rental_number = f"ER{uuid.uuid4().hex[:8].upper()}"

        # ensure total_amount is computed
        try:
            self.total_amount = (self.rental_price + self.security_deposit + self.delivery_charge + self.late_fee + self.damage_charge)
        except Exception:
            pass

        super().save(*args, **kwargs)


class EquipmentPurchase(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )

    order_number = models.CharField(max_length=50, unique=True, editable=False)
    customer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='equipment_purchases')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='purchases')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivery_address = models.TextField()
    delivery_phone = models.CharField(max_length=20)
    delivery_instructions = models.TextField(blank=True)
    customer_notes = models.TextField(blank=True)
    warranty_months = models.PositiveIntegerField(default=0)
    warranty_expires_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'equipment_purchases'
        ordering = ['-created_at']

    def __str__(self):
        return f"Purchase #{self.order_number}"

    def save(self, *args, **kwargs):
        # Prevent modifying critical purchase fields once purchase is no longer pending
        if self.pk:
            try:
                old = EquipmentPurchase.objects.get(pk=self.pk)
            except EquipmentPurchase.DoesNotExist:
                old = None

            if old and old.status != 'pending' and not getattr(self, '_allow_modification', False):
                locked_fields = [
                    'quantity', 'delivery_address', 'delivery_phone', 'delivery_instructions', 'customer_notes'
                ]
                for f in locked_fields:
                    if getattr(old, f) != getattr(self, f):
                        raise ValidationError('This purchase cannot be modified after it has been confirmed/processed. To change your order, please place a new one.')

        if not self.order_number:
            import uuid
            self.order_number = f"EP{uuid.uuid4().hex[:8].upper()}"

        # calculate amounts
        self.subtotal = self.unit_price * self.quantity
        self.total_amount = self.subtotal + self.delivery_charge - self.discount
        super().save(*args, **kwargs)


class EquipmentWishlist(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='equipment_wishlist')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='wishlisted_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'equipment_wishlists_equipment'
        unique_together = ('user', 'equipment')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.username} - {self.equipment.name}"
