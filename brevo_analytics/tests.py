import json
import time

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.management import call_command
from datetime import datetime
from io import StringIO
from .models import BrevoMessage, BrevoEmail
from .sender_utils import (
    get_allowed_senders,
    is_sender_allowed,
    build_sender_filter_q,
    build_sender_sql_clause,
)

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

    def test_email_tags_default(self):
        """BrevoEmail.tags should default to an empty list"""
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test_tags@example.com>",
            recipient_email="tags@example.com",
            sent_at=timezone.now()
        )
        self.assertIsInstance(email.tags, list)
        self.assertEqual(email.tags, [])

    def test_email_tags_stored(self):
        """BrevoEmail.tags should store and retrieve tag arrays"""
        tags = ["digest:42:Esito CDM 2024-09-17", "customer:15:Acme Corp"]
        email = BrevoEmail.objects.create(
            message=self.message,
            brevo_message_id="<test_tags2@example.com>",
            recipient_email="tags2@example.com",
            sent_at=timezone.now(),
            tags=tags
        )
        email.refresh_from_db()
        self.assertEqual(email.tags, tags)


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


class WebhookTagTestCase(TestCase):
    """Tests for tag extraction, storage, and tag-based grouping in webhook"""

    def _post_webhook(self, payload):
        """Helper to post a webhook payload"""
        return self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json'
        )

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_saves_tags_on_email(self):
        """Webhook should save tags from payload onto BrevoEmail.tags"""
        payload = {
            'event': 'request',
            'message-id': '<tag-test-001@example.com>',
            'email': 'recipient@example.com',
            'subject': 'Esito CDM 2024-09-17 - Acme Corp',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM 2024-09-17', 'customer:15:Acme Corp'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-test-001@example.com>',
            recipient_email='recipient@example.com'
        )
        self.assertEqual(email.tags, ['digest:42:Esito CDM 2024-09-17', 'customer:15:Acme Corp'])

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_saves_empty_tags_when_absent(self):
        """Webhook should save empty list when no tags in payload"""
        payload = {
            'event': 'request',
            'message-id': '<tag-test-002@example.com>',
            'email': 'recipient2@example.com',
            'subject': 'No tags email',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-test-002@example.com>',
            recipient_email='recipient2@example.com'
        )
        self.assertEqual(email.tags, [])

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_uses_tag_as_subject(self):
        """When MESSAGE_GROUP_BY='tag', matching tag should be used as BrevoMessage.subject"""
        payload = {
            'event': 'request',
            'message-id': '<tag-group-001@example.com>',
            'email': 'client1@example.com',
            'subject': 'Esito CDM 2024-09-17 - Acme Corp',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM 2024-09-17', 'customer:15:Acme Corp'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-group-001@example.com>',
            recipient_email='client1@example.com'
        )
        self.assertEqual(email.message.subject, 'Esito CDM 2024-09-17')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_aggregates_recipients(self):
        """Multiple recipients with same tag should share one BrevoMessage"""
        ts = int(time.time())

        for i, client_name in enumerate(['Acme Corp', 'Beta Ltd', 'Gamma Inc']):
            payload = {
                'event': 'request',
                'message-id': f'<tag-agg-{i:03d}@example.com>',
                'email': f'client{i}@example.com',
                'subject': f'Esito CDM 2024-09-17 - {client_name}',
                'ts_event': ts,
                'sender': 'noreply@example.com',
                'tags': ['digest:42:Esito CDM 2024-09-17', f'customer:{i}:{client_name}'],
            }
            self._post_webhook(payload)

        messages = BrevoMessage.objects.filter(subject='Esito CDM 2024-09-17')
        self.assertEqual(messages.count(), 1)
        self.assertEqual(messages.first().emails.count(), 3)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_grouping_fallback_to_subject(self):
        """When no tag matches the prefix, fall back to email subject"""
        payload = {
            'event': 'request',
            'message-id': '<tag-fallback-001@example.com>',
            'email': 'nontag@example.com',
            'subject': 'Password reset',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['transactional:password_reset'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-fallback-001@example.com>',
            recipient_email='nontag@example.com'
        )
        self.assertEqual(email.message.subject, 'Password reset')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_default_subject_grouping_unchanged(self):
        """Default behaviour (no MESSAGE_GROUP_BY) should use email subject"""
        payload = {
            'event': 'request',
            'message-id': '<default-group-001@example.com>',
            'email': 'default@example.com',
            'subject': 'Esito CDM 2024-09-17 - Acme Corp',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM 2024-09-17'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<default-group-001@example.com>',
            recipient_email='default@example.com'
        )
        self.assertEqual(email.message.subject, 'Esito CDM 2024-09-17 - Acme Corp')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_subject_with_colons(self):
        """Tag extraction should handle colons in the subject correctly"""
        payload = {
            'event': 'request',
            'message-id': '<tag-colon-001@example.com>',
            'email': 'colon@example.com',
            'subject': 'Esito CDM: riunione del 18 febbraio - Acme',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:42:Esito CDM: riunione del 18 febbraio', 'customer:15:Acme'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-colon-001@example.com>',
            recipient_email='colon@example.com'
        )
        self.assertEqual(email.message.subject, 'Esito CDM: riunione del 18 febbraio')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_webhook_tag_without_id(self):
        """Tag with prefix but no id:subject structure should use remainder as subject"""
        payload = {
            'event': 'request',
            'message-id': '<tag-noid-001@example.com>',
            'email': 'noid@example.com',
            'subject': 'Some email subject',
            'ts_event': int(time.time()),
            'sender': 'noreply@example.com',
            'tags': ['digest:Standalone title'],
        }
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        email = BrevoEmail.objects.get(
            brevo_message_id='<tag-noid-001@example.com>',
            recipient_email='noid@example.com'
        )
        # No colon after prefix removal → uses the remainder as-is
        self.assertEqual(email.message.subject, 'Standalone title')


class DisplaySubjectTestCase(TestCase):
    """Tests for display_subject computed field in serializers"""

    @override_settings(BREVO_ANALYTICS={
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_display_subject_strips_prefix_and_id(self):
        """display_subject should strip '{prefix}:{id}:' from tag-based subjects"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='digest:42:Esito CDM 2024-09-17',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Esito CDM 2024-09-17')

    @override_settings(BREVO_ANALYTICS={
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_display_subject_non_tag_subject_unchanged(self):
        """display_subject should return subject unchanged if it doesn't match the prefix"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='Password reset notification',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Password reset notification')

    @override_settings(BREVO_ANALYTICS={})
    def test_display_subject_in_default_mode_equals_subject(self):
        """In default subject grouping mode, display_subject == subject"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='Normal subject line',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Normal subject line')

    @override_settings(BREVO_ANALYTICS={
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_display_subject_with_colons_in_title(self):
        """display_subject should handle titles containing colons"""
        from brevo_analytics.serializers import BrevoMessageSerializer
        message = BrevoMessage.objects.create(
            subject='digest:42:Esito CDM: seduta del 17/09',
            sent_date=timezone.now().date()
        )
        serializer = BrevoMessageSerializer(message)
        self.assertEqual(serializer.data['display_subject'], 'Esito CDM: seduta del 17/09')


class ImportTagTestCase(TestCase):
    """Tests for tag support in CSV import command"""

    def _create_csv(self, rows):
        """Create a temporary CSV file with the given rows.

        Each row is a dict with keys: st_text, ts, sub, frm, email, tag, mid, link
        """
        import csv
        import os
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='')
        writer = csv.DictWriter(f, fieldnames=['st_text', 'ts', 'sub', 'frm', 'email', 'tag', 'mid', 'link'])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        f.close()
        return f.name

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_import_stores_tag_on_email(self):
        """CSV import should store the tag column value in BrevoEmail.tags"""
        import os
        csv_path = self._create_csv([
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00',
                'sub': 'Esito CDM - Acme', 'frm': 'noreply@example.com',
                'email': 'acme@example.com', 'tag': 'digest:42:Esito CDM 2024-09-17',
                'mid': '<import-tag-001@example.com>', 'link': '',
            },
        ])
        try:
            call_command('import_brevo_logs', csv_path, stdout=StringIO())
            email = BrevoEmail.objects.get(
                brevo_message_id='import-tag-001@example.com',
                recipient_email='acme@example.com'
            )
            self.assertEqual(email.tags, ['digest:42:Esito CDM 2024-09-17'])
        finally:
            os.unlink(csv_path)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_import_tag_grouping(self):
        """CSV import with MESSAGE_GROUP_BY='tag' should group by matching tag"""
        import os
        csv_path = self._create_csv([
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00',
                'sub': 'Esito CDM - Acme', 'frm': 'noreply@example.com',
                'email': 'acme@example.com', 'tag': 'digest:42:Esito CDM 2024-09-17',
                'mid': '<import-grp-001@example.com>', 'link': '',
            },
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:01:00',
                'sub': 'Esito CDM - Beta', 'frm': 'noreply@example.com',
                'email': 'beta@example.com', 'tag': 'digest:42:Esito CDM 2024-09-17',
                'mid': '<import-grp-002@example.com>', 'link': '',
            },
        ])
        try:
            call_command('import_brevo_logs', csv_path, stdout=StringIO())
            messages = BrevoMessage.objects.filter(subject='Esito CDM 2024-09-17')
            self.assertEqual(messages.count(), 1)
            self.assertEqual(messages.first().emails.count(), 2)
        finally:
            os.unlink(csv_path)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['noreply@example.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
        'MESSAGE_GROUP_BY': 'tag',
        'MESSAGE_TAG_PREFIX': 'digest',
    })
    def test_import_tag_grouping_fallback(self):
        """CSV import with tag grouping should fall back to subject when no matching tag"""
        import os
        csv_path = self._create_csv([
            {
                'st_text': 'Inviata', 'ts': '17-09-2024 10:00:00',
                'sub': 'Password reset', 'frm': 'noreply@example.com',
                'email': 'user@example.com', 'tag': '',
                'mid': '<import-fb-001@example.com>', 'link': '',
            },
        ])
        try:
            call_command('import_brevo_logs', csv_path, stdout=StringIO())
            email = BrevoEmail.objects.get(
                brevo_message_id='import-fb-001@example.com',
                recipient_email='user@example.com'
            )
            self.assertEqual(email.message.subject, 'Password reset')
        finally:
            os.unlink(csv_path)


class AllowedSenderMatchingTestCase(TestCase):
    """Tests for domain-based and exact ALLOWED_SENDERS matching"""

    # ── Unit: is_sender_allowed ──

    def test_exact_match(self):
        self.assertTrue(is_sender_allowed('info@example.com', ['info@example.com']))

    def test_exact_match_case_insensitive(self):
        self.assertTrue(is_sender_allowed('Info@Example.COM', ['info@example.com']))

    def test_exact_no_match(self):
        self.assertFalse(is_sender_allowed('other@example.com', ['info@example.com']))

    def test_domain_match(self):
        self.assertTrue(is_sender_allowed('alice@company.com', ['@company.com']))

    def test_domain_match_case_insensitive(self):
        self.assertTrue(is_sender_allowed('Alice@COMPANY.COM', ['@company.com']))

    def test_domain_no_match(self):
        self.assertFalse(is_sender_allowed('alice@other.com', ['@company.com']))

    def test_mixed_list_exact_hit(self):
        allowed = ['info@example.com', '@company.com']
        self.assertTrue(is_sender_allowed('info@example.com', allowed))

    def test_mixed_list_domain_hit(self):
        allowed = ['info@example.com', '@company.com']
        self.assertTrue(is_sender_allowed('bob@company.com', allowed))

    def test_mixed_list_no_match(self):
        allowed = ['info@example.com', '@company.com']
        self.assertFalse(is_sender_allowed('bob@other.com', allowed))

    def test_empty_list_allows_all(self):
        self.assertTrue(is_sender_allowed('anyone@anywhere.com', []))

    def test_none_sender_denied(self):
        self.assertFalse(is_sender_allowed(None, ['@company.com']))

    def test_empty_sender_denied(self):
        self.assertFalse(is_sender_allowed('', ['@company.com']))

    # ── Unit: get_allowed_senders ──

    @override_settings(BREVO_ANALYTICS={'ALLOWED_SENDERS': ['a@b.com', '@c.com']})
    def test_get_allowed_senders_list(self):
        self.assertEqual(get_allowed_senders(), ['a@b.com', '@c.com'])

    @override_settings(BREVO_ANALYTICS={'ALLOWED_SENDERS': 'single@b.com'})
    def test_get_allowed_senders_string_wrapped(self):
        self.assertEqual(get_allowed_senders(), ['single@b.com'])

    @override_settings(BREVO_ANALYTICS={})
    def test_get_allowed_senders_empty_default(self):
        self.assertEqual(get_allowed_senders(), [])

    # ── Unit: build_sender_filter_q ──

    def test_filter_q_empty_list(self):
        from django.db.models import Q
        self.assertEqual(str(build_sender_filter_q([])), str(Q()))

    def test_filter_q_exact_email(self):
        q = build_sender_filter_q(['info@example.com'])
        # Should contain iexact lookup and isnull
        q_str = str(q)
        self.assertIn('sender_email__iexact', q_str)
        self.assertIn('sender_email__isnull', q_str)

    def test_filter_q_domain_pattern(self):
        q = build_sender_filter_q(['@company.com'])
        q_str = str(q)
        self.assertIn('sender_email__iendswith', q_str)
        self.assertIn('sender_email__isnull', q_str)

    # ── Unit: build_sender_sql_clause ──

    def test_sql_clause_empty(self):
        self.assertEqual(build_sender_sql_clause([]), '1=1')

    def test_sql_clause_exact(self):
        clause = build_sender_sql_clause(['info@example.com'])
        self.assertEqual(clause, "LOWER(frm) = 'info@example.com'")

    def test_sql_clause_domain(self):
        clause = build_sender_sql_clause(['@company.com'])
        self.assertEqual(clause, "LOWER(frm) LIKE '%@company.com'")

    def test_sql_clause_mixed(self):
        clause = build_sender_sql_clause(['info@example.com', '@company.com'])
        self.assertIn("LOWER(frm) = 'info@example.com'", clause)
        self.assertIn("LOWER(frm) LIKE '%@company.com'", clause)
        self.assertIn(' OR ', clause)

    def test_sql_clause_custom_column(self):
        clause = build_sender_sql_clause(['info@example.com'], column='sender')
        self.assertEqual(clause, "LOWER(sender) = 'info@example.com'")

    # ── Integration: ORM filtering ──

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_orm_domain_filter_includes_matching(self):
        msg = BrevoMessage.objects.create(subject='Test', sent_date=timezone.now().date())
        BrevoEmail.objects.create(
            message=msg, brevo_message_id='<orm1@test>',
            recipient_email='r@example.com', sent_at=timezone.now(),
            sender_email='alice@company.com',
        )
        self.assertEqual(BrevoEmail.objects.count(), 1)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_orm_domain_filter_excludes_non_matching(self):
        msg = BrevoMessage.objects.create(subject='Test', sent_date=timezone.now().date())
        BrevoEmail.objects.create(
            message=msg, brevo_message_id='<orm2@test>',
            recipient_email='r@example.com', sent_at=timezone.now(),
            sender_email='bob@other.com',
        )
        self.assertEqual(BrevoEmail.objects.count(), 0)

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_orm_domain_filter_includes_null_sender(self):
        msg = BrevoMessage.objects.create(subject='Test', sent_date=timezone.now().date())
        BrevoEmail.objects.create(
            message=msg, brevo_message_id='<orm3@test>',
            recipient_email='r@example.com', sent_at=timezone.now(),
            sender_email=None,
        )
        self.assertEqual(BrevoEmail.objects.count(), 1)

    # ── Integration: webhook ──

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_domain_match_accepted(self):
        payload = {
            'event': 'request',
            'message-id': '<wh-domain-001@test>',
            'email': 'recipient@example.com',
            'subject': 'Domain Test',
            'ts_event': int(time.time()),
            'sender': 'alice@company.com',
        }
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    @override_settings(BREVO_ANALYTICS={
        'ALLOWED_SENDERS': ['@company.com'],
        'EXCLUDED_RECIPIENT_DOMAINS': [],
    })
    def test_webhook_domain_mismatch_rejected(self):
        payload = {
            'event': 'request',
            'message-id': '<wh-domain-002@test>',
            'email': 'recipient@example.com',
            'subject': 'Domain Test',
            'ts_event': int(time.time()),
            'sender': 'bob@other.com',
        }
        response = self.client.post(
            '/brevo-analytics/webhook/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reason'], 'unauthorized_sender')
