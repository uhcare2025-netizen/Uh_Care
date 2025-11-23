from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class ServiceCategory(models.Model):
    """
    Categories for healthcare services
    """
    name = models.CharField(max_length=100, unique=True)
    # optional slug used for category URLs
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.URLField(blank=True, null=True)  # Cloud URL for icon
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'service_categories'
        verbose_name_plural = 'Service Categories'
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # lazily populate slug from name if not set
        from django.utils.text import slugify
        if not getattr(self, 'slug', None):
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Service(models.Model):
    """
    Healthcare services offered by UH Care
    """
    DURATION_UNITS = (
        ('hour', 'Per Hour'),
        ('session', 'Per Session'),
        ('day', 'Per Day'),
        ('week', 'Per Week'),
        ('month', 'Per Month'),
    )
    
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True)
    
    # Pricing
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    # Optional price range (allow services to advertise a min/max price)
    price_min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Minimum advertised price for this service (optional)"
    )
    price_max = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Maximum advertised price for this service (optional)"
    )
    duration_unit = models.CharField(max_length=20, choices=DURATION_UNITS, default='session')
    
    # Security Deposit (optional)
    requires_security_deposit = models.BooleanField(
        default=False,
        help_text="Check if this service requires a security deposit"
    )
    security_deposit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Security deposit amount (refundable after service completion)"
    )
    security_deposit_description = models.TextField(
        blank=True,
        help_text="Additional notes about the security deposit (e.g., conditions for refund)"
    )
    
    # Details
    what_included = models.TextField(help_text="What's included in this service")
    requirements = models.TextField(blank=True, help_text="Patient requirements or preparations")
    
    # Media
    image_url = models.URLField(blank=True, null=True)  # Cloud URL
    # Local image upload (optional) - stored under MEDIA_ROOT/services/
    image = models.ImageField(upload_to='services/', blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_bookings = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'services'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active', 'is_featured']),
            models.Index(fields=['category', 'is_active']),
        ]
        ordering = ['-is_featured', 'name']
    
    def clean(self):
        """
        Model-level validation for price range consistency.
        Ensures price_min <= price_max when both provided and that base_price
        falls within the range if both bounds are present.
        """
        from django.core.exceptions import ValidationError

        if self.price_min is not None and self.price_max is not None:
            if self.price_min > self.price_max:
                raise ValidationError({'price_max': 'price_max must be greater than or equal to price_min.'})

        # If base_price exists and bounds exist, ensure base_price falls within them
        if self.base_price is not None:
            if self.price_min is not None and self.base_price < self.price_min:
                raise ValidationError({'base_price': 'base_price cannot be less than price_min.'})
            if self.price_max is not None and self.base_price > self.price_max:
                raise ValidationError({'base_price': 'base_price cannot be greater than price_max.'})

    def save(self, *args, **kwargs):
        # Run model validation before saving to ensure integrity
        try:
            self.full_clean()
        except Exception:
            # Let Django/routing surface validation errors in admin/forms; re-raise
            raise
        super().save(*args, **kwargs)

    def get_price_display(self):
        """Return a human-friendly price or price range string (amount only, no unit).

        Formats numbers with thousands separators and drops unnecessary ".00" cents when present.
        Examples: 'NPR 500', 'NPR 1,200', 'NPR 500 – 1,200'
        """
        def fmt(val):
            if val is None:
                return None
            # ensure Decimal with two decimal places
            q = Decimal(val).quantize(Decimal('0.01'))
            # if whole number, show without decimals
            if q == q.to_integral():
                return f"{int(q):,}"
            return f"{q:,.2f}"

        parts = []
        if self.price_min is not None and self.price_max is not None:
            return f"NPR {fmt(self.price_min)} – {fmt(self.price_max)}"
        if self.price_min is not None:
            return f"From NPR {fmt(self.price_min)}"
        if self.price_max is not None:
            return f"Up to NPR {fmt(self.price_max)}"
        # fallback to base_price
        return f"NPR {fmt(self.base_price)}"

    def __str__(self):
        return f"{self.name} - {self.get_price_display()}"


class Wishlist(models.Model):
    """
    Wishlist for services (can be extended for equipment/pharmacy)
    """
    # Use the project AUTH_USER_MODEL so Django can resolve the user model correctly
    from django.conf import settings

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='wishlisted_by')
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'wishlists'
        unique_together = ('user', 'service')
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.service.name}"