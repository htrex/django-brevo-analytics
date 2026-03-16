from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from django.conf import settings
import requests
from urllib.parse import quote
from .models import BrevoMessage, BrevoEmail
from .sender_utils import get_allowed_senders, is_sender_allowed
from .serializers import (
    BrevoMessageSerializer,
    BrevoEmailListSerializer,
    BrevoEmailDetailSerializer,
    MessageBrevoEmailsSerializer,
    GlobalBrevoEmailsSerializer
)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def dashboard_api(request):
    """
    Dashboard KPI + ultimi 20 messaggi.

    GET /api/dashboard/
    """
    # Calcola KPI globali
    all_messages = BrevoMessage.objects.all()

    kpi = all_messages.aggregate(
        total_sent=Sum('total_sent'),
        total_delivered=Sum('total_delivered'),
        total_opened=Sum('total_opened'),
        total_clicked=Sum('total_clicked'),
        total_bounced=Sum('total_bounced'),
        total_blocked=Sum('total_blocked'),
    )

    # Calcola rates globali
    total_sent = kpi['total_sent'] or 0
    total_delivered = kpi['total_delivered'] or 0

    if total_sent > 0:
        delivery_rate = round(total_delivered / total_sent * 100, 2)
    else:
        delivery_rate = 0.0

    if total_delivered > 0:
        open_rate = round((kpi['total_opened'] or 0) / total_delivered * 100, 2)
        click_rate = round((kpi['total_clicked'] or 0) / total_delivered * 100, 2)
    else:
        open_rate = 0.0
        click_rate = 0.0

    kpi_data = {
        'total_sent': total_sent,
        'delivery_rate': delivery_rate,
        'open_rate': open_rate,
        'click_rate': click_rate,
        'total_bounced': kpi['total_bounced'] or 0,
        'total_blocked': kpi['total_blocked'] or 0,
    }

    # Ultimi 20 messaggi
    recent_messages = BrevoMessage.objects.all()[:20]
    messages_data = BrevoMessageSerializer(recent_messages, many=True).data

    return Response({
        'kpi': kpi_data,
        'recent_messages': messages_data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def messages_list_api(request):
    """
    Lista di tutti i messaggi (per "Mostra tutti").

    GET /api/messages/
    """
    messages = BrevoMessage.objects.all()
    serializer = BrevoMessageSerializer(messages, many=True)

    return Response({
        'messages': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def message_emails_api(request, message_id):
    """
    BrevoEmail per messaggio specifico.

    GET /api/messages/:id/emails/
    """
    try:
        message = BrevoMessage.objects.get(id=message_id)
    except BrevoMessage.DoesNotExist:
        return Response({'error': 'Message not found'}, status=404)

    emails = message.emails.all()

    # Filtro per status se presente query param
    status_filter = request.GET.get('status')
    if status_filter:
        emails = emails.filter(current_status=status_filter)

    message_data = BrevoMessageSerializer(message).data
    emails_data = BrevoEmailListSerializer(emails, many=True).data

    return Response({
        'message': message_data,
        'emails': emails_data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def emails_bounced_api(request):
    """
    Tutte le email bounced (cross-message).

    GET /api/emails/bounced/
    """
    emails = BrevoEmail.objects.filter(current_status='bounced').select_related('message')
    serializer = GlobalBrevoEmailsSerializer(emails, many=True)

    return Response({
        'emails': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def emails_blocked_api(request):
    """
    Tutte le email blocked (cross-message).

    GET /api/emails/blocked/
    """
    emails = BrevoEmail.objects.filter(current_status='blocked').select_related('message')
    serializer = GlobalBrevoEmailsSerializer(emails, many=True)

    return Response({
        'emails': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def email_detail_api(request, email_id):
    """
    Dettaglio email singola (per modale).

    GET /api/emails/:id/

    Se l'email ha status 'blocked' e non ha blacklist_info cached,
    interroga l'API Brevo per ottenerle.
    """
    try:
        email = BrevoEmail.objects.select_related('message').get(id=email_id)
    except BrevoEmail.DoesNotExist:
        return Response({'error': 'BrevoEmail not found'}, status=404)

    # Se è blocked e non abbiamo blacklist_info, prova a ottenerla
    if email.current_status == 'blocked' and not email.blacklist_info:
        brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
        api_key = brevo_config.get('API_KEY', '')

        if api_key:
            try:
                headers = {
                    'api-key': api_key,
                    'accept': 'application/json'
                }

                response = requests.get(
                    f"https://api.brevo.com/v3/smtp/blockedContacts",
                    headers=headers,
                    params={
                        'email': email.recipient_email,
                        'limit': 50
                    },
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    contacts = data.get('contacts', [])

                    # Find matching contact
                    for contact in contacts:
                        if contact.get('email', '').lower() == email.recipient_email.lower():
                            # Verify this contact belongs to our client:
                            # - If senderEmail matches ALLOWED_SENDERS: it's ours
                            # - If senderEmail is empty/None: check if in local DB (email object already loaded)
                            allowed_senders = get_allowed_senders()
                            if allowed_senders:
                                contact_senders = contact.get('senderEmail', [])
                                if isinstance(contact_senders, str):
                                    contact_senders = [contact_senders]
                                elif not isinstance(contact_senders, list):
                                    contact_senders = []

                                # Check if any of the contact's senders match our allowed list
                                has_our_sender = any(
                                    is_sender_allowed(s, allowed_senders) for s in contact_senders
                                )

                                # If no sender, we already have the email in DB (we're viewing its detail)
                                # So it's definitely ours
                                if not has_our_sender and len(contact_senders) > 0:
                                    # Has senders but not ours - skip
                                    break

                            # Normalize data
                            reason = contact.get('reason', 'unknown')
                            if isinstance(reason, dict):
                                # Extract code first (will be translated in frontend), fallback to message
                                reason = reason.get('code') or reason.get('message') or str(reason)
                            elif not isinstance(reason, str):
                                reason = str(reason) if reason else 'unknown'

                            senders = contact.get('senderEmail', [])
                            if not isinstance(senders, list):
                                if isinstance(senders, str):
                                    senders = [senders]
                                else:
                                    senders = []

                            # Cache blacklist info
                            from django.utils import timezone
                            email.blacklist_info = {
                                'reason': reason,
                                'blocked_at': contact.get('blockedAt', ''),
                                'senders': senders,
                                'checked_at': timezone.now().isoformat()
                            }
                            email.save(update_fields=['blacklist_info', 'updated_at'])
                            break

            except Exception:
                # Silently fail - not critical for display
                pass

    serializer = BrevoEmailDetailSerializer(email)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def check_blacklist_status_api(request, email_address):
    """
    Verifica se un'email è in blacklist Brevo.

    GET /api/blacklist/:email_address/

    Returns:
        {
            "is_blacklisted": true/false,
            "reason": "hard_bounce" | "complaint" | "unsubscribe" | "manual_block",
            "blocked_at": "2026-01-20T10:00:00Z",
            "senders": ["sender1@example.com", "sender2@example.com"]
        }
    """
    brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
    api_key = brevo_config.get('API_KEY', '')

    if not api_key:
        return Response({
            'error': 'Brevo API key not configured'
        }, status=500)

    headers = {
        'api-key': api_key,
        'accept': 'application/json'
    }

    try:
        # Get blocklist info
        # https://developers.brevo.com/reference/get-transac-blocked-contacts
        response = requests.get(
            f"https://api.brevo.com/v3/smtp/blockedContacts",
            headers=headers,
            params={
                'email': email_address,
                'limit': 50
            },
            timeout=10
        )

        if response.status_code == 401:
            return Response({
                'error': 'Invalid API key'
            }, status=500)

        if response.status_code != 200:
            return Response({
                'error': f'Brevo API error: {response.status_code}',
                'details': response.text[:200]
            }, status=500)

        data = response.json()
        contacts = data.get('contacts', [])

        # Find matching contact
        matching_contact = None
        for contact in contacts:
            if contact.get('email', '').lower() == email_address.lower():
                matching_contact = contact
                break

        if not matching_contact:
            return Response({
                'is_blacklisted': False,
                'email': email_address
            })

        # Verify this contact belongs to our client:
        # - If senderEmail matches ALLOWED_SENDERS: it's ours
        # - If senderEmail is empty/None: check if in local DB
        allowed_senders = get_allowed_senders()
        if allowed_senders:
            contact_senders = matching_contact.get('senderEmail', [])
            if isinstance(contact_senders, str):
                contact_senders = [contact_senders]
            elif not isinstance(contact_senders, list):
                contact_senders = []

            # Check if any of the contact's senders match our allowed list
            has_our_sender = any(
                is_sender_allowed(s, allowed_senders) for s in contact_senders
            )

            # If no sender, check if email is in our local database
            if not has_our_sender and len(contact_senders) == 0:
                has_our_sender = BrevoEmail.objects.filter(
                    recipient_email__iexact=email_address
                ).exists()

            if not has_our_sender:
                # This contact is blocked but not for our client
                return Response({
                    'is_blacklisted': False,
                    'email': email_address
                })

        # Normalize data
        reason = matching_contact.get('reason', 'unknown')
        if isinstance(reason, dict):
            # Extract code first (will be translated in frontend), fallback to message
            reason = reason.get('code') or reason.get('message') or str(reason)
        elif not isinstance(reason, str):
            reason = str(reason) if reason else 'unknown'

        senders = matching_contact.get('senderEmail', [])
        if not isinstance(senders, list):
            if isinstance(senders, str):
                senders = [senders]
            else:
                senders = []

        # Parse blocklist info
        return Response({
            'is_blacklisted': True,
            'email': email_address,
            'reason': reason,
            'blocked_at': matching_contact.get('blockedAt', ''),
            'senders': senders
        })

    except requests.exceptions.Timeout:
        return Response({
            'error': 'Timeout connecting to Brevo API'
        }, status=504)
    except Exception as e:
        return Response({
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def remove_from_blacklist_api(request, email_address):
    """
    Rimuove un'email dalla blacklist Brevo.

    DELETE /api/blacklist/:email_address/

    Returns:
        {"success": true, "message": "Email removed from blacklist"}
    """
    brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
    api_key = brevo_config.get('API_KEY', '')

    if not api_key:
        return Response({
            'error': 'Brevo API key not configured'
        }, status=500)

    headers = {
        'api-key': api_key,
        'accept': 'application/json'
    }

    try:
        # URL-encode the email address
        encoded_email = quote(email_address, safe='')

        # Remove from blocklist
        # https://developers.brevo.com/reference/delete_smtp-blockedcontacts-email
        response = requests.delete(
            f"https://api.brevo.com/v3/smtp/blockedContacts/{encoded_email}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 401:
            return Response({
                'error': 'Invalid API key'
            }, status=500)

        if response.status_code == 404:
            return Response({
                'error': 'Email not found in blacklist'
            }, status=404)

        if response.status_code not in [200, 204]:
            return Response({
                'error': f'Brevo API error: {response.status_code}',
                'details': response.text[:200]
            }, status=500)

        # Clear cached blacklist_info in DB
        BrevoEmail.objects.filter(
            recipient_email__iexact=email_address
        ).update(blacklist_info=None)

        return Response({
            'success': True,
            'message': f'Email {email_address} removed from blacklist'
        })

    except requests.exceptions.Timeout:
        return Response({
            'error': 'Timeout connecting to Brevo API'
        }, status=504)
    except Exception as e:
        return Response({
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_blacklist_api(request):
    """
    Lista completa blacklist Brevo.

    GET /api/blacklist/

    Query params:
        - reason: filter by reason (optional)
        - limit: max results (default 100, max 500)

    Returns:
        {
            "contacts": [...],
            "total": 123,
            "by_reason": {"hard_bounce": 50, "complaint": 10, ...}
        }
    """
    brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
    api_key = brevo_config.get('API_KEY', '')

    if not api_key:
        return Response({
            'error': 'Brevo API key not configured'
        }, status=500)

    headers = {
        'api-key': api_key,
        'accept': 'application/json'
    }

    reason_filter = request.GET.get('reason')
    max_results = min(int(request.GET.get('limit', 100)), 500)

    try:
        all_contacts = []
        offset = 0
        limit = 50

        # Paginate through API
        while len(all_contacts) < max_results:
            response = requests.get(
                "https://api.brevo.com/v3/smtp/blockedContacts",
                headers=headers,
                params={
                    'limit': limit,
                    'offset': offset
                },
                timeout=10
            )

            if response.status_code == 401:
                return Response({
                    'error': 'Invalid API key'
                }, status=500)

            if response.status_code != 200:
                return Response({
                    'error': f'Brevo API error: {response.status_code}',
                    'details': response.text[:200]
                }, status=500)

            data = response.json()
            contacts = data.get('contacts', [])

            if not contacts:
                break

            # Normalize contact data
            for contact in contacts:
                # Ensure reason is a string
                if 'reason' in contact:
                    reason = contact['reason']
                    if isinstance(reason, dict):
                        # Extract code first (will be translated in frontend), fallback to message
                        contact['reason'] = reason.get('code') or reason.get('message') or str(reason)
                    elif not isinstance(reason, str):
                        contact['reason'] = str(reason) if reason else 'unknown'

                # Ensure senderEmail is always a list
                if 'senderEmail' in contact:
                    if not isinstance(contact['senderEmail'], list):
                        if isinstance(contact['senderEmail'], str):
                            contact['senderEmail'] = [contact['senderEmail']]
                        else:
                            contact['senderEmail'] = []

            all_contacts.extend(contacts)
            offset += limit

            if len(contacts) < limit:
                break

        # Filter by allowed senders OR local database:
        # - If senderEmail matches ALLOWED_SENDERS: include (even if old, not in DB)
        # - If senderEmail is empty/None: include only if in local DB (to exclude other clients)
        allowed_senders = get_allowed_senders()
        if allowed_senders:
            # Get all local emails for filtering contacts without sender
            local_emails = set(
                BrevoEmail.objects.values_list('recipient_email', flat=True)
            )
            local_emails_lower = {e.lower() for e in local_emails}

            filtered_contacts = []
            for contact in all_contacts:
                sender_emails = contact.get('senderEmail', [])
                contact_email = contact.get('email', '').lower()

                # senderEmail is always a list now (normalized above)
                if isinstance(sender_emails, list):
                    # Has sender from our allowed list: always include
                    if any(is_sender_allowed(s, allowed_senders) for s in sender_emails):
                        filtered_contacts.append(contact)
                    # No sender (or empty list): include only if in local DB
                    elif len(sender_emails) == 0 and contact_email in local_emails_lower:
                        filtered_contacts.append(contact)
                elif is_sender_allowed(sender_emails, allowed_senders):
                    # Fallback for non-list (shouldn't happen after normalization)
                    filtered_contacts.append(contact)

            all_contacts = filtered_contacts

        # Filter by reason if requested
        if reason_filter:
            filtered = []
            for c in all_contacts:
                contact_reason = c.get('reason', '')
                # Ensure we're comparing strings
                if isinstance(contact_reason, str) and contact_reason == reason_filter:
                    filtered.append(c)
            all_contacts = filtered

        # Limit results
        all_contacts = all_contacts[:max_results]

        # Sort by blocked date (most recent first)
        all_contacts.sort(key=lambda c: c.get('blockedAt', ''), reverse=True)

        # Check which emails have local data (for bounce details)
        # Note: Some old contacts with senderEmail may not be in local DB
        local_emails = set(
            BrevoEmail.objects.filter(
                recipient_email__in=[c.get('email') for c in all_contacts]
            ).values_list('recipient_email', flat=True)
        )

        for contact in all_contacts:
            contact['has_local_data'] = contact.get('email') in local_emails

        # Group by reason for stats
        by_reason = {}
        for contact in all_contacts:
            reason = contact.get('reason', 'unknown')
            # Ensure reason is a string (API might return unexpected types)
            if not isinstance(reason, str):
                reason = str(reason) if reason else 'unknown'
            by_reason[reason] = by_reason.get(reason, 0) + 1

        return Response({
            'contacts': all_contacts,
            'total': len(all_contacts),
            'by_reason': by_reason
        })

    except requests.exceptions.Timeout:
        return Response({
            'error': 'Timeout connecting to Brevo API'
        }, status=504)
    except Exception as e:
        return Response({
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def enrich_blocked_emails_api(request):
    """
    Arricchisce email blocked nel DB con info da Brevo API.

    POST /api/blacklist/enrich/

    Body:
        {
            "force": false  // Re-enrich anche quelle già processate
        }

    Returns:
        {
            "enriched": 123,
            "not_found": 5,
            "total_processed": 128
        }
    """
    brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
    api_key = brevo_config.get('API_KEY', '')

    if not api_key:
        return Response({
            'error': 'Brevo API key not configured'
        }, status=500)

    force = request.data.get('force', False)

    # Get blocked emails to process
    if force:
        blocked_emails = BrevoEmail.objects.filter(current_status='blocked')
    else:
        blocked_emails = BrevoEmail.objects.filter(
            current_status='blocked',
            blacklist_info__isnull=True
        )

    total = blocked_emails.count()

    if total == 0:
        return Response({
            'enriched': 0,
            'not_found': 0,
            'total_processed': 0,
            'message': 'No blocked emails to process'
        })

    headers = {
        'api-key': api_key,
        'accept': 'application/json'
    }

    enriched = 0
    not_found = 0

    from django.utils import timezone
    import time

    for email_obj in blocked_emails:
        email_address = email_obj.recipient_email

        try:
            response = requests.get(
                "https://api.brevo.com/v3/smtp/blockedContacts",
                headers=headers,
                params={
                    'email': email_address,
                    'limit': 50
                },
                timeout=5
            )

            if response.status_code == 429:
                # Rate limited, wait and retry
                time.sleep(5)
                continue

            if response.status_code == 200:
                data = response.json()
                contacts = data.get('contacts', [])

                # Find matching contact
                matching = None
                for contact in contacts:
                    if contact.get('email', '').lower() == email_address.lower():
                        matching = contact
                        break

                if matching:
                    # Verify this contact belongs to our client:
                    # - If senderEmail matches ALLOWED_SENDERS: it's ours
                    # - If senderEmail is empty/None: it's ours (we're enriching local DB emails)
                    allowed_senders = get_allowed_senders()
                    if allowed_senders:
                        contact_senders = matching.get('senderEmail', [])
                        if isinstance(contact_senders, str):
                            contact_senders = [contact_senders]
                        elif not isinstance(contact_senders, list):
                            contact_senders = []

                        # Check if any of the contact's senders match our allowed list
                        has_our_sender = any(
                            is_sender_allowed(s, allowed_senders) for s in contact_senders
                        )

                        # If no sender, it's ours (we're processing emails from our local DB)
                        # If has senders but not ours, skip
                        if len(contact_senders) > 0 and not has_our_sender:
                            # This contact is blocked but not for our client - skip
                            not_found += 1
                            continue

                    # Normalize data
                    reason = matching.get('reason', 'unknown')
                    if isinstance(reason, dict):
                        # Extract code first (will be translated in frontend), fallback to message
                        reason = reason.get('code') or reason.get('message') or str(reason)
                    elif not isinstance(reason, str):
                        reason = str(reason) if reason else 'unknown'

                    senders = matching.get('senderEmail', [])
                    if not isinstance(senders, list):
                        if isinstance(senders, str):
                            senders = [senders]
                        else:
                            senders = []

                    email_obj.blacklist_info = {
                        'reason': reason,
                        'blocked_at': matching.get('blockedAt', ''),
                        'senders': senders,
                        'checked_at': timezone.now().isoformat()
                    }
                    email_obj.save(update_fields=['blacklist_info', 'updated_at'])
                    enriched += 1
                else:
                    not_found += 1

        except Exception:
            continue

    return Response({
        'enriched': enriched,
        'not_found': not_found,
        'total_processed': total
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_bounce_details_api(request, email_address):
    """
    Recupera i dettagli del bounce per un indirizzo email.

    Prima controlla il database locale, poi interroga Brevo API se necessario.

    GET /api/bounce-details/<email_address>/

    Returns:
        - email: indirizzo email
        - bounce_reason: motivo del bounce
        - bounce_type: hard/soft
        - timestamp: data/ora del bounce
        - subject: oggetto del messaggio (se da DB locale)
        - source: 'local' o 'api'
    """
    # 1. Cerca prima nel database locale
    emails = BrevoEmail.objects.filter(
        recipient_email=email_address,
        current_status='bounced'
    ).order_by('-sent_at')

    if emails.exists():
        email = emails.first()

        # Trova l'evento bounce più recente nell'array events
        bounce_event = None
        if email.events:
            for event in reversed(email.events):
                if event.get('type') == 'bounced':
                    bounce_event = event
                    break

        if bounce_event:
            return Response({
                'email': email_address,
                'bounce_reason': bounce_event.get('bounce_reason', 'Motivo non specificato'),
                'bounce_type': bounce_event.get('bounce_type', 'unknown'),
                'timestamp': bounce_event.get('timestamp', ''),
                'subject': email.message.subject if email.message else 'N/A',
                'sent_at': email.sent_at.isoformat() if email.sent_at else None,
                'source': 'local'
            })

    # 2. Se non trovato localmente, interroga Brevo API
    brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
    api_key = brevo_config.get('API_KEY', '')

    if not api_key:
        return Response({
            'error': 'Dettagli non disponibili',
            'detail': 'Email non presente nel database locale e API key non configurata'
        }, status=404)

    headers = {
        'api-key': api_key,
        'accept': 'application/json'
    }

    try:
        # Query Brevo API per eventi bounce di questa email
        # Range ampio per trovare bounce anche vecchi (ultimi 3 anni)
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=1095)).strftime('%Y-%m-%d')  # 3 anni

        # Prova prima con hard_bounce
        for event_type in ['hard_bounce', 'soft_bounce']:
            params = {
                'event': event_type,
                'email': email_address,
                'startDate': start_date,
                'endDate': end_date,
                'limit': 1,
                'sort': 'desc'
            }

            response = requests.get(
                "https://api.brevo.com/v3/smtp/statistics/events",
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                events = data.get('events', [])

                if events:
                    event = events[0]
                    return Response({
                        'email': email_address,
                        'bounce_reason': event.get('reason') or event.get('error') or 'Motivo non specificato',
                        'bounce_type': 'hard' if event_type == 'hard_bounce' else 'soft',
                        'timestamp': event.get('date', ''),
                        'subject': event.get('subject', 'N/A'),
                        'source': 'api'
                    })

        # Nessun evento trovato
        return Response({
            'error': 'Nessun evento bounce trovato',
            'detail': 'Nessun bounce negli ultimi 3 anni per questo indirizzo nelle statistiche Brevo'
        }, status=404)

    except requests.exceptions.Timeout:
        return Response({
            'error': 'Timeout connecting to Brevo API'
        }, status=504)
    except Exception as e:
        return Response({
            'error': f'Errore durante la richiesta a Brevo: {str(e)}'
        }, status=500)
