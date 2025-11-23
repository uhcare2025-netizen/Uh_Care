from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from apps.accounts.models import User, PatientProfile, ProviderProfile
from apps.appointments.models import ServiceBooking
from apps.payments.models import Payment
from apps.services.models import Service, ServiceCategory


class DashboardViewsTestCase(TestCase):
    def setUp(self):
        # Create a patient user
        self.patient = User.objects.create_user(username='patient1', password='pass', role='patient', first_name='Pat', last_name='Ent')
        PatientProfile.objects.create(user=self.patient, total_balance=Decimal('100.00'))

        # Create a provider user
        self.provider = User.objects.create_user(username='provider1', password='pass', role='provider', first_name='Prov', last_name='Ider')
        ProviderProfile.objects.create(user=self.provider, specialization='nursing', license_number='LIC123', hourly_rate=Decimal('500.00'))

        # Create an admin/staff user
        self.admin = User.objects.create_user(username='admin1', password='pass', role='admin', is_staff=True, first_name='Ad', last_name='Min')

        # Create a service and an appointment for some context
        cat = ServiceCategory.objects.create(name='Nursing')
        self.service = Service.objects.create(
            name='Test Service',
            category=cat,
            slug='test-service',
            description='Test service description',
            short_description='Short desc',
            base_price=Decimal('1200.00'),
            duration_unit='session',
            what_included='Care',
        )

        # Marketplace ServiceBooking for provider and patient
        self.service_booking = ServiceBooking.objects.create(
            patient=self.patient,
            provider=self.provider,
            service=self.service,
            appointment_date=timezone.now().date(),
            appointment_time=timezone.now().time(),
            duration_hours=Decimal('1.0'),
            status='confirmed',
            service_price=self.service.base_price,
            additional_charges=Decimal('0.00'),
            total_amount=self.service.base_price,
            service_address='Patient home address'
        )

        # Payment record linked to the new service_booking
        Payment.objects.create(
            service_booking=self.service_booking,
            patient=self.patient,
            amount=Decimal('1200.00'),
            payment_status='paid'
        )

    def test_patient_dashboard_renders(self):
        self.client.login(username='patient1', password='pass')
        url = reverse('dashboard:patient')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Ensure stats present
        self.assertIn('stats', resp.context)
        self.assertIn('upcoming_appointments', resp.context)

    def test_provider_dashboard_renders_and_context_keys(self):
        self.client.login(username='provider1', password='pass')
        url = reverse('dashboard:provider')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Check new keys added for template compatibility
        self.assertIn('today_appointments_count', resp.context)
        self.assertIn('pending_count', resp.context)
        self.assertIn('earnings_month', resp.context)

    def test_admin_dashboard_renders_and_stats_aliases(self):
        self.client.login(username='admin1', password='pass')
        url = reverse('dashboard:admin')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Ensure stats alias keys exist
        self.assertIn('stats', resp.context)
        stats = resp.context['stats']
        self.assertIn('users_count', stats)
        self.assertIn('services_count', stats)
        self.assertIn('pending_payments_total', stats)
        # recent_activity should be a list
        self.assertIn('recent_activity', resp.context)
        self.assertIsInstance(resp.context['recent_activity'], list)
