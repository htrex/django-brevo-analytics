from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.management import call_command
from datetime import datetime
from io import StringIO
from .models import BrevoMessage, BrevoEmail

class BrevoModelsTestCase(TestCase):
    def setUp(self):
        self.message = BrevoMessage.objects.create(
            subject="Test Email",
            sent_date=timezone.now().date()
        )

    def test_email_creation(self):
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test123@example.com>",
            recipient_email="test@example.com",
            sent_at=timezone.now()
        )
        self.assertEqual(email.current_status, 'sent')

    def test_add_event(self):
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test456@example.com>",
            recipient_email="test2@example.com",
            sent_at=timezone.now()
        )

        email.add_event('delivered', timezone.now())
        self.assertEqual(email.current_status, 'delivered')
        self.assertEqual(len(email.events), 1)

    def test_status_hierarchy(self):
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test789@example.com>",
            recipient_email="test3@example.com",
            sent_at=timezone.now()
        )

        email.add_event('delivered', timezone.now())
        email.add_event('opened', timezone.now())
        email.add_event('clicked', timezone.now())

        self.assertEqual(email.current_status, 'clicked')

    def test_message_stats_update(self):
        # Create multiple emails for the message
        for i in range(5):
            email = BrevoEmail.objects.create(
                message=self.message,
                brevo_message_id=f"<test{i}@example.com>",
                recipient_email=f"test{i}@example.com",
                sent_at=timezone.now()
            )
            # Add 'sent' event first (required for total_sent count)
            email.add_event('sent', timezone.now())
            if i < 3:
                email.add_event('delivered', timezone.now())
            if i < 2:
                email.add_event('opened', timezone.now())

        # Manually update stats after all emails created
        self.message.update_stats()

        # Refresh message from DB
        self.message.refresh_from_db()

        self.assertEqual(self.message.total_sent, 5)
        self.assertEqual(self.message.total_delivered, 3)
        self.assertEqual(self.message.total_opened, 2)
        self.assertEqual(self.message.delivery_rate, 60.0)

    def test_duplicate_event_prevention(self):
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<testdup@example.com>",
            recipient_email="testdup@example.com",
            sent_at=timezone.now()
        )

        timestamp = timezone.now()
        added1 = email.add_event('delivered', timestamp)
        added2 = email.add_event('delivered', timestamp)

        self.assertTrue(added1)
        self.assertFalse(added2)  # Should not add duplicate
        self.assertEqual(len(email.events), 1)


class BlacklistOnlyModeTestCase(TestCase):
    """Tests for BLACKLIST_ONLY_MODE configuration flag"""

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True})
    def test_webhook_disabled_in_blacklist_only_mode(self):
        """Webhook should return 404 with message in blacklist-only mode"""
        # Webhook is @csrf_exempt so no CSRF token needed
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data='{"event": "delivered", "email": "test@example.com"}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data['status'], 'disabled')
        self.assertIn('BLACKLIST_ONLY_MODE', data['message'])

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True})
    def test_import_disabled_in_blacklist_only_mode(self):
        """Import command should exit with error in blacklist-only mode"""
        out = StringIO()
        call_command('import_brevo_logs', 'test.csv', stdout=out)
        output = out.getvalue()
        self.assertIn('disabled', output.lower())
        self.assertIn('BLACKLIST_ONLY_MODE', output)

    @override_settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': False})
    def test_webhook_enabled_when_mode_disabled(self):
        """Webhook should work normally when blacklist-only mode is disabled"""
        # Webhook is @csrf_exempt so no CSRF token needed
        # This should not return 404 (will fail for other reasons like missing fields, but not 404)
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data='{}',
            content_type='application/json'
        )
        # Should get 400 (bad request) not 404 (disabled)
        self.assertNotEqual(response.status_code, 404)
