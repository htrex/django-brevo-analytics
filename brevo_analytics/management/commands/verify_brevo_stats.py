"""
Management command to verify statistics against Brevo API.

This command compares local statistics with what's reported by Brevo API
to help identify discrepancies.

Usage:
    python manage.py verify_brevo_stats --api-key YOUR_API_KEY [--message-id ID]
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from brevo_analytics.models import BrevoMessage, BrevoEmail
import requests
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Verify statistics against Brevo API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--api-key',
            type=str,
            help='Brevo API Key (or set BREVO_API_KEY in settings)',
            default=None
        )
        parser.add_argument(
            '--message-id',
            type=int,
            help='Verify specific message ID only',
            default=None
        )
        parser.add_argument(
            '--recent',
            type=int,
            default=10,
            help='Check only N most recent messages (default: 10)'
        )

    def handle(self, *args, **options):
        # Check if blacklist-only mode is enabled
        brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
        if brevo_config.get('BLACKLIST_ONLY_MODE', False):
            self.stdout.write(
                self.style.ERROR(
                    'This command is disabled in BLACKLIST_ONLY_MODE.\n'
                    'Database tables are unused in this mode. '
                    'Use Blacklist Management to access data from Brevo API.'
                )
            )
            return

        api_key = options['api_key'] or settings.BREVO_ANALYTICS.get('API_KEY', '')

        if not api_key:
            self.stderr.write(self.style.ERROR(
                'Brevo API Key required. Use --api-key or set BREVO_API_KEY in settings'
            ))
            return

        headers = {
            'accept': 'application/json',
            'api-key': api_key
        }

        # Get messages to verify
        if options['message_id']:
            messages = BrevoMessage.objects.filter(id=options['message_id'])
        else:
            messages = BrevoMessage.objects.order_by('-sent_date')[:options['recent']]

        total = messages.count()
        self.stdout.write(f"Verifying {total} message(s)...\n")

        for message in messages:
            self.stdout.write(self.style.HTTP_INFO(
                f"\n{'='*80}\n{message.subject} ({message.sent_date})\n{'='*80}"
            ))

            # Local statistics
            self.stdout.write(f"\n📊 LOCAL STATISTICS:")
            self.stdout.write(f"  Total Sent:      {message.total_sent}")
            self.stdout.write(f"  Delivered:       {message.total_delivered}")
            self.stdout.write(f"  Opened:          {message.total_opened}")
            self.stdout.write(f"  Clicked:         {message.total_clicked}")
            self.stdout.write(f"  Bounced:         {message.total_bounced}")
            self.stdout.write(f"  Blocked:         {message.total_blocked}")
            self.stdout.write(f"  Delivery Rate:   {message.delivery_rate}%")
            self.stdout.write(f"  Open Rate:       {message.open_rate}%")
            self.stdout.write(f"  Click Rate:      {message.click_rate}%")

            # Count emails by status in our DB
            email_counts = {}
            for status in ['sent', 'delivered', 'opened', 'clicked', 'bounced', 'blocked', 'deferred']:
                count = message.emails.filter(current_status=status).count()
                email_counts[status] = count

            self.stdout.write(f"\n📧 EMAIL COUNTS BY STATUS:")
            for status, count in email_counts.items():
                self.stdout.write(f"  {status:12}: {count}")

            # Try to get stats from Brevo API
            try:
                # Get a sample of emails to query
                sample_emails = message.emails.order_by('sent_at')[:5]

                if not sample_emails:
                    self.stdout.write(self.style.WARNING(
                        "\n🔍 BREVO API: No emails found in local DB"
                    ))
                    continue

                self.stdout.write(f"\n🌐 Querying Brevo API for {len(sample_emails)} sample emails...")

                api_email_data = []
                for email in sample_emails:
                    # Query by email address (required parameter)
                    params = {
                        'limit': 50,
                        'email': email.recipient_email,
                        'startDate': str(message.sent_date),
                        'endDate': str(message.sent_date),
                    }

                    response = requests.get(
                        'https://api.brevo.com/v3/smtp/emails',
                        headers=headers,
                        params=params,
                        timeout=10
                    )

                    if response.status_code == 200:
                        data = response.json()
                        emails_list = data.get('transactionalEmails', [])
                        # Filter by subject
                        matching = [e for e in emails_list if e.get('subject') == message.subject]
                        api_email_data.extend(matching)

                # Remove duplicates by messageId
                seen_ids = set()
                unique_api_emails = []
                for email_data in api_email_data:
                    msg_id = email_data.get('messageId')
                    if msg_id and msg_id not in seen_ids:
                        seen_ids.add(msg_id)
                        unique_api_emails.append(email_data)

                if unique_api_emails:
                    self.stdout.write(f"\n🔍 BREVO API RESULTS:")
                    self.stdout.write(f"  Sample emails queried: {len(sample_emails)}")
                    self.stdout.write(f"  Matching emails found:  {len(unique_api_emails)}")

                    # Skip detailed event counting for now
                    self.stdout.write(f"\n  (Detailed event comparison skipped - API returns limited data)")
                else:
                    self.stdout.write(self.style.WARNING(
                        "\n🔍 BREVO API: No matching emails found"
                    ))
                    continue

                # Now try to get aggregate stats instead
                response = None  # Skip the old response handling

                if response.status_code == 200:
                    data = response.json()
                    emails = data.get('transactionalEmails', [])

                    # Filter by subject
                    matching_emails = [e for e in emails if e.get('subject') == message.subject]

                    self.stdout.write(f"\n🔍 BREVO API RESULTS:")
                    self.stdout.write(f"  Total emails returned: {len(emails)}")
                    self.stdout.write(f"  Matching subject:      {len(matching_emails)}")

                    if matching_emails:
                        # Count by event
                        api_counts = {
                            'sent': 0,
                            'delivered': 0,
                            'opened': 0,
                            'clicked': 0,
                            'bounced': 0,
                            'blocked': 0,
                        }

                        for email in matching_emails:
                            events = email.get('event', [])
                            if isinstance(events, list):
                                if 'click' in events:
                                    api_counts['clicked'] += 1
                                elif 'opened' in events:
                                    api_counts['opened'] += 1
                                elif 'delivered' in events:
                                    api_counts['delivered'] += 1
                                elif 'hard_bounce' in events or 'soft_bounce' in events:
                                    api_counts['bounced'] += 1
                                elif 'blocked' in events:
                                    api_counts['blocked'] += 1
                                else:
                                    api_counts['sent'] += 1

                        self.stdout.write(f"\n  API Event Counts:")
                        for status, count in api_counts.items():
                            local_count = email_counts.get(status, 0)
                            diff = count - local_count
                            diff_str = f"({diff:+d})" if diff != 0 else "✓"
                            self.stdout.write(f"    {status:12}: {count:4} vs {local_count:4} {diff_str}")

                    else:
                        self.stdout.write(self.style.WARNING(
                            "  No matching emails found in API response"
                        ))

                else:
                    try:
                        error_detail = response.json()
                        self.stderr.write(self.style.ERROR(
                            f"  API error {response.status_code}: {error_detail}"
                        ))
                    except:
                        self.stderr.write(self.style.ERROR(
                            f"  API error {response.status_code}: {response.text[:500]}"
                        ))

            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  Error querying API: {str(e)}"
                ))
                import traceback
                self.stderr.write(traceback.format_exc())

        self.stdout.write(f"\n{'='*80}\n")
        self.stdout.write(self.style.SUCCESS("✓ Verification complete"))
