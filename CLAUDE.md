# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`django-brevo-analytics` is a reusable Django package that integrates transactional email analytics from Brevo directly into Django admin. It uses Django-native models with events stored as JSONField for optimal performance.

**Architecture:** Django Models + DRF API + Vue.js SPA + Direct Brevo Webhooks

**Date:** 2026-01-21 (Complete refactoring from Supabase to Django-native)

## Development Setup

This is a **Django package** (not a standalone project). Development is done against the `infoparlamento` project located at `~/Workspace/infoparlamento`.

### Running the Development Project

To execute any Django management command for testing:

```bash
# 1. Ensure docker-compose stack is running
cd ~/Workspace/infoparlamento
docker compose -f local.yml up -d

# 2. Activate virtualenv and run commands
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py <command>
```

**Required services (local.yml):**
- PostgreSQL (port 5432)
- Redis (port 6379)
- MailHog (ports 1025, 8025)

### Common Development Commands

```bash
# Create migrations
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py makemigrations brevo_analytics

# Apply migrations
DJANGO_READ_DOT_ENV_FILE=1 python manage.py migrate brevo_analytics

# Run tests
DJANGO_READ_DOT_ENV_FILE=1 python manage.py test brevo_analytics

# Import historical data from raw Brevo logs
# (automatically enriches bounces if API key is configured)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /path/to/logs_infoparlamento_202512_today.csv

# Verify statistics against Brevo API (reads API key from settings if not provided)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py verify_brevo_stats

# Run development server (from infoparlamento project)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py runserver
```

### Building Package

```bash
cd /home/gu/Workspace/lab.prototypes/brevo-analytics
python setup.py sdist bdist_wheel
```

## Architecture

### Django-Native Architecture (2026-01-21+)

**Data Flow:**
```
Brevo Webhooks → Django Webhook Endpoint → Django Models (PostgreSQL) → DRF API → Vue.js SPA
```

**Key Components:**

1. **Django Models** (`brevo_analytics/models.py`):
   - `BrevoMessage`: Identified by `subject` + `sent_date` (unique together)
   - `Email`: Contains events as JSONField array, with cached `current_status`
   - Direct database access via Django ORM
   - Denormalized statistics for performance

2. **REST API** (`brevo_analytics/api_views.py`, `brevo_analytics/serializers.py`):
   - Django REST Framework endpoints
   - 6 API endpoints for dashboard, messages, emails
   - Admin-only access via `IsAdminUser` permission

3. **Vue.js SPA** (`brevo_analytics/static/brevo_analytics/js/app.js`):
   - Served within Django admin interface
   - Hash-based routing (Vue Router)
   - Modal overlays for email details (no page reloads)
   - Reactive KPI filters and search

4. **Brevo Webhook** (`brevo_analytics/webhooks.py`):
   - Real-time event processing
   - HMAC signature validation
   - Automatic status updates and statistics recalculation

### Data Models

**BrevoMessage:**
```python
subject = TextField()                    # Email subject
sent_date = DateField()                  # Date of sending
# Denormalized statistics
total_sent, total_delivered, total_opened, total_clicked
total_bounced, total_blocked
delivery_rate, open_rate, click_rate

unique_together = [['subject', 'sent_date']]
```

**Email:**
```python
brevo_message_id = CharField()           # Brevo's unique ID
recipient_email = EmailField()
sent_at = DateTimeField()
events = JSONField(default=list)         # Array of event objects
current_status = CharField()             # Cached for fast queries

# Events structure:
# [
#   {"type": "sent", "timestamp": "2026-01-21T10:00:00Z"},
#   {"type": "delivered", "timestamp": "2026-01-21T10:01:23Z"},
#   {"type": "opened", "timestamp": "2026-01-21T11:30:00Z", "ip": "..."}
# ]
```

### API Endpoints

```
GET /admin/brevo_analytics/api/dashboard/
    → KPI + last 20 messages

GET /admin/brevo_analytics/api/messages/
    → All messages (for "show all")

GET /admin/brevo_analytics/api/messages/:id/emails/?status=bounced
    → Emails for specific message (with optional status filter)

GET /admin/brevo_analytics/api/emails/bounced/
    → All bounced emails (cross-message)

GET /admin/brevo_analytics/api/emails/blocked/
    → All blocked emails (cross-message)

GET /admin/brevo_analytics/api/emails/:id/
    → Single email detail with full event timeline

POST /admin/brevo_analytics/webhook/
    → Brevo webhook endpoint (HMAC validated)
```

### SPA Routes (Hash-based)

```
#/                                      → Dashboard
#/messages/:id/emails                   → Emails for message
#/messages/:id/emails?status=bounced    → Filtered emails
#/emails/bounced                        → Global bounced emails
#/emails/blocked                        → Global blocked emails

(Modal overlay, no route change)       → Email detail timeline
```

## Configuration

### Required Django Settings

```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'corsheaders',
    'brevo_analytics',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Add at top
    # ... other middleware
]

# DRF settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAdminUser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
}

# CORS (development)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
]

# Brevo Analytics configuration
BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret-here',  # From Brevo dashboard
    'CLIENT_UID': 'your-client-uuid',              # For tracking
    'API_KEY': 'your-brevo-api-key',               # Optional: for bounce enrichment

    # CRITICAL: Multi-tenant security - only process events from your senders
    'ALLOWED_SENDERS': ['info@infoparlamento.it'], # REQUIRED: Your authorized sender email(s)

    # Exclude internal test/error emails
    'EXCLUDED_RECIPIENT_DOMAINS': [                # Exclude internal domains
        'openpolis.it',
        'deppsviluppo.org'
    ],
}
```

### Include URLs

```python
# your_project/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin/brevo_analytics/', include('brevo_analytics.urls')),
]
```

## Blacklist-Only Mode

For use cases where email analytics are not needed (e.g., variable subjects per client like Comin), you can enable blacklist-only mode.

### Configuration

Add to your Django settings:

```python
BREVO_ANALYTICS = {
    'API_KEY': 'your-brevo-api-key',  # Required for blacklist access
    'BLACKLIST_ONLY_MODE': True,      # Enable blacklist-only mode
}
```

### What Changes

When `BLACKLIST_ONLY_MODE = True`:

1. **Admin Interface**:
   - ✅ "Blacklist Management" visible
   - ❌ "Message Analysis" hidden

2. **Webhook**:
   - Returns 404 with message: `"Webhook is disabled in BLACKLIST_ONLY_MODE"`
   - No event processing

3. **Import Command**:
   - `import_brevo_logs` exits with error
   - Shows: `"Import is disabled in BLACKLIST_ONLY_MODE"`

4. **Database**:
   - Tables (`brevo_messages`, `brevo_emails`) are created but unused
   - No data stored locally

5. **Blacklist SPA**:
   - Works normally
   - Queries Brevo API directly for blacklist data
   - No dependency on local database

### Use Cases

- **Variable Subjects**: Email subjects customized per client (grouping by subject impractical)
- **Simple Blacklist Management**: Only need to check/remove blocked emails
- **No Analytics**: Don't need delivery/open/click statistics

### Example Configuration

```python
# settings.py for blacklist-only deployment
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'rest_framework',
    'brevo_analytics',
]

BREVO_ANALYTICS = {
    'API_KEY': 'xkeysib-abc123...',        # Required
    'BLACKLIST_ONLY_MODE': True,           # Enable mode
    'ALLOWED_SENDERS': ['info@comin.it'],  # Optional: filter blacklist
}
```

### Verification

After enabling blacklist-only mode:

```bash
# Start Django dev server
python manage.py runserver

# Access admin
# You'll see only: "Blacklist Management"
# "Message Analysis" will be hidden
```

**Webhook test** (should return 404):
```bash
curl -X POST http://localhost:8000/admin/brevo_analytics/webhook/ \
  -H "Content-Type: application/json" \
  -d '{"event": "test"}'
# Response: {"status": "disabled", "message": "..."}
```

**Import test** (should exit with error):
```bash
python manage.py import_brevo_logs test.csv
# Output: "Import is disabled in BLACKLIST_ONLY_MODE..."
```

### Disabled Commands

When `BLACKLIST_ONLY_MODE = True`, these management commands are disabled:

- **`import_brevo_logs`** - Historical data import from CSV
- **`clean_internal_emails`** - Database cleanup of internal domains
- **`recalculate_stats`** - Statistics recalculation for messages
- **`verify_brevo_stats`** - API verification against local database

All commands will exit immediately with a clear error message:
```
This command is disabled in BLACKLIST_ONLY_MODE.
Database tables are unused in this mode. Use Blacklist Management to access data from Brevo API.
```

## File Structure

```
brevo_analytics/
├── models.py                    # Django models (BrevoMessage, Email)
├── admin.py                     # Django admin registration + SPA view
├── serializers.py               # DRF serializers
├── api_views.py                 # DRF API endpoints
├── webhooks.py                  # Brevo webhook handler
├── urls.py                      # URL configuration
├── tests.py                     # Unit tests
├── migrations/                  # Django migrations
│   └── 0001_initial.py
├── management/                  # Management commands
│   └── commands/
│       ├── import_brevo_logs.py # Main import command (DuckDB-based)
│       ├── verify_brevo_stats.py # Statistics verification tool
│       └── archive/             # Archived obsolete commands
├── templates/                   # Django templates
│   └── brevo_analytics/
│       └── spa.html             # SPA entry point
├── static/                      # Frontend assets
│   └── brevo_analytics/
│       ├── css/
│       │   └── app.css          # SPA styles
│       └── js/
│           └── app.js           # Vue.js SPA
└── templatetags/
    └── brevo_filters.py         # Template filters (legacy)

docs/
├── README.md                    # Main documentation
├── INSTALLATION.md              # Installation guide
├── plans/
│   └── 2026-01-21-spa-implementation-plan.md
└── archive/                     # Obsolete Supabase docs
    ├── README.md
    ├── sql/                     # Old Supabase schema
    └── [archived docs]

Root files:
├── emails_import.csv            # Historical data for import
├── email_events_import.csv
└── requirements.txt
```

## Key Design Decisions

1. **Django-Native vs Supabase**: Complete refactoring to eliminate external dependencies and reduce costs. All data stored directly in Django database.

2. **Events as JSONField**: Denormalized approach stores events as JSON array in Email model. Enables single-query access to complete email history.

3. **Cached Status**: `current_status` field pre-calculated and indexed for fast filtering without parsing JSON.

4. **No Temporal Filters**: SPA shows all historical data (no date range filters). Simplifies UX and ensures complete visibility.

5. **Modal-Based Details**: Email event timeline displayed in modal overlay to avoid page navigation and maintain context.

6. **Single-Tenant**: One client per Django instance (no multi-tenant complexity). Client ID stored in settings.

7. **Internal Domain Filtering**: Emails sent to internal domains (configurable via `EXCLUDED_RECIPIENT_DOMAINS`) are automatically excluded from import, webhooks, and queries. This prevents internal error notifications and test emails from skewing production statistics.

8. **Multi-Tenant Security**: Sender filtering (`ALLOWED_SENDERS`) prevents webhook events and data from other clients on shared Brevo accounts from contaminating your analytics. All queries automatically filter by authorized senders.

## Common Development Tasks

### Running Tests

**Standalone test runner (recommended for local development):**

```bash
cd /home/gu/Workspace/lab.prototypes/brevo-analytics
python runtests.py
```

This uses the standalone test configuration in `test_settings.py` with SQLite, no external Django project required.

**Alternative: Testing in development project:**

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py test brevo_analytics
```

### Database Migration for sender_email Field

**⚠️ REQUIRED for v0.2.1+**: The BrevoEmail model now includes a `sender_email` field for multi-tenant security. You must create and apply this migration:

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate

# Create migration for the new field
DJANGO_READ_DOT_ENV_FILE=1 python manage.py makemigrations brevo_analytics

# Apply the migration
DJANGO_READ_DOT_ENV_FILE=1 python manage.py migrate brevo_analytics
```

The field is nullable to maintain backward compatibility with existing data. New imports and webhook events will populate this field automatically.

### Importing Historical Data from Raw Logs

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate

# Test import with dry-run (no data changes)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /home/gu/Workspace/lab.prototypes/brevo-analytics/logs_infoparlamento_202512_today.csv \
  --dry-run

# Actual import (automatically enriches bounces if API key is configured)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /home/gu/Workspace/lab.prototypes/brevo-analytics/logs_infoparlamento_202512_today.csv

# Clear existing data and reimport
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /home/gu/Workspace/lab.prototypes/brevo-analytics/logs_infoparlamento_202512_today.csv \
  --clear
```

**Note:** The import command automatically excludes emails sent to internal domains configured in `EXCLUDED_RECIPIENT_DOMAINS` (default: openpolis.it, deppsviluppo.org).

### Cleaning Existing Internal Domain Emails

If you have already imported data that includes emails to internal domains, use this command to clean them:

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate

# Preview what would be deleted (dry-run)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py clean_internal_emails --dry-run

# Actually delete internal emails and recalculate statistics
DJANGO_READ_DOT_ENV_FILE=1 python manage.py clean_internal_emails
```

This command will:
- Find all emails sent to excluded domains (openpolis.it, deppsviluppo.org)
- Delete them from the database
- Recalculate statistics for affected messages
- Delete messages with zero remaining emails

### Recalculating Message Statistics

If you need to recalculate statistics for all messages (e.g., after a bug fix or data cleanup):

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate

# Recalculate all messages
DJANGO_READ_DOT_ENV_FILE=1 python manage.py recalculate_stats

# Recalculate specific message by ID
DJANGO_READ_DOT_ENV_FILE=1 python manage.py recalculate_stats --message-id 123
```

This command will:
- Count emails with 'sent' events in their event timeline
- Update delivery_rate, open_rate, and click_rate
- Show before/after statistics
- Identify messages with zero sent emails for cleanup

### Testing Webhook Locally

```bash
# Terminal 1: Start Django dev server
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py runserver

# Terminal 2: Use ngrok for external access
ngrok http 8000

# Configure ngrok URL in Brevo dashboard:
# https://abc123.ngrok.io/admin/brevo_analytics/webhook/
```

### Testing Webhook with curl

```bash
curl -X POST http://localhost:8000/admin/brevo_analytics/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "event": "delivered",
    "message-id": "<test123@smtp-relay.mailin.fr>",
    "email": "test@example.com",
    "subject": "Test Email",
    "ts_event": 1737468000
  }'
```

### Accessing the SPA

Once the development server is running:
```
http://localhost:8000/admin/brevo_analytics/brevomessage/
```

## Historical Note

This project was completely refactored on 2026-01-21 from a Supabase-based architecture to Django-native. Old documentation is archived in `docs/archive/`.

## Status Hierarchy

Events determine email status based on this hierarchy (highest wins):
```
clicked > opened > delivered > bounced > blocked > deferred > unsubscribed > sent
```

## Event Types

Mapped from Brevo webhook events:
- `request` → `sent`
- `delivered` → `delivered`
- `hard_bounce`, `soft_bounce` → `bounced`
- `blocked` → `blocked`
- `spam` → `spam`
- `unsubscribe` → `unsubscribed`
- `opened` → `opened`
- `click` → `clicked`
- `deferred` → `deferred`

## Release and Deployment

### Package Information
- **PyPI Package**: https://pypi.org/project/django-brevo-analytics/
- **GitHub Repository**: https://github.com/guglielmo/django-brevo-analytics
- **Automated Deployment**: GitHub Actions publishes to PyPI on release

### Release Process

#### 1. Update Version

Edit `brevo_analytics/__init__.py`:
```python
__version__ = '0.2.0'  # Update to new version
```

Edit `pyproject.toml`
```
[project]                                                                                                                                    
 name = "django-brevo-analytics"                                                                                                              
 version = "0.2.4"                                                                                                                             
 ...
```

#### 2. Update CHANGELOG.md

Add release notes in [Keep a Changelog](https://keepachangelog.com/) format:
```markdown
## [0.2.0] - 2026-01-XX

### Added
- New feature description

### Changed
- Change description

### Fixed
- Fix description
```

#### 3. Commit and Tag

```bash
cd /home/gu/Workspace/lab.prototypes/brevo-analytics

# Commit version bump
git add brevo_analytics/__init__.py CHANGELOG.md
git commit -m "Release v0.2.0"

# Create and push tag
git tag v0.2.0
git push origin main v0.2.0
```

#### 4. Create GitHub Release

```bash
# Create release with GitHub CLI
gh release create v0.2.0 \
  --title "v0.2.0" \
  --notes "Brief description or link to CHANGELOG"
```

**GitHub Actions will automatically:**
1. Build the package (`python -m build`)
2. Validate package with twine
3. Publish to PyPI using `PYPI_API_TOKEN` secret

#### 5. Monitor Deployment

```bash
# Check GitHub Actions workflow
gh run list --limit 3

# View specific run details
gh run view <run-id>
```

### Manual Release (Alternative)

If GitHub Actions fails or you need to publish manually:

```bash
cd /home/gu/Workspace/lab.prototypes/brevo-analytics

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Install build tools
pip install build twine

# Build package
python -m build

# Check package
twine check dist/*

# Upload to PyPI
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=<your-pypi-token>  # Token from ~/.pypirc or pypi.org
twine upload dist/*
```

### Version Numbering

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR** (1.0.0): Breaking changes, incompatible API
- **MINOR** (0.2.0): New features, backwards-compatible
- **PATCH** (0.1.1): Bug fixes, backwards-compatible

### GitHub Actions Configuration

The release workflow is defined in `.github/workflows/publish.yml`:
- Triggers on: GitHub release published
- Requires secret: `PYPI_API_TOKEN` (PyPI API token)
- Builds wheel and source distribution
- Validates with twine
- Publishes to PyPI

### PyPI Token Management

The PyPI token is stored as a GitHub secret:
- Name: `PYPI_API_TOKEN`
- Value: API token from https://pypi.org/manage/account/token/
- Scope: Entire account (for first upload) or project-specific

To update the token:
```bash
# Interactive (will prompt for token)
gh secret set PYPI_API_TOKEN

# Or from stdin
echo "pypi-YOUR-TOKEN-HERE" | gh secret set PYPI_API_TOKEN
```

**Note**: Never commit PyPI tokens to git. Keep them in:
- GitHub Secrets (for CI/CD)
- `~/.pypirc` (for local manual uploads)
- Password manager (for backup)

### Testing Package Installation

After publishing to PyPI:
```bash
# Create test environment
python -m venv test_env
source test_env/bin/activate

# Install from PyPI
pip install django-brevo-analytics==0.2.0

# Verify installation
python -c "import brevo_analytics; print(brevo_analytics.__version__)"
```

### Troubleshooting Releases

**GitHub Actions fails with 403 Forbidden:**
- Verify `PYPI_API_TOKEN` secret is correctly set
- Check token hasn't expired on pypi.org
- Ensure token has upload permissions

**Package already exists on PyPI:**
- Cannot re-upload same version
- Increment version number and release again

**Build warnings about license:**
- Warnings about `project.license` format are safe to ignore
- Package will still publish successfully
