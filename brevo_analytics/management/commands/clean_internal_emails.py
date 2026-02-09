"""
Clean emails sent to internal domains from the database.

This command removes BrevoEmail records sent to excluded internal domains
(configurable via EXCLUDED_RECIPIENT_DOMAINS) and recalculates message statistics.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from brevo_analytics.models import BrevoMessage, BrevoEmail


class Command(BaseCommand):
    help = 'Remove emails sent to internal domains and recalculate statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
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

        dry_run = options['dry_run']

        # Get excluded domains from configuration
        excluded_domains = brevo_config.get('EXCLUDED_RECIPIENT_DOMAINS', ['openpolis.it', 'deppsviluppo.org'])

        if isinstance(excluded_domains, str):
            excluded_domains = [excluded_domains]

        if not excluded_domains:
            self.stdout.write(self.style.WARNING("No excluded domains configured. Nothing to clean."))
            return

        self.stdout.write(f"\n🧹 Cleaning emails sent to: {', '.join(excluded_domains)}\n")

        # Find emails to delete
        from django.db.models import Q
        exclude_q = Q()
        for domain in excluded_domains:
            exclude_q |= Q(recipient_email__iendswith=f'@{domain}')

        # Use all_including_internal() to bypass the default manager filter
        internal_emails = BrevoEmail.objects.all_including_internal().filter(exclude_q)
        total_count = internal_emails.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("✓ No internal emails found. Database is clean!"))
            return

        self.stdout.write(f"Found {total_count:,} emails to internal domains:")

        # Show breakdown by domain
        for domain in excluded_domains:
            count = BrevoEmail.objects.all_including_internal().filter(
                recipient_email__iendswith=f'@{domain}'
            ).count()
            if count > 0:
                self.stdout.write(f"  - @{domain}: {count:,} emails")

        # Show sample emails
        self.stdout.write("\nSample emails to be deleted:")
        sample_emails = internal_emails[:10]
        for email in sample_emails:
            self.stdout.write(
                f"  - {email.recipient_email} | {email.message.subject[:60]} | {email.sent_at}"
            )

        if total_count > 10:
            self.stdout.write(f"  ... and {total_count - 10:,} more\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n🔍 DRY RUN - No data deleted"))
            return

        # Confirm deletion
        self.stdout.write(
            self.style.WARNING(
                f"\n⚠️  This will DELETE {total_count:,} emails from the database."
            )
        )
        confirm = input("Type 'yes' to continue: ")

        if confirm.lower() != 'yes':
            self.stdout.write(self.style.WARNING("Operation cancelled."))
            return

        # Get affected messages before deletion
        affected_message_ids = set(internal_emails.values_list('message_id', flat=True))
        self.stdout.write(f"\n📊 {len(affected_message_ids)} messages will have statistics updated")

        # Delete emails
        with transaction.atomic():
            deleted_count, _ = internal_emails.delete()
            self.stdout.write(f"✓ Deleted {deleted_count:,} internal emails")

            # Recalculate statistics for affected messages
            self.stdout.write("\nRecalculating message statistics...")
            updated_count = 0
            deleted_messages = []

            for message_id in affected_message_ids:
                try:
                    message = BrevoMessage.objects.get(id=message_id)
                    message.update_stats()
                    updated_count += 1

                    # If message now has zero emails, mark for deletion
                    if message.total_sent == 0:
                        deleted_messages.append(message)

                except BrevoMessage.DoesNotExist:
                    pass

            self.stdout.write(f"✓ Updated statistics for {updated_count} messages")

            # Delete messages with zero emails
            if deleted_messages:
                self.stdout.write(
                    f"\n🗑️  Deleting {len(deleted_messages)} messages with no remaining emails..."
                )
                for message in deleted_messages:
                    self.stdout.write(f"  - {message.subject[:80]}")
                    message.delete()

        self.stdout.write(self.style.SUCCESS("\n✅ Cleanup completed successfully!"))
        self.stdout.write(
            f"Summary: Deleted {deleted_count:,} emails and {len(deleted_messages)} empty messages"
        )
