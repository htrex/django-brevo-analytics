"""
Verify and clean emails from unauthorized senders.

This command identifies emails that may have been created by webhooks from
other clients on the same Brevo account, before sender filtering was implemented.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from brevo_analytics.models import BrevoMessage, BrevoEmail
from brevo_analytics.sender_utils import get_allowed_senders


class Command(BaseCommand):
    help = 'Verify emails are from authorized senders and optionally clean unauthorized ones'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be analyzed/deleted without making changes'
        )
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Delete emails that cannot be verified as from authorized senders'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clean = options['clean']

        # Get allowed senders from configuration
        allowed_senders = get_allowed_senders()

        if not allowed_senders:
            self.stdout.write(self.style.WARNING("No ALLOWED_SENDERS configured. Cannot verify."))
            return

        self.stdout.write(f"\n🔍 Verifying emails are from authorized senders\n")
        self.stdout.write(f"Authorized senders: {', '.join(allowed_senders)}\n")

        # Since BrevoEmail doesn't store sender information directly,
        # we need to check if messages exist that shouldn't be there
        # The best we can do is identify suspicious patterns

        all_emails = BrevoEmail.objects.all_including_internal()
        total_emails = all_emails.count()

        self.stdout.write(f"Total emails in database: {total_emails:,}\n")

        # Group by subject to find potential unauthorized campaigns
        from django.db.models import Count
        messages_by_subject = BrevoMessage.objects.values('subject').annotate(
            email_count=Count('emails'),
            message_count=Count('id')
        ).order_by('-email_count')

        self.stdout.write("\n📊 Top messages by email count:")
        self.stdout.write("(Review these manually - suspicious patterns might indicate unauthorized senders)\n")

        for i, msg in enumerate(messages_by_subject[:20], 1):
            subject = msg['subject'][:70]
            count = msg['email_count']
            msg_count = msg['message_count']

            # Flag suspicious patterns
            flags = []
            if msg_count > 1:
                flags.append(f"{msg_count} messages with same subject")

            flag_str = f" ⚠️  {', '.join(flags)}" if flags else ""

            self.stdout.write(f"  {i:2}. {subject:<70} | {count:>6} emails{flag_str}")

        # Check for emails without 'sent' event (might be from webhook-only sources)
        emails_without_sent = []
        self.stdout.write("\n🔍 Checking for emails without 'sent' events...")

        # Sample check (don't load all emails into memory)
        sample_size = min(1000, total_emails)
        sample_emails = all_emails[:sample_size]

        for email in sample_emails:
            has_sent = any(e.get('type') == 'sent' for e in email.events)
            if not has_sent:
                emails_without_sent.append(email)

        if emails_without_sent:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  Found {len(emails_without_sent)} emails (in sample of {sample_size}) without 'sent' event:"
                )
            )
            for email in emails_without_sent[:10]:
                self.stdout.write(
                    f"  - {email.recipient_email} | {email.message.subject[:60]} | "
                    f"Events: {[e.get('type') for e in email.events]}"
                )

            if len(emails_without_sent) > 10:
                self.stdout.write(f"  ... and {len(emails_without_sent) - 10} more in sample")

            self.stdout.write(
                "\nEmails without 'sent' events might be from unauthorized webhook sources."
            )
        else:
            self.stdout.write(self.style.SUCCESS("✓ All sampled emails have 'sent' events"))

        # Provide recommendations
        self.stdout.write("\n" + "="*80)
        self.stdout.write("\n📝 RECOMMENDATIONS:\n")

        self.stdout.write(
            "1. Review the message list above for subjects that don't belong to infoparlamento\n"
            "2. Emails without 'sent' events are suspicious and might be from other clients\n"
            "3. Since BrevoEmail doesn't store sender info directly, you need to:\n"
            "   a) Manually identify unauthorized message subjects\n"
            "   b) Delete those messages: BrevoMessage.objects.filter(subject__icontains='...').delete()\n"
            "   c) Or re-import from CSV (which now filters by sender) with --clear flag\n"
        )

        if not dry_run and clean:
            self.stdout.write(
                self.style.ERROR(
                    "\n⚠️  CLEAN mode is not implemented because we cannot automatically "
                    "determine sender without that field in the model.\n"
                    "Please manually review and delete unauthorized messages using the "
                    "Django shell or admin interface."
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n🔍 DRY RUN - No changes made"))

        self.stdout.write("\n" + "="*80 + "\n")
