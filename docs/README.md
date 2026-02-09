# Brevo Analytics Documentation

**Architecture:** Django native models + Direct Brevo webhooks + Vue.js SPA

**Last Updated:** 2026-01-21

---

## 📚 Current Documentation

### 1. Implementation Plan (START HERE)
**File:** `plans/2026-01-21-spa-implementation-plan.md`

Complete step-by-step implementation guide for the Django-native architecture with Vue.js SPA frontend.

**What's inside:**
- 6 implementation phases (~12 hours total)
- Complete code for all files (copy-paste ready)
- API endpoints specification
- Vue.js SPA structure
- Webhook integration
- Historical data import
- Testing & deployment

**Status:** ✅ Ready for implementation

### 2. Installation Guide
**File:** `INSTALLATION.md`

Quick start guide for installing and running the package.

**Status:** 🔄 Needs update for new architecture

---

## 🏗️ Architecture Overview

### Current Architecture (2026-01-21+)
```
Brevo Webhooks
    ↓
Django Webhook Endpoint
    ↓
Django Models (PostgreSQL/SQLite)
    ├─ BrevoMessage (subject + sent_date)
    └─ Email (with events as JSONField)
    ↓
Django REST Framework API
    ↓
Vue.js SPA (served in Django Admin)
```

**Key Features:**
- ✅ Real-time webhook processing
- ✅ Events stored as JSON array (denormalized)
- ✅ Single database query per view
- ✅ Modal-based email details (no page reload)
- ✅ No temporal filters (all historical data)
- ✅ Zero external dependencies

### Models

**BrevoMessage:**
- Identified by: `subject` + `sent_date` (unique together)
- Stores: Aggregated stats (sent, delivered, opened, clicked, bounced, blocked)
- Example: "Calendario Eventi - 2026-01-22" with 148 emails sent

**Email:**
- Belongs to: BrevoMessage (ForeignKey)
- Stores: `events` as JSONField array
- Status: Cached in `current_status` field (updated on event add)

### API Endpoints

```
GET /api/dashboard/                      # KPI + last 20 messages
GET /api/messages/                       # All messages (for "show all")
GET /api/messages/:id/emails/            # Emails for specific message
GET /api/emails/bounced/                 # All bounced emails (cross-message)
GET /api/emails/blocked/                 # All blocked emails (cross-message)
GET /api/emails/:id/                     # Single email detail (for modal)

POST /webhook/                           # Brevo webhook endpoint
```

### SPA Routes (Hash-based)

```
#/                                       # Dashboard
#/messages/:id/emails                    # Emails for message
#/emails/bounced                         # Global bounced emails
#/emails/blocked                         # Global blocked emails

(Modal overlay, no route change)        # Email detail timeline
```

---

## 🔧 Blacklist-Only Mode

For use cases where email analytics are not needed (e.g., variable subjects per client), you can enable blacklist-only mode.

### Configuration

```python
BREVO_ANALYTICS = {
    'API_KEY': 'your-brevo-api-key',  # Required for blacklist access
    'BLACKLIST_ONLY_MODE': True,      # Enable blacklist-only mode
}
```

### Behavior

When `BLACKLIST_ONLY_MODE = True`:

- **Webhook**: Disabled (returns 404 with informative message)
- **Import**: Disabled (command exits with error message)
- **Admin Menu**: Shows only "Blacklist Management" (hides "Message Analysis")
- **Database**: Tables created but unused (no data stored)
- **Blacklist SPA**: Works normally via direct Brevo API queries

### Use Cases

- **Variable subjects**: Email subjects customized per client (e.g., Comin)
  - Standard grouping by subject becomes impractical
  - Only blacklist management needed

- **Simple blacklist management**: Only need to check/remove blocked emails
  - No need for delivery/open/click statistics
  - Direct API access is sufficient

- **No analytics required**: Don't need email campaign analytics
  - Lighter deployment
  - No historical data storage

### Required Settings

- **`API_KEY`**: Required for Brevo API access
- **`ALLOWED_SENDERS`**: Optional (for multi-tenant filtering of blacklist entries)

### Example

```python
# settings.py
BREVO_ANALYTICS = {
    'API_KEY': 'xkeysib-abc123...',
    'BLACKLIST_ONLY_MODE': True,
    'ALLOWED_SENDERS': ['info@example.com'],  # Optional: filter blacklist by sender
}
```

After configuring, restart Django and access only:
- **Admin**: `/admin/brevo_analytics/brevoemail/` (Blacklist Management)

The Message Analysis menu will be hidden automatically.

---

## 🗄️ Archived Documentation

**Location:** `archive/`

Contains obsolete documentation from the Supabase-based architecture (pre-2026-01-21).

See `archive/README.md` for details on what was archived and why.

---

## 📋 Implementation Checklist

Follow this order:

- [ ] **Phase 1:** Django Models & Migrations (2h)
  - Create `BrevoMessage` and `Email` models
  - Run migrations
  - Delete old Supabase code

- [ ] **Phase 2:** Django REST Framework API (3h)
  - Install DRF
  - Create serializers
  - Create 6 API endpoints
  - Configure URLs

- [ ] **Phase 3:** Brevo Webhook Integration (1h)
  - Create webhook handler
  - Test with ngrok
  - Configure in Brevo dashboard

- [ ] **Phase 4:** Vue.js SPA Frontend (4h)
  - Create SPA template
  - Write Vue components
  - Style with CSS
  - Test navigation

- [ ] **Phase 5:** Historical Data Import (1h)
  - Create management command
  - Import CSV data
  - Update message stats

- [ ] **Phase 6:** Testing & Deployment (1h)
  - Write unit tests
  - Production checklist
  - Deploy

**Total estimated time:** 12 hours

---

## 🔧 Configuration

**Required settings:**

```python
# settings.py
INSTALLED_APPS = [
    'rest_framework',
    'corsheaders',
    'brevo_analytics',
]

BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret',  # From Brevo dashboard
    'CLIENT_UID': 'your-client-uuid',         # For tracking
}
```

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install djangorestframework django-cors-headers

# 2. Run migrations
python manage.py migrate brevo_analytics

# 3. Import historical data (optional)
python manage.py import_brevo_csv emails_import.csv email_events_import.csv

# 4. Configure Brevo webhook
# URL: https://your-domain.com/admin/brevo_analytics/webhook/

# 5. Access SPA
# http://localhost:8000/admin/brevo_analytics/brevomessage/
```

---

## 📞 Support

For issues or questions:
- Check `plans/2026-01-21-spa-implementation-plan.md` for detailed implementation steps
- Review archived docs if needed for historical context

---

## 📝 Notes

### Why Django Native vs Supabase?

**Advantages:**
- ✅ **Simpler:** Standard Django patterns, no external API
- ✅ **Cheaper:** Zero external costs (no Supabase)
- ✅ **Faster:** Direct ORM queries, no HTTP overhead
- ✅ **Real-time:** Webhooks go directly to Django
- ✅ **Isolated:** Each Django instance has its own database

**Trade-offs:**
- ❌ No multi-tenant out-of-box (one client per instance)
- ❌ No automatic API layer (but we build our own with DRF)

### Why JSONField for Events?

**Advantages:**
- ✅ **1 query instead of 2:** Email + events in single SELECT
- ✅ **No JOINs:** Better performance at scale
- ✅ **Flexible:** Easy to add new event fields
- ✅ **Atomic updates:** Append to array in one operation

**Best for:**
- Read-heavy analytics (our use case)
- Immutable event logs (append-only)
- Event visualization (timeline)

**Not good for:**
- Querying across events (but we cache status)
- Updating individual events (but they're immutable)
