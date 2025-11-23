from django.db import migrations


def copy_appointments_to_servicebookings(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    ServiceBooking = apps.get_model('appointments', 'ServiceBooking')
    # Iterate and copy rows. Use bulk_create in batches for performance.
    to_create = []
    batch_size = 200
    for a in Appointment.objects.all().iterator():
        sb = ServiceBooking(
            id=a.id,
            patient_id=a.patient_id,
            provider_id=a.provider_id,
            service_id=a.service_id,
            appointment_date=a.appointment_date,
            appointment_time=a.appointment_time,
            duration_hours=a.duration_hours,
            service_address=a.service_address,
            service_price=a.service_price,
            additional_charges=a.additional_charges,
            final_price=a.final_price,
            total_amount=a.total_amount,
            status=a.status,
            patient_notes=a.patient_notes,
            provider_notes=a.provider_notes,
            cancellation_reason=a.cancellation_reason,
            created_at=a.created_at,
            updated_at=a.updated_at,
            confirmed_at=a.confirmed_at,
            completed_at=a.completed_at,
        )
        to_create.append(sb)
        if len(to_create) >= batch_size:
            ServiceBooking.objects.bulk_create(to_create)
            to_create = []
    if to_create:
        ServiceBooking.objects.bulk_create(to_create)


def noop_reverse(apps, schema_editor):
    # Do not delete data on reverse automatically. Manual rollback procedure recommended.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0004_create_servicebooking'),
    ]

    operations = [
        migrations.RunPython(copy_appointments_to_servicebookings, reverse_code=noop_reverse),
    ]
