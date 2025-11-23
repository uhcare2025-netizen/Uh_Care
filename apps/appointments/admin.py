"""
Appointments Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import ServiceBooking
from .models import (
    PersonalAppointment,
    ProviderSchedule,
    AppointmentReview,
)


# Note: ProviderAvailability model is intentionally not registered in admin
# to avoid duplicate/confusing admin entries. Use `ProviderSchedule` for
# managing provider working hours and slot configuration.
    


@admin.register(ProviderSchedule)
class ProviderScheduleAdmin(admin.ModelAdmin):
    list_display = ['provider', 'day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_available']
    list_filter = ['day_of_week', 'is_available']
    search_fields = ['provider__email', 'provider__first_name', 'provider__last_name']
    ordering = ['provider', 'day_of_week', 'start_time']
    list_editable = ['is_available', 'slot_duration']
    
    fieldsets = (
        ('Provider', {
            'fields': ('provider',)
        }),
        ('Schedule', {
            'fields': ('day_of_week', 'start_time', 'end_time', 'slot_duration')
        }),
        ('Availability', {
            'fields': ('is_available',)
        }),
    )


@admin.register(PersonalAppointment)
class PersonalAppointmentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'patient_name', 'provider_name', 'appointment_type',
        'appointment_date', 'appointment_time', 'location_type', 'patient_phone',
        'status_badge', 'total_fee'
    ]
    list_filter = ['status', 'appointment_type', 'location_type', 'appointment_date']
    search_fields = [
        'patient__email', 'patient__first_name', 'patient__last_name',
        'provider__email', 'provider__first_name', 'provider__last_name',
        'reason', 'symptoms'
    ]
    readonly_fields = ['created_at', 'updated_at', 'confirmed_at', 'completed_at', 'total_fee']
    date_hierarchy = 'appointment_date'
    
    fieldsets = (
        ('Participants', {
            'fields': ('patient', 'provider')
        }),
        ('Appointment Details', {
            'fields': ('appointment_type', 'appointment_date', 'appointment_time', 'duration_minutes', 'patient_phone')
        }),
        ('Location', {
            'fields': ('location_type', 'location_address', 'video_link')
        }),
        ('Medical Information', {
            'fields': ('reason', 'symptoms', 'patient_notes', 'provider_notes', 'diagnosis', 'prescription')
        }),
        ('Fees', {
            'fields': ('consultation_fee', 'additional_charges', 'total_fee')
        }),
        ('Status', {
            'fields': ('status', 'cancellation_reason', 'cancelled_at')
        }),
        ('Reminders', {
            'fields': ('reminder_sent', 'reminder_sent_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'confirmed_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def patient_name(self, obj):
        return obj.patient.get_full_name()
    patient_name.short_description = 'Patient'
    
    def provider_name(self, obj):
        return obj.provider.get_full_name()
    provider_name.short_description = 'Provider'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#FF9500',
            'confirmed': '#007AFF',
            'in_progress': '#5856D6',
            'completed': '#34C759',
            'cancelled_by_patient': '#8E8E93',
            'cancelled_by_provider': '#FF3B30',
            'no_show': '#FF3B30',
        }
        color = colors.get(obj.status, '#8E8E93')
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    actions = ['mark_as_confirmed', 'mark_as_completed', 'mark_as_cancelled']
    
    def mark_as_confirmed(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='pending').update(
            status='confirmed',
            confirmed_at=timezone.now()
        )
        self.message_user(request, f'{count} appointment(s) confirmed.')
    mark_as_confirmed.short_description = 'Confirm selected appointments'
    
    def mark_as_completed(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status__in=['confirmed', 'in_progress']).update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f'{count} appointment(s) completed.')
    mark_as_completed.short_description = 'Mark as completed'
    
    def mark_as_cancelled(self, request, queryset):
        count = queryset.exclude(status='completed').update(
            status='cancelled_by_patient'
        )
        self.message_user(request, f'{count} appointment(s) cancelled.')
    mark_as_cancelled.short_description = 'Cancel selected appointments'


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'patient_name', 'provider_name', 'service', 
        'appointment_date', 'appointment_time', 'status_badge', 'service_price', 'final_price', 'total_amount'
    ]
    list_filter = ['status', 'appointment_date', 'created_at']
    search_fields = [
        'patient__email', 'patient__first_name', 'patient__last_name',
        'provider__first_name', 'provider__last_name', 'service__name'
    ]
    ordering = ['-appointment_date', '-appointment_time']
    readonly_fields = ['created_at', 'updated_at', 'confirmed_at', 'completed_at']
    raw_id_fields = ['patient', 'provider', 'service']
    
    fieldsets = (
        ('Service Booking Details', {
            'fields': ('patient', 'provider', 'service', 'status')
        }),
        ('Schedule', {
            'fields': ('appointment_date', 'appointment_time', 'duration_hours', 'service_address')
        }),
        ('Pricing', {
            'fields': ('service_price', 'final_price', 'additional_charges', 'total_amount')
        }),
        ('Notes', {
            'fields': ('patient_notes', 'provider_notes', 'cancellation_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'confirmed_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def patient_name(self, obj):
        return obj.patient.get_full_name()
    patient_name.short_description = 'Patient'
    
    def provider_name(self, obj):
        return obj.provider.get_full_name() if obj.provider else 'Unassigned'
    provider_name.short_description = 'Provider'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#FF9500',
            'confirmed': '#007AFF',
            'in_progress': '#5856D6',
            'completed': '#34C759',
            'cancelled': '#8E8E93',
            'rejected': '#FF3B30',
        }
        color = colors.get(obj.status, '#8E8E93')
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    actions = ['mark_as_confirmed', 'mark_as_completed', 'mark_as_cancelled']
    
    def mark_as_confirmed(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='pending').update(
            status='confirmed',
            confirmed_at=timezone.now()
        )
        self.message_user(request, f'{count} service booking(s) marked as confirmed.')
    mark_as_confirmed.short_description = 'Mark selected as Confirmed'
    
    def mark_as_completed(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status__in=['confirmed', 'in_progress']).update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f'{count} service booking(s) marked as completed.')
    mark_as_completed.short_description = 'Mark selected as Completed'
    
    def mark_as_cancelled(self, request, queryset):
        count = queryset.exclude(status__in=['completed']).update(
            status='cancelled'
        )
        self.message_user(request, f'{count} service booking(s) cancelled.')
    mark_as_cancelled.short_description = 'Cancel selected service bookings'

    def save_model(self, request, obj, form, change):
        if change:
            setattr(obj, '_allow_modification', True)
        super().save_model(request, obj, form, change)


@admin.register(AppointmentReview)
class AppointmentReviewAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'appointment', 'rating_display', 'patient_name',
        'provider_name', 'would_recommend', 'created_at'
    ]
    list_filter = ['rating', 'would_recommend', 'created_at']
    search_fields = [
        'appointment__patient__email',
        'appointment__provider__email',
        'review_text'
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Review Details', {
            'fields': ('appointment', 'rating', 'review_text', 'would_recommend')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def patient_name(self, obj):
        return obj.appointment.patient.get_full_name()
    patient_name.short_description = 'Patient'
    
    def provider_name(self, obj):
        return obj.appointment.provider.get_full_name()
    provider_name.short_description = 'Provider'
    
    def rating_display(self, obj):
        stars = '⭐' * obj.rating
        return format_html(
            '<span style="font-size: 16px;">{}</span>',
            stars
        )
    rating_display.short_description = 'Rating'