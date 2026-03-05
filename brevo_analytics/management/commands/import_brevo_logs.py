"""
Import historical Brevo data from raw logs CSV using DuckDB.

This command processes the CSV export from Brevo logs and reconstructs:
1. BrevoEmail records with complete event timeline
2. BrevoMessage records aggregated by subject + sent_date

Only emails with a 'sent' event are imported (complete history).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
import duckdb
import pytz
import requests
import time
from typing import Optional
from brevo_analytics.models import BrevoMessage, BrevoEmail


# Mapping from CSV st_text values to our event types
# Events mapped to None are explicitly ignored (e.g. repeated 'Aperta'
# events — only 'Prima apertura' / first opening is tracked).
EVENT_TYPE_MAPPING = {
    'Inviata': 'sent',
    'Consegnata': 'delivered',
    'Caricata per procura': 'delivered',  # Alternative delivered status
    'Prima apertura': 'opened',
    'Aperta': None,
    'Cliccata': 'clicked',
    'Hard bounce': 'bounced',
    'Soft bounce': 'bounced',
    'Bloccata': 'blocked',
    'Spam': 'spam',
    'Disiscrizione': 'unsubscribed',
    'Rinviata': 'deferred',
}

BREVO_API_BASE = "https://api.brevo.com/v3"


class Command(BaseCommand):
    help = 'Import historical Brevo logs from CSV using DuckDB'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_path',
            type=str,
            help='Path to logs CSV file (e.g., logs_infoparlamento_202512_today.csv)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show statistics without importing'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before import'
        )

    def handle(self, *args, **options):
        # Check if blacklist-only mode is enabled
        brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
        if brevo_config.get('BLACKLIST_ONLY_MODE', False):
            self.stdout.write(
                self.style.ERROR(
                    'Import is disabled in BLACKLIST_ONLY_MODE.\n'
                    'Use Blacklist Management in Django admin to access '
                    'blacklist data directly from Brevo API.'
                )
            )
            return

        csv_path = options['csv_path']
        dry_run = options['dry_run']
        clear_existing = options['clear']

        self.stdout.write(f"\n📊 Processing CSV: {csv_path}\n")

        # Connect to DuckDB (in-memory)
        conn = duckdb.connect(':memory:')

        try:
            # Load CSV into DuckDB
            self.stdout.write("Loading CSV into DuckDB...")
            conn.execute(f"""
                CREATE TABLE logs AS
                SELECT * FROM read_csv_auto('{csv_path}',
                    header=true,
                    delim=',',
                    quote='"',
                    all_varchar=true
                )
            """)

            # Show total rows
            total_rows = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
            self.stdout.write(f"✓ Loaded {total_rows:,} log entries")

            # Clean up message IDs (remove angle brackets)
            conn.execute("""
                UPDATE logs
                SET mid = TRIM(BOTH '<>' FROM mid)
                WHERE mid LIKE '<%>'
            """)

            # Get allowed senders from configuration
            brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
            allowed_senders = brevo_config.get('ALLOWED_SENDERS', ['info@infoparlamento.it'])

            if isinstance(allowed_senders, str):
                allowed_senders = [allowed_senders]

            self.stdout.write(f"\n🔒 Filtering by allowed senders: {', '.join(allowed_senders)}")

            # Get excluded recipient domains from configuration (default: internal domains)
            excluded_domains = brevo_config.get('EXCLUDED_RECIPIENT_DOMAINS', ['openpolis.it', 'deppsviluppo.org'])
            if isinstance(excluded_domains, str):
                excluded_domains = [excluded_domains]

            if excluded_domains:
                self.stdout.write(f"🚫 Excluding recipient domains: {', '.join(excluded_domains)}")

            # Parse timestamps and map event types
            self.stdout.write("\nPreparing data...")

            # Build WHERE clause for allowed senders
            senders_clause = " OR ".join([f"frm = '{sender}'" for sender in allowed_senders])

            # Build WHERE clause to exclude internal recipient domains
            excluded_clause = ""
            if excluded_domains:
                excluded_conditions = " AND ".join([f"email NOT LIKE '%@{domain}'" for domain in excluded_domains])
                excluded_clause = f"AND ({excluded_conditions})"

            conn.execute(f"""
                CREATE TABLE parsed_logs AS
                SELECT
                    mid,
                    email,
                    sub as subject,
                    st_text,
                    strptime(ts, '%d-%m-%Y %H:%M:%S') as event_timestamp,
                    link,
                    frm
                FROM logs
                WHERE mid IS NOT NULL
                  AND mid != 'NA'
                  AND email IS NOT NULL
                  AND sub IS NOT NULL
                  AND ({senders_clause})
                  {excluded_clause}
            """)

            parsed_count = conn.execute("SELECT COUNT(*) FROM parsed_logs").fetchone()[0]
            self.stdout.write(f"✓ Parsed {parsed_count:,} valid entries")

            # Find emails with 'sent' event
            self.stdout.write("\nFiltering emails with 'sent' event...")
            conn.execute("""
                CREATE TABLE valid_emails AS
                SELECT DISTINCT mid, email
                FROM parsed_logs
                WHERE st_text = 'Inviata'
            """)

            valid_emails_count = conn.execute("SELECT COUNT(*) FROM valid_emails").fetchone()[0]
            self.stdout.write(f"✓ Found {valid_emails_count:,} emails with complete history")

            # Aggregate events per email
            self.stdout.write("\nAggregating events per email...")
            emails_data = conn.execute("""
                SELECT
                    p.mid,
                    p.email,
                    -- Take the first non-null subject (they should all be the same)
                    FIRST(p.subject ORDER BY p.event_timestamp) as subject,
                    -- Take sender from first event
                    FIRST(p.frm ORDER BY p.event_timestamp) as sender,
                    MIN(CASE WHEN p.st_text = 'Inviata'
                        THEN p.event_timestamp END) as sent_at,
                    LIST({
                        'type': p.st_text,
                        'timestamp': p.event_timestamp,
                        'link': p.link
                    } ORDER BY p.event_timestamp) as events
                FROM parsed_logs p
                INNER JOIN valid_emails v ON p.mid = v.mid AND p.email = v.email
                GROUP BY p.mid, p.email
                HAVING MIN(CASE WHEN p.st_text = 'Inviata'
                           THEN p.event_timestamp END) IS NOT NULL
            """).fetchall()

            self.stdout.write(f"✓ Aggregated {len(emails_data):,} email records")

            if dry_run:
                self.stdout.write("\n🔍 DRY RUN - No data imported")
                self._show_statistics(conn)
                return

            # Import into Django with bulk operations
            self.stdout.write("\n💾 Importing into Django (optimized with bulk operations)...")

            if clear_existing:
                self.stdout.write("⚠️  Clearing existing data...")
                BrevoEmail.objects.all().delete()
                BrevoMessage.objects.all().delete()
                self.stdout.write("✓ Cleared all existing data")

            # Check if API key is available for automatic enrichment
            brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
            api_key = brevo_config.get('API_KEY', '')

            if api_key:
                self.stdout.write("✓ API key found - will enrich bounces automatically")
            else:
                self.stdout.write("ℹ️  No API key configured - bounces will not be enriched")

            messages_dict = {}  # (subject, sent_date) -> BrevoMessage
            bounces_enriched = 0
            bounces_failed = 0

            # Process in batches
            BATCH_SIZE = 500
            total_emails = len(emails_data)

            # Track all processed (mid, email) combinations globally to detect duplicates
            all_processed_combinations = set()

            for batch_start in range(0, total_emails, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_emails)
                batch = emails_data[batch_start:batch_end]

                # Prepare batch data
                emails_to_create = []
                emails_to_update = []

                # Get existing emails in this batch
                # Key is (message_id, recipient_email) since same message_id goes to multiple recipients
                batch_message_ids = list(set(row[0] for row in batch))
                existing_emails_list = BrevoEmail.objects.filter(brevo_message_id__in=batch_message_ids)
                existing_emails = {
                    (e.brevo_message_id, e.recipient_email): e
                    for e in existing_emails_list
                }

                for row in batch:
                    mid, recipient_email, subject, sender, sent_at_raw, events_raw = row

                    # Skip if already processed globally (safety check for duplicates in CSV)
                    combination_key = (mid, recipient_email)
                    if combination_key in all_processed_combinations:
                        continue
                    all_processed_combinations.add(combination_key)

                    # Parse sent_at
                    if isinstance(sent_at_raw, str):
                        sent_at = datetime.strptime(sent_at_raw, '%Y-%m-%d %H:%M:%S')
                    else:
                        sent_at = sent_at_raw

                    if sent_at.tzinfo is None:
                        sent_at = pytz.UTC.localize(sent_at)

                    sent_date = sent_at.date()

                    # Get or create BrevoMessage
                    message_key = (subject, sent_date)
                    if message_key not in messages_dict:
                        message, _ = BrevoMessage.objects.get_or_create(
                            subject=subject,
                            sent_date=sent_date
                        )
                        messages_dict[message_key] = message
                    else:
                        message = messages_dict[message_key]

                    # Map events
                    events_list = []
                    has_bounce = False
                    bounce_type = None
                    bounce_event_idx = None

                    for event_idx, event_raw in enumerate(events_raw):
                        event_type_csv = event_raw['type']
                        event_type = EVENT_TYPE_MAPPING.get(event_type_csv, event_type_csv.lower())

                        # Skip explicitly ignored events (e.g. repeated opens)
                        if event_type is None:
                            continue

                        event_timestamp_raw = event_raw['timestamp']
                        if isinstance(event_timestamp_raw, str):
                            event_timestamp = datetime.strptime(event_timestamp_raw, '%Y-%m-%d %H:%M:%S')
                        else:
                            event_timestamp = event_timestamp_raw

                        if event_timestamp.tzinfo is None:
                            event_timestamp = pytz.UTC.localize(event_timestamp)

                        event_data = {
                            'type': event_type,
                            'timestamp': event_timestamp.isoformat(),
                        }

                        # Track bounce for enrichment
                        if event_type == 'bounced':
                            has_bounce = True
                            bounce_event_idx = event_idx
                            if 'Hard bounce' in event_type_csv:
                                bounce_type = 'hard'
                            elif 'Soft bounce' in event_type_csv:
                                bounce_type = 'soft'
                            else:
                                bounce_type = 'hard'
                            event_data['bounce_type'] = bounce_type

                        # Add link if present
                        link = event_raw.get('link')
                        if link and link != 'NA':
                            event_data['link'] = link

                        events_list.append(event_data)

                    # Enrich bounce if requested and needed (only for new emails to avoid re-enrichment)
                    if api_key and has_bounce and bounce_event_idx is not None and combination_key not in existing_emails:
                        bounce_timestamp = datetime.fromisoformat(
                            events_list[bounce_event_idx]['timestamp'].replace('Z', '+00:00')
                        )
                        reason = self._fetch_bounce_reason(
                            api_key, mid, bounce_type, bounce_timestamp
                        )
                        if reason:
                            events_list[bounce_event_idx]['bounce_reason'] = reason
                            bounces_enriched += 1
                        else:
                            bounces_failed += 1

                    # Calculate status
                    event_types = {e['type'] for e in events_list}
                    if 'clicked' in event_types:
                        current_status = 'clicked'
                    elif 'opened' in event_types:
                        current_status = 'opened'
                    elif 'delivered' in event_types:
                        current_status = 'delivered'
                    elif 'bounced' in event_types:
                        current_status = 'bounced'
                    elif 'blocked' in event_types:
                        current_status = 'blocked'
                    elif 'deferred' in event_types:
                        current_status = 'deferred'
                    elif 'unsubscribed' in event_types:
                        current_status = 'unsubscribed'
                    else:
                        current_status = 'sent'

                    # Create or update
                    if combination_key in existing_emails:
                        email = existing_emails[combination_key]
                        email.message = message
                        email.sender_email = sender if sender else None
                        email.recipient_email = recipient_email
                        email.sent_at = sent_at
                        email.events = events_list
                        email.current_status = current_status
                        emails_to_update.append(email)
                    else:
                        email = BrevoEmail(
                            brevo_message_id=mid,
                            message=message,
                            sender_email=sender if sender else None,
                            recipient_email=recipient_email,
                            sent_at=sent_at,
                            events=events_list,
                            current_status=current_status
                        )
                        emails_to_create.append(email)

                # Bulk operations and count
                with transaction.atomic():
                    if emails_to_create:
                        BrevoEmail.objects.bulk_create(emails_to_create, batch_size=500)
                    if emails_to_update:
                        BrevoEmail.objects.bulk_update(
                            emails_to_update,
                            ['message', 'sender_email', 'recipient_email', 'sent_at', 'events', 'current_status'],
                            batch_size=500
                        )

                self.stdout.write(
                    f"  Batch {batch_end:,}/{total_emails:,}: "
                    f"+{len(emails_to_create)} created, ~{len(emails_to_update)} updated",
                    ending='\r'
                )

            # Count actual records in DB
            total_emails_in_db = BrevoEmail.objects.count()
            total_bounces_in_db = BrevoEmail.objects.filter(current_status='bounced').count()
            duplicates_skipped = total_emails - len(all_processed_combinations)

            self.stdout.write(f"\n✓ Processed {len(all_processed_combinations):,} unique (message_id, recipient) pairs from CSV")
            self.stdout.write(f"✓ Total emails in DB: {total_emails_in_db:,}")
            self.stdout.write(f"✓ Total bounces in DB: {total_bounces_in_db}")

            if duplicates_skipped > 0:
                self.stdout.write(f"ℹ️  Skipped {duplicates_skipped:,} duplicate entries in CSV")

            if api_key and (bounces_enriched > 0 or bounces_failed > 0):
                self.stdout.write(f"✓ Enriched {bounces_enriched}/{bounces_enriched + bounces_failed} bounces with reasons from API")
                if bounces_failed > 0:
                    self.stdout.write(f"   ({bounces_failed} bounces not found in Brevo API)")

            # Update message statistics (batch)
            self.stdout.write("\nUpdating message statistics...")
            for message in messages_dict.values():
                message.update_stats()

            self.stdout.write(f"✓ Updated {len(messages_dict):,} messages")

            self.stdout.write("\n✅ Import completed successfully!\n")

        except Exception as e:
            self.stderr.write(f"\n❌ Error: {e}\n")
            raise

        finally:
            conn.close()

    def _fetch_bounce_reason(
        self,
        api_key: str,
        brevo_message_id: str,
        bounce_type: str,
        event_timestamp: datetime
    ) -> Optional[str]:
        """
        Fetch bounce reason from Brevo API for a specific message.

        Args:
            api_key: Brevo API key
            brevo_message_id: Brevo message ID (without angle brackets)
            bounce_type: 'hard' or 'soft'
            event_timestamp: Datetime of the bounce event

        Returns:
            Bounce reason string or None if not found
        """
        # Map bounce_type to API event name
        api_event = 'hardBounces' if bounce_type == 'hard' else 'softBounces'

        # Search window: same day ± 1 day for safety
        start_date_dt = event_timestamp - timedelta(days=1)
        end_date_dt = event_timestamp + timedelta(days=1)

        # IMPORTANT: Brevo API rejects endDate > today
        today = timezone.now()  # Use timezone-aware datetime
        if end_date_dt > today:
            end_date_dt = today

        start_date = start_date_dt.strftime('%Y-%m-%d')
        end_date = end_date_dt.strftime('%Y-%m-%d')

        headers = {
            'api-key': api_key,
            'accept': 'application/json'
        }

        # Brevo API requires angle brackets
        message_id_param = f"<{brevo_message_id}>"

        params = {
            'event': api_event,
            'messageId': message_id_param,
            'startDate': start_date,
            'endDate': end_date,
            'limit': 10,
            'sort': 'desc'
        }

        try:
            response = requests.get(
                f"{BREVO_API_BASE}/smtp/statistics/events",
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 429:
                self.stdout.write("    Rate limited (429), waiting 5s...")
                time.sleep(5)
                return self._fetch_bounce_reason(api_key, brevo_message_id, bounce_type, event_timestamp)

            if response.status_code == 401:
                self.stderr.write("    ERROR: Invalid API key (401)")
                return None

            if response.status_code != 200:
                self.stderr.write(f"    API error {response.status_code}: {response.text[:100]}")
                return None

            data = response.json()
            events = data.get('events', [])

            if not events:
                return None

            # Get reason from first matching event
            event = events[0]
            reason = event.get('reason', event.get('error', ''))

            return reason if reason else None

        except requests.exceptions.Timeout:
            self.stderr.write("    Timeout fetching from API")
            return None
        except Exception as e:
            self.stderr.write(f"    Error fetching from API: {e}")
            return None

    def _show_statistics(self, conn):
        """Show statistics about the data to be imported"""
        self.stdout.write("\n📈 Statistics:")

        # Total events by type
        self.stdout.write("\nEvents by type:")
        event_stats = conn.execute("""
            SELECT st_text, COUNT(*) as count
            FROM parsed_logs
            GROUP BY st_text
            ORDER BY count DESC
        """).fetchall()

        for event_type, count in event_stats:
            mapped_type = EVENT_TYPE_MAPPING.get(event_type, event_type)
            if mapped_type is None:
                self.stdout.write(f"  {event_type} → (ignored): {count:,}")
            else:
                self.stdout.write(f"  {event_type} → {mapped_type}: {count:,}")

        # Emails with/without sent event
        with_sent = conn.execute("""
            SELECT COUNT(DISTINCT mid || email)
            FROM parsed_logs
            WHERE st_text = 'Inviata'
        """).fetchone()[0]

        without_sent = conn.execute("""
            SELECT COUNT(DISTINCT mid || email)
            FROM parsed_logs
            WHERE mid || email NOT IN (
                SELECT mid || email
                FROM parsed_logs
                WHERE st_text = 'Inviata'
            )
        """).fetchone()[0]

        self.stdout.write(f"\n✅ Emails WITH sent event: {with_sent:,}")
        self.stdout.write(f"❌ Emails WITHOUT sent event (will be skipped): {without_sent:,}")

        # Date range
        date_range = conn.execute("""
            SELECT MIN(event_timestamp), MAX(event_timestamp)
            FROM parsed_logs
        """).fetchone()

        self.stdout.write(f"\n📅 Date range: {date_range[0]} to {date_range[1]}\n")
