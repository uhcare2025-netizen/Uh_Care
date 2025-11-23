"""
Payments Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Payment
from .models import UserPaymentMethod
from django.contrib.admin import SimpleListFilter


class LinkedObjectFilter(SimpleListFilter):
    title = 'Linked to'
    parameter_name = 'linked'

    def lookups(self, request, model_admin):
        return (
            ('appointment', 'Service / Appointment'),
            ('pharmacy', 'Pharmacy Order'),
            ('purchase', 'Equipment Purchase'),
            ('rental', 'Equipment Rental'),
            ('unlinked', 'Unlinked'),
        )

    def queryset(self, request, queryset):
        from django.db.models import Q
        val = self.value()
        if val == 'appointment':
            # Include both legacy appointment and new service_booking
            return queryset.filter(Q(appointment__isnull=False) | Q(service_booking__isnull=False))
        if val == 'pharmacy':
            return queryset.filter(pharmacy_order__isnull=False)
        if val == 'purchase':
            return queryset.filter(equipment_purchase__isnull=False)
        if val == 'rental':
            return queryset.filter(equipment_rental__isnull=False)
        if val == 'unlinked':
            return queryset.filter(appointment__isnull=True, service_booking__isnull=True, pharmacy_order__isnull=True, equipment_purchase__isnull=True, equipment_rental__isnull=True)
        return queryset


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'patient_name', 'amount', 'payment_method', 
        'payment_status_badge', 'payment_date', 'created_at', 'linked_object'
    ]
    # Put our custom linked filter first for convenience
    list_filter = [LinkedObjectFilter, 'payment_status', 'payment_method', 'created_at', 'payment_date']
    search_fields = [
        'patient__email', 'patient__first_name', 'patient__last_name',
        'transaction_id', 'notes'
    ]
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'verified_at']
    raw_id_fields = ['patient', 'appointment', 'service_booking', 'verified_by', 'pharmacy_order', 'equipment_purchase', 'equipment_rental']
    
    # Include a preview field for uploaded payment proof (image URL)
    readonly_fields = readonly_fields + ['payment_proof_preview']

    fieldsets = (
        ('Payment Information', {
            'fields': ('patient', 'appointment', 'service_booking', 'pharmacy_order', 'equipment_purchase', 'equipment_rental', 'amount', 'payment_method', 'payment_status')
        }),
        ('Transaction Details', {
            'fields': ('transaction_id', 'payment_proof_preview', 'payment_proof_url', 'payment_date')
        }),
        ('Verification', {
            'fields': ('verified_by', 'verified_at')
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_at', 'updated_at')
        }),
    )

    # Use a custom change_list template to render quick-filter tabs
    change_list_template = 'admin/payments/payment/change_list.html'

    def get_list_display(self, request):
        """Return a list_display tailored to the selected LinkedObjectFilter.
        The SimpleListFilter uses the 'linked' parameter; if present, show a
        domain-specific column to make the list clearer for admins.
        """
        base = ['id', 'patient_name', 'amount', 'payment_method', 'payment_status_badge', 'payment_date', 'created_at']
        linked = request.GET.get('linked')
        if linked == 'appointment':
            return base + ['appointment_service', 'linked_object']
        if linked == 'pharmacy':
            return base + ['pharmacy_order_number', 'linked_object']
        if linked == 'purchase':
            return base + ['equipment_purchase_order_number', 'linked_object']
        if linked == 'rental':
            return base + ['equipment_rental_number', 'linked_object']
        # default: include linked_object as a helpful column
        return base + ['linked_object']

    def linked_object(self, obj):
        if obj.service_booking:
            return format_html('<a href="/admin/appointments/servicebooking/{}/change/">ServiceBooking #{}</a>', obj.service_booking.id, obj.service_booking.id)
        if obj.appointment:
            return format_html('<a href="/admin/appointments/appointment/{}/change/">Appointment #{}</a>', obj.appointment.id, obj.appointment.id)
        if obj.pharmacy_order:
            return format_html('<a href="/admin/pharmacy/pharmacyorder/{}/change/">Order #{}</a>', obj.pharmacy_order.id, obj.pharmacy_order.order_number)
        if obj.equipment_purchase:
            return format_html('<a href="/admin/equipment/equipmentpurchase/{}/change/">Purchase #{}</a>', obj.equipment_purchase.id, obj.equipment_purchase.order_number)
        if obj.equipment_rental:
            return format_html('<a href="/admin/equipment/equipmentrental/{}/change/">Rental #{}</a>', obj.equipment_rental.id, obj.equipment_rental.rental_number)
        return '-'
    linked_object.short_description = 'Linked'
    
    def patient_name(self, obj):
        return obj.patient.get_full_name()
    patient_name.short_description = 'Patient'

    # --- Per-type display helpers ---
    def appointment_service(self, obj):
        try:
            # Check both service_booking and appointment for service name
            if obj.service_booking:
                return obj.service_booking.service.name
            return obj.appointment.service.name
        except Exception:
            return '-'
    appointment_service.short_description = 'Service'

    def pharmacy_order_number(self, obj):
        if obj.pharmacy_order:
            return obj.pharmacy_order.order_number
        return '-'
    pharmacy_order_number.short_description = 'Order #'

    def equipment_purchase_order_number(self, obj):
        if obj.equipment_purchase:
            return obj.equipment_purchase.order_number
        return '-'
    equipment_purchase_order_number.short_description = 'Purchase #'

    def equipment_rental_number(self, obj):
        if obj.equipment_rental:
            return obj.equipment_rental.rental_number
        return '-'
    equipment_rental_number.short_description = 'Rental #'
    
    def payment_status_badge(self, obj):
        colors = {
            'unpaid': '#FF3B30',
            'paid': '#34C759',
            'refunded': '#FF9500',
            'partial': '#007AFF',
        }
        color = colors.get(obj.payment_status, '#8E8E93')
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            color,
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = 'Payment Status'
    
    actions = ['mark_as_paid', 'mark_as_unpaid']
    
    def mark_as_paid(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(payment_status='unpaid').update(
            payment_status='paid',
            verified_by=request.user,
            verified_at=timezone.now(),
            payment_date=timezone.now()
        )
        self.message_user(request, f'{count} payment(s) marked as paid.')
    mark_as_paid.short_description = 'Mark selected as Paid'
    
    def mark_as_unpaid(self, request, queryset):
        count = queryset.exclude(payment_status='refunded').update(
            payment_status='unpaid',
            verified_by=None,
            verified_at=None
        )
        self.message_user(request, f'{count} payment(s) marked as unpaid.')
    mark_as_unpaid.short_description = 'Mark selected as Unpaid'

    def payment_proof_preview(self, obj):
        """Render an inline image preview for payment proof URLs in the admin change view."""
        # Prefer uploaded file if present
        if getattr(obj, 'payment_proof_file', None):
            try:
                url = obj.payment_proof_file.url
                return format_html(
                    '<a href="{}" target="_blank"><img src="{}" style="max-width:520px; max-height:360px; object-fit:contain; border:1px solid #eee; padding:4px; background:#fff;" /></a>',
                    url, url
                )
            except Exception:
                pass

        if obj.payment_proof_url:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" style="max-width:520px; max-height:360px; object-fit:contain; border:1px solid #eee; padding:4px; background:#fff;" /></a>',
                obj.payment_proof_url
            )

        return "No proof uploaded"
    payment_proof_preview.short_description = 'Payment proof'
    payment_proof_preview.short_description = 'Payment proof'

    def save_model(self, request, obj, form, change):
        """
        Allow staff/admin users to intentionally override the payment_method
        immutability enforced on the model by setting a temporary flag on the
        instance before saving.
        """
        if change and 'payment_method' in getattr(form, 'changed_data', []):
            # mark instance to allow the change in the model.save() hook
            obj._allow_payment_method_change = True
        super().save_model(request, obj, form, change)


@admin.register(UserPaymentMethod)
class UserPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_name', 'method', 'is_default', 'created_at']
    list_filter = ['method', 'is_default', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at']

    def user_name(self, obj):
        return obj.user.get_full_name()
    user_name.short_description = 'User'