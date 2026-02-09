import json
import logging
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from .models import BrevoMessage, BrevoEmail

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def brevo_webhook(request):
    """
    Brevo webhook endpoint for real-time event processing.

    Configure in Brevo dashboard:
    URL: https://your-domain.com/brevo-analytics/webhook/
    Events: All transactional email events

    Disabled when BLACKLIST_ONLY_MODE is enabled.
    """
    config = getattr(settings, 'BREVO_ANALYTICS', {})

    # Check if blacklist-only mode is enabled
    if config.get('BLACKLIST_ONLY_MODE', False):
        logger.warning("Webhook called but BLACKLIST_ONLY_MODE is enabled")
        return JsonResponse({
            'status': 'disabled',
            'message': 'Webhook is disabled in BLACKLIST_ONLY_MODE. Use Blacklist Management for direct API access.'
        }, status=404)

    # Verify webhook authentication (if configured)
    webhook_secret = config.get('WEBHOOK_SECRET')

    if webhook_secret:
        # Brevo uses Bearer token authentication in Authorization header
        auth_header = request.headers.get('Authorization', '')

        # Extract token from "Bearer <token>" format
        if auth_header.startswith('Bearer '):
            received_token = auth_header[7:]  # Remove "Bearer " prefix
        else:
            received_token = ''

        if received_token != webhook_secret:
            logger.warning(
                f"Invalid webhook authentication - "
                f"expected Bearer token but received: {auth_header[:20]}..."
            )
            return HttpResponseBadRequest('Invalid authentication')

    # Parse webhook payload
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return HttpResponseBadRequest('Invalid JSON')

    # Extract required fields
    event_type = payload.get('event')
    message_id = payload.get('message-id')
    email_address = payload.get('email')
    subject = payload.get('subject', '')
    timestamp_unix = payload.get('ts_event')
    sender = payload.get('sender') or payload.get('from') or payload.get('sender_email', '')  # Brevo uses 'sender_email' in some events

    if not all([event_type, message_id, email_address, timestamp_unix]):
        logger.error(f"Missing required fields in webhook: {payload}")
        return HttpResponseBadRequest('Missing required fields')

    # CRITICAL: Verify sender is authorized (multi-tenant security)
    allowed_senders = config.get('ALLOWED_SENDERS', ['info@infoparlamento.it'])
    if isinstance(allowed_senders, str):
        allowed_senders = [allowed_senders]

    if allowed_senders and sender:
        sender_lower = sender.lower()
        if not any(allowed.lower() == sender_lower for allowed in allowed_senders):
            logger.warning(
                f"Ignoring webhook event from unauthorized sender: {sender} "
                f"(allowed: {', '.join(allowed_senders)})"
            )
            return JsonResponse({'status': 'ignored', 'reason': 'unauthorized_sender'})
    elif allowed_senders and not sender:
        # No sender info in payload - log warning but allow (for backward compatibility)
        logger.warning(
            f"Webhook event has no sender information. Payload keys: {list(payload.keys())}"
        )

    # Check if email is to an excluded internal domain
    excluded_domains = config.get('EXCLUDED_RECIPIENT_DOMAINS', ['openpolis.it', 'deppsviluppo.org'])
    if isinstance(excluded_domains, str):
        excluded_domains = [excluded_domains]

    if excluded_domains:
        email_lower = email_address.lower()
        for domain in excluded_domains:
            if email_lower.endswith(f'@{domain}'):
                logger.info(f"Ignoring webhook event for internal domain: {email_address}")
                return JsonResponse({'status': 'ignored', 'reason': 'internal_domain'})

    # Convert timestamp
    try:
        event_datetime = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
    except (ValueError, OSError):
        logger.error(f"Invalid timestamp: {timestamp_unix}")
        return HttpResponseBadRequest('Invalid timestamp')

    event_date = event_datetime.date()

    # Map Brevo event name to our event type
    event_mapping = {
        'request': 'sent',
        'delivered': 'delivered',
        'hard_bounce': 'bounced',
        'soft_bounce': 'bounced',
        'blocked': 'blocked',
        'spam': 'spam',
        'unsubscribe': 'unsubscribed',
        'opened': 'opened',
        'click': 'clicked',
        'deferred': 'deferred',
    }

    our_event_type = event_mapping.get(event_type, event_type)
    is_sent_event = (our_event_type == 'sent')
    is_delivered_event = (our_event_type == 'delivered')

    # Treat 'delivered' as proof of 'sent' for creating records
    is_creation_event = is_sent_event or is_delivered_event

    # 1. Try to find existing BrevoEmail
    try:
        email = BrevoEmail.objects.select_related('message').get(
            brevo_message_id=message_id,
            recipient_email=email_address
        )
        message = email.message
        email_created = False
        logger.debug(f"Found existing email: {message_id} to {email_address}")
    except BrevoEmail.DoesNotExist:
        email = None
        email_created = True

    # 2. If email doesn't exist and this is NOT a 'sent' or 'delivered' event, ignore it
    #    Rationale: 'delivered' proves the email was sent, even if we missed the 'sent' event
    if email is None and not is_creation_event:
        logger.info(
            f"Ignoring {event_type} event for unknown email {message_id} to {email_address} "
            f"(no 'sent' or 'delivered' event received yet)"
        )
        return JsonResponse({'status': 'ignored', 'reason': 'no_sent_event'})

    # 3. If this is a 'sent' or 'delivered' event and email doesn't exist, create it
    if email is None and is_creation_event:
        # Get or create BrevoMessage (identified by subject + sent_date)
        message, message_created = BrevoMessage.objects.get_or_create(
            subject=subject,
            sent_date=event_date,
            defaults={
                'total_sent': 0,
            }
        )

        if message_created:
            logger.info(f"Created new message: {subject} - {event_date}")

        # Determine initial status and sent_at based on event type
        if is_delivered_event:
            # If we're creating from 'delivered', it means we missed the 'sent' event
            # Use delivered timestamp as sent_at (close enough approximation)
            initial_status = 'delivered'
            initial_events = [
                {
                    'type': 'sent',
                    'timestamp': event_datetime.isoformat(),
                    'inferred': True,  # Mark that this was inferred from delivered
                }
            ]
            logger.info(
                f"Creating email from 'delivered' event (missed 'sent'): "
                f"{message_id} to {email_address} from {sender}"
            )
        else:
            # Normal 'sent' event
            initial_status = 'sent'
            initial_events = []

        # Create BrevoEmail
        email = BrevoEmail.objects.create(
            brevo_message_id=message_id,
            message=message,
            sender_email=sender if sender else None,
            recipient_email=email_address,
            sent_at=event_datetime,
            current_status=initial_status,
            events=initial_events
        )
        logger.info(f"Created new email: {message_id} to {email_address} from {sender}")

    # 4. Build event data with extra fields
    extra_data = {}

    # Bounce information
    if 'bounce' in event_type:
        extra_data['bounce_type'] = 'hard' if 'hard' in event_type else 'soft'
        extra_data['bounce_reason'] = payload.get('reason', '')

    # Click information
    if event_type == 'click':
        extra_data['url'] = payload.get('link', '')

    # Open information
    if event_type == 'opened':
        extra_data['ip'] = payload.get('ip', '')
        extra_data['user_agent'] = payload.get('user_agent', '')

    # Store raw payload for debugging
    extra_data['raw'] = payload

    # 5. Add event (handles duplicates internally)
    added = email.add_event(our_event_type, event_datetime, **extra_data)

    if added:
        logger.info(f"Added event {our_event_type} for email {message_id}")
    else:
        logger.debug(f"Event {our_event_type} already exists for email {message_id}")

    return JsonResponse({'status': 'ok'})
