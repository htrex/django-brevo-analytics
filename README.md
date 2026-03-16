# Django Brevo Analytics

A reusable Django package that integrates transactional email analytics from Brevo directly into Django admin with an interactive Vue.js interface.

## Features

### Analytics Dashboard
- **KPI Metrics**: Total emails sent, delivery rate, open rate, click rate
- **Real-time Stats**: Bounced and blocked emails count
- **Recent Messages**: Last 20 sent messages with quick access
- **Interactive Vue.js SPA**: Fast, responsive interface with modal-based navigation

### Email Tracking
- **Message-level View**: All emails grouped by message with aggregate statistics
- **Email Detail Modal**: Complete event timeline for each recipient
- **Status Filtering**: Filter by delivered, opened, clicked, bounced, blocked
- **Event Timeline**: Chronological view of all email events with metadata

### Blacklist Management
- **Check Individual Emails**: Verify if an email is in Brevo's blacklist
- **Manage Blacklist**: View and manage all blacklisted emails
- **Brevo API Integration**: Real-time synchronization with Brevo
- **Remove from Blacklist**: Unblock emails directly from the UI

### Internationalization
- **Multi-language Support**: English and Italian translations
- **Localized UI**: All interface elements respect Django's `LANGUAGE_CODE`
- **Date Formatting**: Locale-aware date and time display

### Real-time Webhook Integration
- **Instant Updates**: Process Brevo events as they occur
- **Bearer Token Authentication**: Secure webhook authentication via Authorization header
- **Auto-enrichment**: Bounce reasons automatically fetched from Brevo API

### Historical Data Import
- **CSV Import**: Import historical email data from raw Brevo logs
- **DuckDB Processing**: Efficient bulk data processing
- **Bounce Enrichment**: Automatic bounce reason lookup during import
- **Statistics Verification**: Validate data against Brevo API

## Requirements

- Python 3.8+
- Django 4.2+ (including Django 5.x)
- Django REST Framework 3.14+
- PostgreSQL (for JSONField support)

## Installation

```bash
pip install django-brevo-analytics
```

## Quick Start

### 1. Add to INSTALLED_APPS

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
```

### 2. Configure Settings

```python
# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAdminUser',
    ],
}

# CORS (adjust for production)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
]

# Brevo Analytics Configuration
BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret',  # From Brevo dashboard
    'API_KEY': 'your-brevo-api-key',          # Optional, for bounce enrichment
    'ALLOWED_SENDERS': [                       # Filter emails by sender
        'info@yourproject.com',
        '@yourcompany.com',                    # Domain pattern: matches any sender
    ],
}
```

### 3. Run Migrations

```bash
python manage.py migrate brevo_analytics
```

### 4. Include URLs

```python
# your_project/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('brevo-analytics/', include('brevo_analytics.urls')),  # API endpoints for Vue.js frontend
]
```

**Note:** The API endpoints are mounted at `/brevo-analytics/` to serve the Vue.js SPA. The dashboard itself is accessed through Django admin (see step 6).

### 5. Set Up Brevo Webhook

Configure webhook in Brevo dashboard:
- URL: `https://yourdomain.com/brevo-analytics/webhook/`
- Events: All transactional email events
- Add webhook secret to settings

### 6. Access Dashboard

Navigate to `/admin/brevo_analytics/brevomessage/` (requires staff permissions)

## Management Commands

### Import Historical Data

```bash
python manage.py import_brevo_logs /path/to/brevo_logs.csv
```

Options:
- `--dry-run`: Preview import without saving
- `--clear`: Clear existing data before import

### Verify Statistics

```bash
python manage.py verify_brevo_stats
```

Compares local statistics with Brevo API to ensure data accuracy.

## Architecture

### Django-Native Design
- **Models**: Data stored directly in PostgreSQL via Django ORM
- **JSONField Events**: Email events stored as JSON array for optimal performance
- **Denormalized Stats**: Pre-calculated statistics for fast queries
- **Cached Status**: Current status field for efficient filtering

### REST API
- **Django REST Framework**: 6 API endpoints for dashboard and analytics
- **Admin-Only Access**: All endpoints require Django admin permissions
- **Serialized Data**: Optimized JSON responses for Vue.js frontend

### Vue.js SPA
- **Composition API**: Modern Vue 3 with reactivity
- **Hash-based Routing**: Client-side routing without server config
- **Modal Overlays**: Email details shown in modals, no page reloads
- **Responsive Design**: Mobile-friendly interface

### Security
- **Bearer Token Webhook Authentication**: Verify webhook authenticity via Authorization header
- **Admin Permissions**: All views require Django staff access
- **CORS Protection**: Configurable CORS for API endpoints
- **SQL Injection Safe**: Django ORM prevents SQL injection

## Configuration Options

### Required

- `WEBHOOK_SECRET`: Secret key from Brevo webhook configuration

### Optional

- `API_KEY`: Brevo API key for bounce enrichment and blacklist management
- `ALLOWED_SENDERS`: List of sender emails or domain patterns to filter (for multi-client accounts). Values starting with `@` match any sender from that domain (e.g., `'@yourcompany.com'`)
- `EXCLUDED_RECIPIENT_DOMAINS`: List of email domains to exclude from analytics (e.g., internal/test domains)
- `MESSAGE_GROUP_BY`: Grouping strategy — `'subject'` (default) or `'tag'` (see [Tag-Based Message Grouping](#tag-based-message-grouping))
- `MESSAGE_TAG_PREFIX`: Tag prefix for grouping (default: `'digest'`, only used when `MESSAGE_GROUP_BY = 'tag'`)
- `CLIENT_UID`: UUID for tracking client (defaults to generated UUID)

## Tag-Based Message Grouping

By default, emails are grouped into messages by subject line and sent date. For applications where email subjects are personalised per recipient (e.g. `"Report 2024-09-17 - ClientName"`), this causes each unique subject to create a separate message, fragmenting analytics.

Tag-based grouping solves this by using [Brevo tags](https://developers.brevo.com/docs/transactional-webhooks) instead of subjects for grouping.

### Grouping Configuration

```python
BREVO_ANALYTICS = {
    # ... other settings ...
    'MESSAGE_GROUP_BY': 'tag',       # Group by tag instead of subject
    'MESSAGE_TAG_PREFIX': 'digest',  # Match tags starting with this prefix
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `MESSAGE_GROUP_BY` | `'subject'` | Grouping strategy: `'subject'` (default) or `'tag'` |
| `MESSAGE_TAG_PREFIX` | `'digest'` | Prefix to identify the grouping tag (only used when `MESSAGE_GROUP_BY = 'tag'`) |

### Tag Format Convention

The sending application should set tags following a `{prefix}:{id}:{display_title}` convention:

```python
# Example using django-anymail
message = EmailMultiAlternatives(subject="Report - Acme Corp", ...)
message.tags = [
    "digest:42:Weekly Report 2024-09-17",  # Grouping tag
    "customer:15:Acme Corp",                # Optional extra tag
]
message.send()
```

- **`prefix`** — matches `MESSAGE_TAG_PREFIX` (e.g. `digest`)
- **`id`** — unique identifier for the logical send (prevents collisions on same-day sends with identical titles)
- **`display_title`** — human-readable title shown in the dashboard

### How It Works

1. Tags are extracted from the Brevo webhook payload or CSV export
2. All tags are stored on `BrevoEmail.tags` (regardless of grouping mode)
3. When `MESSAGE_GROUP_BY = 'tag'`:
   - The first tag matching the configured prefix is used as the `BrevoMessage.subject`
   - If no matching tag is found, falls back to the email subject (graceful degradation)
4. The API returns both `subject` (raw) and `display_subject` (human-readable, with prefix and ID stripped)

### Backward Compatibility

- Default behaviour is completely unchanged (`MESSAGE_GROUP_BY` defaults to `'subject'`)
- Existing installations require no configuration changes
- The `BrevoMessage` model is unchanged — no new fields, constraints, or migrations on that table
- Tags are always stored on `BrevoEmail` even in subject grouping mode, enabling future analytics

## Data Flow

```
Brevo → Webhook → Django Model → PostgreSQL
                       ↓
                   DRF API
                       ↓
                  Vue.js SPA
```

## Multi-Client Support

For shared Brevo accounts, use `ALLOWED_SENDERS` to filter:
- **Exact emails** (`'info@yourproject.com'`): match that address only (case-insensitive)
- **Domain patterns** (`'@yourcompany.com'`): match any sender from that domain (case-insensitive)
- Emails without sender info: included only if in local database
- This prevents showing other clients' data

## Development

### Clone Repository

```bash
git clone https://github.com/guglielmo/django-brevo-analytics.git
cd django-brevo-analytics
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Tests

```bash
python manage.py test brevo_analytics
```

### Build Package

```bash
python -m build
```

## Troubleshooting

### Webhook Not Working

- Verify `WEBHOOK_SECRET` matches Brevo configuration
- Check webhook URL is publicly accessible
- Review Django logs for authentication errors
- Test webhook with `curl` to check connectivity

### Empty Dashboard

- Run `import_brevo_logs` to import historical data
- Verify webhook is configured and receiving events
- Check `ALLOWED_SENDERS` filter isn't too restrictive
- Ensure migrations have been applied

### Blacklist Management Not Working

- Add `API_KEY` to `BREVO_ANALYTICS` settings
- Verify API key has correct permissions on Brevo
- Check network connectivity to Brevo API

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

See [AUTHORS.md](AUTHORS.md) for contributors.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

- Built with [Django](https://www.djangoproject.com/) and [Django REST Framework](https://www.django-rest-framework.org/)
- Frontend powered by [Vue.js 3](https://vuejs.org/)
- CSV processing with [DuckDB](https://duckdb.org/)

## Links

- [PyPI Package](https://pypi.org/project/django-brevo-analytics/)
- [GitHub Repository](https://github.com/guglielmo/django-brevo-analytics)
- [Issue Tracker](https://github.com/guglielmo/django-brevo-analytics/issues)
- [Changelog](CHANGELOG.md)
