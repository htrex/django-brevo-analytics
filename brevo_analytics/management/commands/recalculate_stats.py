"""
Recalculate statistics for all BrevoMessage records.

Use this after updating the calculation logic or cleaning data.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from brevo_analytics.models import BrevoMessage


class Command(BaseCommand):
    help = 'Recalculate statistics for all messages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--message-id',
            type=int,
            help='Recalculate only for specific message ID'
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

        message_id = options.get('message_id')

        if message_id:
            try:
                message = BrevoMessage.objects.get(id=message_id)
                messages = [message]
                self.stdout.write(f"\n📊 Recalculating statistics for message ID {message_id}\n")
            except BrevoMessage.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Message with ID {message_id} not found"))
                return
        else:
            messages = BrevoMessage.objects.all()
            total = messages.count()
            self.stdout.write(f"\n📊 Recalculating statistics for {total:,} messages\n")

        updated = 0
        deleted = []

        for i, message in enumerate(messages, 1):
            # Show progress
            if not message_id and i % 100 == 0:
                self.stdout.write(f"  Processing {i:,}/{len(messages):,}...", ending='\r')

            old_total_sent = message.total_sent
            message.update_stats()

            # Show details if single message or if stats changed significantly
            if message_id or abs(old_total_sent - message.total_sent) > 0:
                self.stdout.write(
                    f"  {message.subject[:60]:<60} | "
                    f"Sent: {old_total_sent:>4} → {message.total_sent:>4}"
                )

            updated += 1

            # Track messages with zero emails for cleanup suggestion
            if message.total_sent == 0:
                deleted.append(message)

        self.stdout.write(f"\n✓ Updated statistics for {updated:,} messages")

        if deleted:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  Found {len(deleted)} messages with zero sent emails:"
                )
            )
            for msg in deleted[:10]:
                self.stdout.write(f"  - ID {msg.id}: {msg.subject[:70]}")

            if len(deleted) > 10:
                self.stdout.write(f"  ... and {len(deleted) - 10} more")

            self.stdout.write("\nConsider deleting these messages:")
            self.stdout.write("  BrevoMessage.objects.filter(total_sent=0).delete()")

        self.stdout.write(self.style.SUCCESS("\n✅ Statistics recalculation completed!\n"))
