from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from apps.appointments.models import ServiceBooking
from apps.pharmacy.models import PharmacyOrder
from apps.equipment.models import EquipmentRental, EquipmentPurchase
from apps.payments.models import Payment
from .services import NotificationService


@receiver(post_save, sender=ServiceBooking)
def servicebooking_notification(sender, instance, created, **kwargs):
    """
    Send notifications for service booking events (new ServiceBooking model)
    """
    if created:
        NotificationService.send_notification(
            user=instance.patient,
            notification_type='appointment_booked',
            title='Service Booked Successfully',
            message=f'Your service booking for {instance.service.name} has been booked for {instance.appointment_date}.',
            related_object=instance,
            action_url=f'/appointments/detail/{instance.id}/',
            send_email=True,
            send_sms=True
        )
    else:
        if instance.status == 'confirmed' and instance.provider:
            NotificationService.send_notification(
                user=instance.patient,
                notification_type='appointment_confirmed',
                title='Service Booking Confirmed',
                message=f'Your service booking has been confirmed. Provider: {instance.provider.get_full_name()}',
                related_object=instance,
                action_url=f'/appointments/detail/{instance.id}/',
                send_email=True,
                send_sms=True
            )

            NotificationService.send_notification(
                user=instance.provider,
                notification_type='appointment_confirmed',
                title='New Service Booking Assigned',
                message=f'New service booking assigned: {instance.service.name} on {instance.appointment_date}',
                related_object=instance,
                action_url=f'/appointments/detail/{instance.id}/',
                send_email=True
            )

        elif instance.status == 'cancelled':
            NotificationService.send_notification(
                user=instance.patient,
                notification_type='appointment_cancelled',
                title='Service Booking Cancelled',
                message=f'Your service booking for {instance.service.name} has been cancelled.',
                related_object=instance,
                action_url=f'/appointments/detail/{instance.id}/',
                send_email=True,
                send_sms=True
            )
            if instance.provider:
                NotificationService.send_notification(
                    user=instance.provider,
                    notification_type='appointment_cancelled',
                    title='Service Booking Cancelled',
                    message=f'Service booking cancelled: {instance.service.name}',
                    related_object=instance,
                    action_url=f'/appointments/detail/{instance.id}/'
                )

        elif instance.status == 'completed':
            NotificationService.send_notification(
                user=instance.patient,
                notification_type='appointment_completed',
                title='Service Completed',
                message=f'Your service booking for {instance.service.name} has been completed. Thank you!',
                related_object=instance,
                action_url=f'/appointments/detail/{instance.id}/',
                send_email=True
            )


@receiver(post_save, sender=PharmacyOrder)
def pharmacy_order_notification(sender, instance, created, **kwargs):
    """
    Send notifications for pharmacy orders
    """
    if created:
        NotificationService.send_notification(
            user=instance.customer,
            notification_type='order_placed',
            title='Pharmacy Order Placed',
            message=f'Your order #{instance.order_number} has been placed. Total: रू {instance.total_amount}',
            related_object=instance,
            action_url=f'/pharmacy/order/{instance.order_number}/',
            send_email=True,
            send_sms=True
        )
    else:
        if instance.status == 'confirmed':
            NotificationService.send_notification(
                user=instance.customer,
                notification_type='order_confirmed',
                title='Order Confirmed',
                message=f'Your order #{instance.order_number} has been confirmed and is being processed.',
                related_object=instance,
                action_url=f'/pharmacy/order/{instance.order_number}/',
                send_email=True,
                send_sms=True
            )
        
        elif instance.status == 'out_for_delivery':
            NotificationService.send_notification(
                user=instance.customer,
                notification_type='order_shipped',
                title='Order Out for Delivery',
                message=f'Your order #{instance.order_number} is out for delivery!',
                related_object=instance,
                action_url=f'/pharmacy/order/{instance.order_number}/',
                send_sms=True
            )
        
        elif instance.status == 'delivered':
            NotificationService.send_notification(
                user=instance.customer,
                notification_type='order_delivered',
                title='Order Delivered',
                message=f'Your order #{instance.order_number} has been delivered. Thank you for shopping with UH Care!',
                related_object=instance,
                action_url=f'/pharmacy/order/{instance.order_number}/',
                send_email=True
            )


@receiver(post_save, sender=EquipmentRental)
def equipment_rental_notification(sender, instance, created, **kwargs):
    """
    Send notifications for equipment rentals
    """
    if created:
        NotificationService.send_notification(
            user=instance.customer,
            notification_type='rental_started',
            title='Equipment Rental Confirmed',
            message=f'Your rental for {instance.equipment.name} has been confirmed. Rental period: {instance.start_date} to {instance.end_date}',
            related_object=instance,
            action_url='/equipment/my-rentals/',
            send_email=True,
            send_sms=True
        )


@receiver(post_save, sender=Payment)
def payment_notification(sender, instance, created, **kwargs):
    """
    Send notifications for payments
    """
    if not created and getattr(instance, 'payment_status', '') == 'paid':
        NotificationService.send_notification(
            user=instance.patient,
            notification_type='payment_received',
            title='Payment Confirmed',
            message=f'Your payment of रू {instance.amount} has been confirmed. Thank you!',
            related_object=instance,
            action_url='/payments/history/',
            send_email=True,
            send_sms=True
        )
