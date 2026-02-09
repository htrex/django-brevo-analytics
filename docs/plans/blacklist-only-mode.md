# Plan: Blacklist-Only Mode

**Date**: 2026-02-09
**Goal**: Add configuration flag to use only Blacklist Management without analytics/webhook sync

## Context

Some use cases (like Comin) have variable email subjects (customized per client), making message grouping by subject impractical. For these cases, we only need the Blacklist Management features without full email analytics.

## Solution

Add single configuration flag `BLACKLIST_ONLY_MODE` that:
- Disables webhook endpoint
- Hides "Message Analysis" from admin menu
- Shows only "Blacklist Management" in admin
- Blacklist SPA works normally using Brevo API directly
- Database tables (BrevoMessage, BrevoEmail) are created but unused

## Implementation Steps

### 1. Update Configuration (Settings)

**File**: Documentation
**Changes**: Document new setting in CLAUDE.md and README

```python
BREVO_ANALYTICS = {
    # Existing settings...
    'WEBHOOK_SECRET': 'your-secret',
    'API_KEY': 'your-key',
    'ALLOWED_SENDERS': ['info@example.com'],

    # NEW: Blacklist-only mode (no analytics, no webhook sync)
    'BLACKLIST_ONLY_MODE': False,  # Set to True to disable analytics
}
```

**When `BLACKLIST_ONLY_MODE = True`**:
- Webhook returns 404
- Message Analysis hidden from admin
- Only Blacklist Management visible
- Import commands disabled
- Blacklist SPA uses only Brevo API

### 2. Modify Admin Registration

**File**: `brevo_analytics/admin.py`

**Changes**:
- Read `BLACKLIST_ONLY_MODE` from settings
- Register `BrevoMessageAdmin` only if `BLACKLIST_ONLY_MODE = False`
- Always register `BrevoEmailAdmin` (Blacklist Management)

**Implementation**:
```python
# At the end of admin.py
brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
blacklist_only = brevo_config.get('BLACKLIST_ONLY_MODE', False)

if not blacklist_only:
    admin.site.register(BrevoMessage, BrevoMessageAdmin)

# Always register Blacklist Management
admin.site.register(BrevoEmail, BrevoEmailAdmin)
```

**Note**: Need to refactor to conditional registration instead of `@admin.register()` decorator

### 3. Modify Webhook Endpoint

**File**: `brevo_analytics/webhooks.py`

**Changes**:
- Check `BLACKLIST_ONLY_MODE` at start of `brevo_webhook()` function
- If enabled, return HTTP 404 or informative message
- Add logging

**Implementation**:
```python
@csrf_exempt
@require_POST
def brevo_webhook(request):
    """
    Brevo webhook endpoint for real-time event processing.

    Disabled when BLACKLIST_ONLY_MODE is enabled.
    """
    config = getattr(settings, 'BREVO_ANALYTICS', {})

    # Check if blacklist-only mode
    if config.get('BLACKLIST_ONLY_MODE', False):
        logger.warning("Webhook called but BLACKLIST_ONLY_MODE is enabled")
        return JsonResponse({
            'status': 'disabled',
            'message': 'Webhook is disabled in BLACKLIST_ONLY_MODE. Use Blacklist Management for direct API access.'
        }, status=404)

    # ... rest of existing webhook code
```

### 4. Update Import Command

**File**: `brevo_analytics/management/commands/import_brevo_logs.py`

**Changes**:
- Check `BLACKLIST_ONLY_MODE` at start of `handle()` method
- If enabled, print error and exit
- Add helpful message

**Implementation**:
```python
def handle(self, *args, **options):
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

    # ... rest of existing import code
```

### 5. Update Documentation

**Files**:
- `docs/README.md`
- `brevo_analytics/CLAUDE.md`

**Changes**:
- Add section "Blacklist-Only Mode"
- Document configuration flag
- Explain use cases (variable subjects, no analytics needed)
- Document behavior differences

**Content**:
```markdown
## Blacklist-Only Mode

For use cases where email analytics are not needed (e.g., variable subjects per client),
you can enable blacklist-only mode:

### Configuration

```python
BREVO_ANALYTICS = {
    'API_KEY': 'your-brevo-api-key',  # Required for blacklist access
    'BLACKLIST_ONLY_MODE': True,
}
```

### Behavior

When enabled:
- **Webhook**: Disabled (returns 404)
- **Import**: Disabled (command exits with error)
- **Admin Menu**: Shows only "Blacklist Management"
- **Database**: Tables created but unused
- **Blacklist SPA**: Works normally via Brevo API

### Use Cases

- **Variable subjects**: Email subjects customized per client (e.g., Comin)
- **Simple blacklist management**: Only need to check/remove blocked emails
- **No analytics required**: Don't need delivery/open/click statistics

### Required Settings

- `API_KEY`: Required for Brevo API access
- `ALLOWED_SENDERS`: Optional (for multi-tenant filtering)
```

### 6. Add Tests

**File**: `brevo_analytics/tests.py`

**Changes**:
- Add test case for blacklist-only mode
- Test webhook returns 404
- Test import command exits with error
- Test admin registration

**Implementation**:
```python
class BlacklistOnlyModeTestCase(TestCase):
    def test_webhook_disabled_in_blacklist_only_mode(self):
        """Webhook should return 404 in blacklist-only mode"""
        with self.settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True}):
            response = self.client.post('/admin/brevo_analytics/webhook/', {})
            self.assertEqual(response.status_code, 404)

    def test_import_disabled_in_blacklist_only_mode(self):
        """Import command should exit with error in blacklist-only mode"""
        with self.settings(BREVO_ANALYTICS={'BLACKLIST_ONLY_MODE': True}):
            out = StringIO()
            call_command('import_brevo_logs', 'test.csv', stdout=out)
            self.assertIn('disabled', out.getvalue().lower())
```

## Testing Plan

1. **Manual Testing**:
   - Set `BLACKLIST_ONLY_MODE = True` in infoparlamento settings
   - Restart dev server
   - Verify "Message Analysis" hidden from admin menu
   - Verify "Blacklist Management" visible
   - Verify Blacklist SPA works (uses Brevo API)
   - Test webhook returns 404
   - Test import command shows error

2. **Unit Tests**:
   - Run `python manage.py test brevo_analytics`
   - All existing tests should pass
   - New blacklist-only mode tests should pass

3. **Regression Testing**:
   - Set `BLACKLIST_ONLY_MODE = False` (default)
   - Verify all analytics features work normally
   - Webhook processes events
   - Import works
   - Both admin menus visible

## Files Changed

1. `brevo_analytics/admin.py` - Conditional registration
2. `brevo_analytics/webhooks.py` - Check mode, return 404
3. `brevo_analytics/management/commands/import_brevo_logs.py` - Check mode, exit
4. `brevo_analytics/tests.py` - Add test cases
5. `docs/README.md` - Document new mode
6. `brevo_analytics/CLAUDE.md` - Document new mode

## Migration Required

**No database migration required** - only code changes.

## Backwards Compatibility

- Default behavior unchanged (`BLACKLIST_ONLY_MODE = False`)
- Existing installations continue working normally
- Opt-in feature via explicit configuration

## Release Notes

```markdown
### Added
- Blacklist-only mode for use cases without analytics (variable subjects, simple blacklist management)
- Configuration flag `BLACKLIST_ONLY_MODE` to disable webhook/import and show only Blacklist Management
- Automatic webhook disabling when blacklist-only mode enabled
- Helpful error messages for disabled features
```
