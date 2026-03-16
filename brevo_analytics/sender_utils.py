"""
Shared utilities for ALLOWED_SENDERS matching.

Supports two value formats:
- Exact email:  ``'info@example.com'``  — matches that address only (case-insensitive)
- Domain pattern: ``'@example.com'``    — matches any sender from that domain (case-insensitive)
"""

from django.conf import settings
from django.db.models import Q


def get_allowed_senders():
    """Read and normalise ``BREVO_ANALYTICS['ALLOWED_SENDERS']`` from settings.

    Returns a list of strings (possibly empty).  A single-string config value
    is wrapped in a list for uniform handling downstream.
    """
    brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
    allowed = brevo_config.get('ALLOWED_SENDERS', [])
    if isinstance(allowed, str):
        allowed = [allowed]
    return allowed


def is_sender_allowed(sender, allowed_senders):
    """Check whether *sender* matches any entry in *allowed_senders*.

    Rules:
    - Entries starting with ``@`` are domain patterns and match via
      case-insensitive ``endswith``.
    - All other entries are exact email matches (case-insensitive).
    - Returns ``True`` when *allowed_senders* is empty (no filtering).
    """
    if not allowed_senders:
        return True
    if not sender:
        return False
    sender_lower = sender.lower()
    for entry in allowed_senders:
        entry_lower = entry.lower()
        if entry_lower.startswith('@'):
            if sender_lower.endswith(entry_lower):
                return True
        else:
            if sender_lower == entry_lower:
                return True
    return False


def build_sender_filter_q(allowed_senders):
    """Build a Django ORM ``Q`` object that filters by *allowed_senders*.

    Returns a ``Q`` that includes:
    - emails whose ``sender_email`` matches an allowed entry, **plus**
    - emails with ``sender_email IS NULL`` (backward compat with old data).

    If *allowed_senders* is empty the returned ``Q()`` matches everything.
    """
    if not allowed_senders:
        return Q()

    filter_q = Q(sender_email__isnull=True)
    for entry in allowed_senders:
        if entry.startswith('@'):
            filter_q |= Q(sender_email__iendswith=entry)
        else:
            filter_q |= Q(sender_email__iexact=entry)
    return filter_q


def build_sender_sql_clause(allowed_senders, column='frm'):
    """Build a DuckDB SQL fragment for filtering by *allowed_senders*.

    Returns a string suitable for a ``WHERE (...)`` clause.
    Exact emails use ``LOWER(col) = 'email'``; domain patterns use
    ``LOWER(col) LIKE '%@domain'``.

    If *allowed_senders* is empty, returns ``'1=1'`` (match everything).
    """
    if not allowed_senders:
        return '1=1'

    conditions = []
    for entry in allowed_senders:
        entry_lower = entry.lower()
        if entry_lower.startswith('@'):
            # Domain pattern: match anything ending with @domain
            conditions.append(f"LOWER({column}) LIKE '%{entry_lower}'")
        else:
            conditions.append(f"LOWER({column}) = '{entry_lower}'")
    return ' OR '.join(conditions)
