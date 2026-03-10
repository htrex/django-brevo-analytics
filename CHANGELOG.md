# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Tag-Based Message Grouping**: Optional grouping strategy that uses Brevo tags instead of email subjects
  - New setting `MESSAGE_GROUP_BY`: `'subject'` (default, unchanged) or `'tag'`
  - New setting `MESSAGE_TAG_PREFIX`: prefix to match grouping tags (default: `'digest'`)
  - Tag format convention: `{prefix}:{id}:{display_title}`
  - New `tags` JSONField on `BrevoEmail` model — stores all tags from webhook/CSV regardless of grouping mode
  - New `display_subject` computed field in API serializers — strips prefix and ID for human-readable display
  - Webhook: extracts tags from payload, applies tag-based grouping when configured
  - CSV import: reads `tag` column, stores on BrevoEmail, applies tag-based grouping when configured
  - Graceful fallback: when no matching tag found, uses email subject (same as default mode)
  - Full backward compatibility: no changes to BrevoMessage model, no migration on that table
  - New migration 0007: adds `tags` JSONField to BrevoEmail (default=list)

### Fixed

- **Django 5.2 compatibility**: Fixed `timezone.utc` deprecation in webhook handler (use `datetime.timezone.utc`)

## [0.5.1] - 2026-03-05

### Changed

- **Date formatting improvements** in email list views (thanks to @htrex):
  - `formatShortDate` now includes the year (e.g. "5 dic 2025" instead of "5 dic")
  - `formatDateTime` now includes the year and uses a "date - time" separator (e.g. "5 dic 2025 - 12:15:32")
  - Column header renamed from "Data" to "Data - Ora Invio" with a dedicated i18n key `sent_datetime`

## [0.5.0] - 2026-03-05

### Added

- **Complete Brevo webhook event mapping** (thanks to @htrex):
  - Added `invalid_email` → `bounced` and `error` → `bounced` event types
  - Added `unique_opened` → `opened` and `unique_proxy_open` → `opened` (first-open tracking)
  - Added explicit `proxy_open` → ignored (repeated proxy opens suppressed)

### Changed

- **Ignore repeated open events**: `opened` and `proxy_open` events are now ignored; only `unique_opened` and `unique_proxy_open` (first opening) are tracked to avoid inflating open counts
- **CSV import**: `Aperta` events (repeated opens) are now ignored; only `Prima apertura` is tracked, consistent with webhook behaviour
- **Fix `unsubscribe` key**: corrected event mapping key from `unsubscribe` to `unsubscribed` to match Brevo API documentation
- **Fix ip/user_agent capture**: open metadata (IP, user agent) now correctly captured for `unique_opened` and `unique_proxy_open` events

## [0.4.0] - 2026-02-20

### Changed

- **Django 5.x Compatibility** (thanks to @htrex):
  - Widened Django version constraint from `>=4.2,<5.0` to `>=4.2,<6.0`
  - Replaced deprecated `unique_together` with `UniqueConstraint` in both `BrevoMessage` and `BrevoEmail` models
  - Added migration 0006 to convert existing unique_together constraints to named UniqueConstraints
  - Added Django 5.0 and 5.1 framework classifiers to pyproject.toml
  - Fully backward compatible with Django 4.2 (UniqueConstraint available since Django 2.2)

### Fixed

- **Documentation**: Corrected URL paths in README.md to align with frontend API implementation
  - Changed URL mounting from `/admin/brevo_analytics/` to `/brevo-analytics/` to match Vue.js SPA expectations
  - Updated webhook URL documentation from `/admin/brevo_analytics/webhook/` to `/brevo-analytics/webhook/`
  - Added clarifying note that API endpoints are mounted at `/brevo-analytics/` while dashboard access remains at Django admin URL `/admin/brevo_analytics/brevomessage/`

## [0.3.0] - 2026-02-09

### Added

- **Blacklist-Only Mode**: New configuration flag for deployments that only need blacklist management without full email analytics
  - **Configuration**: Set `BLACKLIST_ONLY_MODE = True` in `BREVO_ANALYTICS` settings
  - **Use Case**: Ideal for scenarios where email subjects vary per client (e.g., Comin with customizable subjects), making subject-based message grouping impractical
  - **Behavior**:
    - Admin interface shows only "Blacklist Management" menu (hides "Message Analysis")
    - Webhook endpoint returns 404 with informative message
    - Import and statistics commands exit with clear error messages
    - Database tables are created but remain unused
    - Blacklist SPA works normally via direct Brevo API queries
  - **Commands disabled**: `import_brevo_logs`, `clean_internal_emails`, `recalculate_stats`, `verify_brevo_stats`
  - **Backwards compatible**: Default is `False`, existing installations continue working normally

### Technical Details

- **Admin Registration** (`admin.py`):
  - Refactored from `@admin.register()` decorators to conditional registration
  - `BrevoMessageAdmin` registered only when `BLACKLIST_ONLY_MODE = False`
  - `BrevoEmailAdmin` always registered for blacklist management

- **Webhook Handler** (`webhooks.py`):
  - Added early mode check at function start
  - Returns JSON response with `status: "disabled"` and HTTP 404 when mode enabled
  - Includes logging for monitoring webhook calls in blacklist-only mode

- **Management Commands**:
  - `import_brevo_logs.py`: Added mode check, exits with styled error message
  - `clean_internal_emails.py`: Added mode check to prevent database cleanup operations
  - `recalculate_stats.py`: Added mode check to prevent statistics recalculation
  - `verify_brevo_stats.py`: Added mode check to prevent API verification
  - All commands show consistent error message directing users to Blacklist Management

- **Test Coverage** (`tests.py`):
  - Added `BlacklistOnlyModeTestCase` with 3 test methods
  - Tests webhook returns 404 in blacklist-only mode
  - Tests import command exits with error in blacklist-only mode
  - Tests webhook works normally when mode disabled
  - All 8 tests pass successfully

- **Documentation**:
  - Added comprehensive "Blacklist-Only Mode" section to `docs/README.md`
  - Added detailed configuration guide to `CLAUDE.md` with verification steps
  - Documented all disabled commands and expected behavior
  - Included example configurations for blacklist-only deployments

## [0.2.6] - 2026-02-03

### Fixed

- **Webhook Event Recovery**: Webhook now creates email records from 'delivered' events when 'sent' event was missed or delayed
  - **Problem**: Brevo doesn't guarantee event order - 'delivered', 'opened', or 'clicked' events can arrive before 'sent' event
  - **Previous behavior**: Webhook ignored all events for unknown emails, waiting for 'sent' event that might never arrive
  - **New behavior**:
    - 'delivered' event is treated as proof of sending and triggers record creation
    - When creating from 'delivered': adds inferred 'sent' event to maintain statistics consistency
    - If real 'sent' event arrives later: replaces inferred 'sent' with real one (correct timestamp)
  - **Impact**: Improves delivery rate accuracy by recovering ~6% of emails where 'sent' event arrives late or is lost
  - **Benefit**: Reduces false error reports in Brevo webhook dashboard (from ~250 errors to near zero)

### Technical Details

- **Webhook changes** (`webhooks.py`):
  - Added `is_delivered_event` check alongside `is_sent_event` for record creation
  - When creating from 'delivered' event:
    - Sets initial status to 'delivered' instead of 'sent'
    - Adds inferred 'sent' event with `inferred: True` flag to events array
    - Uses delivered timestamp as sent_at (close approximation)
  - Updated log messages to distinguish between normal creation and recovery from delivered event
  - Other events (opened, clicked) still require prior sent/delivered event

- **Model changes** (`models.py`):
  - Modified `BrevoEmail.add_event()` to handle inferred 'sent' events
  - When adding real 'sent' event: automatically removes any inferred 'sent' events first
  - Prevents duplicate 'sent' events in statistics and timeline
  - Ensures correct sent_count in message statistics

- **Event ordering scenarios**:
  - Normal: sent → delivered → opened → clicked (no change in behavior)
  - Delayed: delivered → opened → sent (now handled: creates from delivered, updates when sent arrives)
  - Missing: delivered → opened → clicked (no sent ever) (now handled: uses inferred sent)

## [0.2.5] - 2026-01-29

### Removed

- **Blacklist Management UI**: Removed "Arricchisci DB" (Enrich Database) button from blacklist management interface
  - Button allowed enriching local blocked emails database with information from Brevo blacklist
  - Functionality removed as it's no longer needed in the current workflow
  - Simplified UI by removing unnecessary operation button
  - Removed `enrichDatabase()` function and related state management from Vue.js component

### Technical Details

- Removed enrichment button from ListAllTab component template
- Removed `enriching` reactive state reference
- Removed `enrichDatabase` async function
- Cleaned up component return statement to remove unused references

## [0.2.4] - 2026-01-28

### Fixed

- **Internationalization**: Fixed untranslated KPI filter labels in Message Emails view
  - Status filter buttons (Sent, Delivered, Opened, Clicked, Bounced, Blocked) now properly use i18n translation keys
  - Labels were previously hardcoded in English, preventing proper localization
  - All KPI filter labels now use `$t()` function for dynamic translation based on user locale
  - Improves user experience for non-English speakers

### Technical Details

- Updated Vue.js SPA template to replace hardcoded English labels with i18n keys
- Modified KPI filter button rendering in Message Emails view component
- Maintains existing functionality while enabling proper multilingual support

## [0.2.3] - 2026-01-27

### Fixed

- **Webhook Authentication**: Fixed critical bug where webhook validation was looking for non-existent `X-Brevo-Signature` HMAC header
  - Brevo actually sends authentication as `Authorization: Bearer <token>` header
  - Changed webhook authentication from HMAC signature validation to Bearer token validation
  - This bug caused all webhook requests to fail with "Invalid webhook signature" warnings since v0.1.0
  - Webhook now correctly validates the Bearer token from `Authorization` header against `WEBHOOK_SECRET` setting
- **Sender Email Extraction**: Enhanced sender field extraction to support `sender_email` field in webhook payloads
  - Webhook now checks `sender`, `from`, and `sender_email` fields (in that order) to extract sender information
  - Eliminates "no sender information" warnings for events that include `sender_email` field

### Technical Details

- Removed unused `hmac` and `hashlib` imports from webhook handler
- Simplified authentication logic: direct string comparison of Bearer token instead of HMAC computation
- Maintains backward compatibility with existing `WEBHOOK_SECRET` configuration

## [0.2.2] - 2026-01-27

### Fixed

- **Missing Migration File**: Included Django migration file (`0005_brevoemail_sender_email.py`) that was inadvertently omitted from v0.2.1 package
  - Users who installed v0.2.1 encountered errors when running `python manage.py migrate brevo_analytics`
  - Migration creates the `sender_email` field required for sender validation introduced in v0.2.1
  - This hotfix completes the security patch from v0.2.1 by providing the required database schema changes

### Migration Note

**For users who installed v0.2.1:**
- Upgrade immediately to v0.2.2 to get the missing migration file
- Run `python manage.py migrate brevo_analytics` after upgrading
- No other changes required - all configuration from v0.2.1 remains valid

**For new installations:**
- This version includes all migrations needed for the sender validation security feature
- Follow the standard installation and configuration steps from the README

### Technical Details

- Added migration file: `brevo_analytics/migrations/0005_brevoemail_sender_email.py`
- Creates `sender_email` field on `BrevoEmail` model (nullable CharField, indexed)
- No code changes - purely a packaging fix to include the migration in the distribution

## [0.2.1] - 2026-01-27

### Security

**CRITICAL SECURITY PATCH - IMMEDIATE UPDATE REQUIRED**

- **Multi-Tenant Data Contamination Vulnerability**: Fixed critical security flaw where webhook accepted events from ANY sender on shared Brevo account
  - **Impact**: Before this fix, webhook processed events from all clients sharing the same Brevo account, mixing data from different organizations into the same database
  - **Severity**: CRITICAL - Potential for unauthorized access to analytics data from other tenants
  - **Resolution**: Webhook now validates sender email against `ALLOWED_SENDERS` configuration before processing any events

### Added

- **Sender Email Tracking**: New `sender_email` field in `BrevoEmail` model
  - Captures sender address from every Brevo event
  - Enables sender-based filtering and data isolation
  - Indexed for fast queries
- **Sender Validation**: Automatic sender verification in webhook processing
  - Only events from senders in `BREVO_ANALYTICS['ALLOWED_SENDERS']` are processed
  - Unauthorized sender events are logged and rejected
  - Prevents data contamination from other tenants on shared Brevo accounts
- **ORM-Level Sender Filtering**: Enhanced `BrevoEmailManager` with automatic sender filtering
  - All database queries automatically exclude unauthorized senders
  - Transparent filtering - no code changes required in existing applications
  - Works with all Django ORM methods (filter, exclude, annotate, etc.)
- **Management Command**: `verify_senders` - Identify potentially contaminated data
  - Scans database for emails from unauthorized senders
  - Reports statistics on data contamination
  - Supports dry-run mode to preview issues before cleanup
  - Helps assess impact of vulnerability on existing installations

### Changed

- **Database Schema**: Added `sender_email` field to `BrevoEmail` model
  - **Migration Required**: Run `python manage.py migrate brevo_analytics` after update
  - Nullable field for backward compatibility with existing data
  - Future webhook events will populate this field automatically
- **Configuration Requirement**: `ALLOWED_SENDERS` setting is now MANDATORY
  - Must be configured in `BREVO_ANALYTICS['ALLOWED_SENDERS']` setting
  - List of authorized sender email addresses for your organization
  - Events from unlisted senders will be rejected
  - Example: `ALLOWED_SENDERS = ['noreply@example.com', 'alerts@example.com']`
- **Webhook Behavior**: Enhanced event processing with sender validation
  - Extracts sender email from `from` or `sender` webhook fields
  - Validates against ALLOWED_SENDERS before database operations
  - Logs rejection of unauthorized sender events for audit trail

### Migration Guide

**CRITICAL - Action Required for All Installations:**

1. **Update Package**:
   ```bash
   pip install --upgrade django-brevo-analytics==0.2.1
   ```

2. **Configure ALLOWED_SENDERS** in Django settings:
   ```python
   BREVO_ANALYTICS = {
       'WEBHOOK_SECRET': 'your-webhook-secret',
       'CLIENT_UID': 'your-client-uuid',
       'ALLOWED_SENDERS': [
           'noreply@yourcompany.com',
           'alerts@yourcompany.com',
           # Add all legitimate sender addresses for your organization
       ],
   }
   ```

3. **Run Database Migration**:
   ```bash
   python manage.py migrate brevo_analytics
   ```

4. **Verify Existing Data** (optional but recommended):
   ```bash
   # Check for potentially contaminated data
   python manage.py verify_senders
   ```

5. **Re-import Historical Data** (recommended):
   ```bash
   # Clear and reimport to populate sender_email field
   python manage.py import_brevo_logs /path/to/logs.csv --clear
   ```

### Impact Assessment

**Before Fix:**
- Webhook accepted events from ANY sender on shared Brevo account
- Analytics data could include emails from other organizations
- No sender validation or isolation between tenants
- Potential for data leakage in multi-tenant Brevo accounts

**After Fix:**
- Only authorized senders (configured in ALLOWED_SENDERS) are processed
- Automatic sender validation on all webhook events
- ORM-level filtering ensures unauthorized data never appears in queries
- Complete data isolation for multi-tenant environments

**Affected Versions**: All versions prior to 0.2.1

**Recommended Action**: Immediate update for all installations, especially those on shared Brevo accounts

## [0.2.0] - 2026-01-27

### Added
- **Internal Domain Filtering System**: Comprehensive three-level filtering to exclude internal/test emails from analytics
  - Configure excluded domains via `BREVO_ANALYTICS['EXCLUDED_RECIPIENT_DOMAINS']` setting
  - Automatic filtering during CSV import prevents internal emails from entering the database
  - Real-time webhook filtering blocks internal domain events before processing
  - Model-level query filtering ensures internal emails never appear in analytics views or API responses
- **Management Command**: `clean_internal_emails` - Remove existing internal emails from database
  - Supports dry-run mode to preview deletions before applying
  - Automatically recalculates message statistics after cleanup
  - Useful for cleaning up data imported before domain filtering was configured
- **Management Command**: `recalculate_stats` - Recalculate statistics for all messages
  - Rebuild denormalized statistics from event data
  - Useful after data cleanup or manual database changes
  - Ensures dashboard metrics remain accurate

### Fixed
- **Statistics Accuracy**: Fixed critical bug in `BrevoMessage.update_stats()` that was counting all emails in the database instead of only emails with 'sent' events for the specific message
  - Delivery rate, open rate, and click rate calculations now correctly reflect actual sent emails
  - Prevents inflated or incorrect percentage metrics in dashboard
- **Webhook Event Processing**: Webhook now correctly ignores events that arrive without a prior 'sent' event in the database
  - Prevents orphaned events from creating incomplete email records
  - Ensures all tracked emails have complete event history starting from 'sent'

### Changed
- **Email Model**: Added custom `BrevoEmailQuerySet` and `BrevoEmailManager` for automatic domain filtering at the ORM level
  - All queries automatically exclude internal domains without manual filtering
  - Transparent to existing code - filtering happens automatically
- **Import Command**: Enhanced `import_brevo_logs` to filter internal domains during CSV processing
  - Reduces database size by excluding test/internal emails from the start
  - Improves import performance by skipping unnecessary records
- **Webhook Processing**: Updated webhook handler to filter internal domains in real-time
  - Prevents test emails from affecting production analytics
  - Reduces database writes for non-production events

### Technical Details
- All changes are backward compatible with existing configurations
- Domain filtering is optional - package works without `EXCLUDED_RECIPIENT_DOMAINS` configuration
- Custom manager ensures filtering works with all Django ORM query methods (filter, exclude, annotate, etc.)
- Statistics recalculation is automatically triggered after cleanup operations

## [0.1.1] - 2026-01-22

### Changed
- Updated README.md to remove all Supabase references
- Updated documentation to reflect Django-native architecture
- Added comprehensive setup instructions for DRF and CORS
- Added management commands documentation
- Updated troubleshooting section for current architecture

### Fixed
- Multi-client blacklist filtering: now correctly filters by ALLOWED_SENDERS and local database
- Emails with empty senderEmail (hard bounces) now properly included when in local DB
- Prevents showing blacklisted emails from other clients on shared Brevo accounts

## [0.1.0] - 2026-01-22

### Added
- Initial release of django-brevo-analytics
- Django-native architecture with models stored in PostgreSQL
- Django REST Framework API endpoints for analytics data
- Vue.js Single Page Application (SPA) for interactive analytics viewing
- Real-time webhook integration for Brevo events
- Dashboard with KPI metrics:
  - Total emails sent, delivery rate, open rate, click rate
  - Bounced and blocked emails count
  - Recent messages list
- Message-level email tracking with status filtering
- Email detail modal with complete event timeline
- Blacklist management interface:
  - Check individual emails for blacklist status
  - View and manage all blacklisted emails
  - Integration with Brevo API for real-time blacklist data
  - Remove emails from blacklist directly from UI
- Internationalization (i18n) support:
  - English and Italian translations
  - JavaScript-based UI localization
  - Django model verbose names localization
- Historical data import from raw Brevo logs (CSV)
- Automatic bounce reason enrichment via Brevo API
- Statistics verification command against Brevo API
- DuckDB-based CSV import for efficient data processing
- JSONField-based event storage for optimal performance

### Technical Details
- Python 3.8+ support
- Django 4.2+ support
- Django REST Framework integration
- Vue.js 3 with Composition API
- Hash-based routing (Vue Router in-memory)
- HMAC signature validation for webhooks
- Denormalized statistics for fast queries
- Cached status fields for efficient filtering
- Multi-client filtering via ALLOWED_SENDERS configuration
- Modal-based UI for seamless navigation
- Comprehensive management commands:
  - `import_brevo_logs`: Import historical data from CSV
  - `verify_brevo_stats`: Verify statistics against Brevo API
