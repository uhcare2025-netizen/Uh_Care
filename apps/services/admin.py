"""
Services Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import ServiceCategory, Service, Wishlist


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'display_order', 'service_count']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    ordering = ['display_order', 'name']
    # ServiceCategory model does not have a slug field. Remove prepopulated_fields.
    
    def service_count(self, obj):
        count = obj.services.count()
        return format_html(
            '<a href="{}?category__id__exact={}">{} services</a>',
            reverse('admin:services_service_changelist'),
            obj.id,
            count
        )
    service_count.short_description = 'Services'


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price_range_display', 'duration_unit', 'security_deposit_display', 'is_active', 'is_featured', 'total_bookings']
    list_filter = ['category', 'is_active', 'is_featured', 'requires_security_deposit', 'created_at']
    search_fields = ['name', 'description', 'short_description']
    ordering = ['-is_featured', '-created_at']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['total_bookings', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'category', 'short_description', 'description')
        }),
        ('Pricing', {
            'fields': ('base_price', 'price_min', 'price_max', 'duration_unit')
        }),
        ('Security Deposit', {
            'fields': ('requires_security_deposit', 'security_deposit_amount', 'security_deposit_description'),
            'description': 'Configure security deposit requirements for this service. Security deposits are refundable after service completion.'
        }),
        ('Details', {
            'fields': ('what_included', 'requirements', 'image', 'image_url')
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured')
        }),
        ('Statistics', {
            'fields': ('total_bookings', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def price_range_display(self, obj):
        return obj.get_price_display()
    price_range_display.short_description = 'Price'
    
    def security_deposit_display(self, obj):
        if obj.requires_security_deposit:
            return format_html(
                '<span style="color: #009e4d; font-weight: bold;">रु {}</span>',
                f"{obj.security_deposit_amount:,.2f}"
            )
        return format_html('<span style="color: #6b7280;">None</span>')
    security_deposit_display.short_description = 'Security Deposit'


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['user', 'service', 'added_at']
    list_filter = ['added_at']
    search_fields = ['user__email', 'user__first_name', 'service__name']
    ordering = ['-added_at']
    raw_id_fields = ['user', 'service']