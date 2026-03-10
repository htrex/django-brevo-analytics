# Tag-Based Message Grouping — Design Spec

**Date**: 2026-03-10
**Status**: Approved
**Context**: Integration of django-brevo-analytics into comin-monitoraggio (GitLab issue [#27](https://gitlab.openpolis.io/depp/comin/comin-monitoraggio/-/issues/27))

## Problem

The package groups emails into `BrevoMessage` records by `(subject, sent_date)`. This works well when all recipients of a logical send share the same subject line.

In applications where:
- email subjects are personalised per recipient (e.g. `"Report 2024-09-17 - ClientName"`)
- content editors can freely modify individual subjects before sending
- the separator between the common part and the personalised part is not reliable (client names may contain the same separator)

...the current grouping produces one `BrevoMessage` per unique subject, fragmenting analytics. A single logical send to 100 recipients becomes 100 separate "messages" in the dashboard.

## Solution

Allow grouping by **Brevo tag** instead of subject, configured via a new setting. Tags are set by the sending application (via Anymail or any Brevo integration), propagated by Brevo in webhook payloads and CSV exports, and follow a prefix convention for identification.

### Design Principles

- **Zero changes to BrevoMessage model** — no new fields, no constraint changes, no migrations on that table
- **Full backward compatibility** — default behaviour is identical to current; existing installations require no configuration changes
- **Convention over configuration** — tags use a `prefix:id:display` format; the package matches by prefix
- **Generic storage** — all tags are saved on BrevoEmail without imposed semantics; the consuming application decides what tags mean

## New Setting

```python
BREVO_ANALYTICS = {
    # ... existing settings ...
    "MESSAGE_GROUP_BY": "subject",   # default — current behaviour, unchanged
    # "tag" — group by the first tag matching MESSAGE_TAG_PREFIX
    "MESSAGE_TAG_PREFIX": "digest",  # only used when MESSAGE_GROUP_BY = "tag"
}
```

## Model Change

**BrevoEmail** — one new field:

```python
tags = models.JSONField(default=list, blank=True)
```

Stores the raw tag array from the Brevo webhook payload or CSV export. Always populated regardless of `MESSAGE_GROUP_BY` setting, so tag data is available for future analytics even in subject-grouping mode.

**BrevoMessage** — no changes. The existing `subject` field and `(subject, sent_date)` unique constraint remain as-is.

## Tag Format Convention

The sending application sets tags with a prefix convention:

```
{prefix}:{id}:{display_title}
```

Examples:
- `digest:42:Esito CDM 2024-09-17`
- `customer:15:Eni SpA`

The package does not enforce this format — it simply looks for a tag starting with the configured prefix.

## Grouping Logic

### When `MESSAGE_GROUP_BY = "subject"` (default)

No change. The webhook and CSV import use the email subject as the `subject` value in `BrevoMessage.objects.get_or_create(subject=X, sent_date=Y)`.

Tags are still saved on BrevoEmail for future use.

### When `MESSAGE_GROUP_BY = "tag"`

1. Extract the tag array from the webhook payload / CSV row
2. Find the first tag matching the configured prefix:
   ```python
   prefix = config.get("MESSAGE_TAG_PREFIX", "digest")
   group_tag = next((t for t in tags if t.startswith(f"{prefix}:")), None)
   ```
3. If found, use `group_tag` as the `subject` in `get_or_create`
4. If not found, fall back to the email subject (graceful degradation)

This means `BrevoMessage.subject` contains the full tag string (e.g. `"digest:42:Esito CDM 2024-09-17"`). The unique constraint `(subject, sent_date)` ensures uniqueness — the ID in the tag prevents collision when two sends have the same display title on the same day.

## Display Subject

The `BrevoMessageSerializer` adds a computed `display_subject` field that strips the `{prefix}:{id}:` portion:

```python
def get_display_subject(self, obj):
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    if config.get('MESSAGE_GROUP_BY') == 'tag':
        prefix = config.get('MESSAGE_TAG_PREFIX', 'digest')
        tag_prefix = f"{prefix}:"
        if obj.subject.startswith(tag_prefix):
            # Strip "prefix:" then strip "id:"
            remainder = obj.subject[len(tag_prefix):]
            if ':' in remainder:
                return remainder.split(':', 1)[1]
            return remainder
    return obj.subject
```

When `MESSAGE_GROUP_BY = "subject"`, `display_subject` equals `subject` — no transformation.

## Files to Modify

### brevo_analytics/models.py
- Add `tags` field to BrevoEmail

### brevo_analytics/webhooks.py
- Extract `tags` from payload: `payload.get('tags', [])`
- Save tags on BrevoEmail
- When `MESSAGE_GROUP_BY = "tag"`: use matched tag as subject in `get_or_create`
- Fallback to email subject if no matching tag found

### brevo_analytics/management/commands/import_brevo_logs.py
- Read `tag` column from CSV in DuckDB query
- Store as single-element list in BrevoEmail.tags
- Same grouping logic as webhook

### brevo_analytics/serializers.py
- Add `display_subject` SerializerMethodField to BrevoMessageSerializer

### brevo_analytics/migrations/0007_brevoemail_tags.py
- Add `tags` JSONField to BrevoEmail (default=list)

### brevo_analytics/tests.py
- Test: webhook saves tags on BrevoEmail
- Test: webhook with MESSAGE_GROUP_BY="tag" creates BrevoMessage with tag as subject
- Test: webhook with MESSAGE_GROUP_BY="subject" (default) behaviour unchanged
- Test: webhook with MESSAGE_GROUP_BY="tag" but no matching tag falls back to subject
- Test: display_subject strips prefix correctly
- Test: CSV import reads tag column and applies grouping

### Documentation
- README.md — add Tag-Based Grouping section with configuration and usage examples
- CHANGELOG.md — document new feature

## Migration Safety

- Single migration: add nullable JSONField with default=list to BrevoEmail
- No data migration needed — existing records get empty list
- No changes to BrevoMessage table
- Fully reversible

## What Does NOT Change

- BrevoMessage model (fields, constraints, indexes, methods)
- BrevoEmail unique constraint `(brevo_message_id, recipient_email)`
- BrevoEmailManager (custom filtering logic)
- API views (endpoints, permissions, query logic)
- Admin SPA (Vue.js frontend)
- All existing management commands
- Webhook authentication and sender verification
- BLACKLIST_ONLY_MODE behaviour
- Internationalization (i18n.py)
