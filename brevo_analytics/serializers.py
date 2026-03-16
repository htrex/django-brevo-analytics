from django.conf import settings
from rest_framework import serializers
from .models import BrevoMessage, BrevoEmail


def _display_subject(raw_subject):
    """Strip tag prefix and ID from subject when in tag grouping mode.

    When MESSAGE_GROUP_BY='tag', subjects look like '{prefix}:{id}:{title}'.
    This returns just the '{title}' portion. In default mode, returns subject unchanged.
    """
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    if config.get('MESSAGE_GROUP_BY') == 'tag':
        prefix = config.get('MESSAGE_TAG_PREFIX', 'digest')
        tag_prefix = f"{prefix}:"
        if raw_subject.startswith(tag_prefix):
            remainder = raw_subject[len(tag_prefix):]
            # Strip the ID portion: "{id}:{display_title}"
            if ':' in remainder:
                return remainder.split(':', 1)[1]
            return remainder
    return raw_subject


class BrevoMessageSerializer(serializers.ModelSerializer):
    """Serializer per lista messaggi"""
    display_subject = serializers.SerializerMethodField()

    class Meta:
        model = BrevoMessage
        fields = [
            'id', 'subject', 'display_subject', 'sent_date',
            'total_sent', 'total_delivered', 'total_opened',
            'total_clicked', 'total_bounced', 'total_blocked',
            'delivery_rate', 'open_rate', 'click_rate',
            'updated_at'
        ]

    def get_display_subject(self, obj):
        """Return human-readable subject, stripping tag prefix and ID when in tag grouping mode."""
        return _display_subject(obj.subject)


class BrevoEmailListSerializer(serializers.ModelSerializer):
    """Serializer per lista email (senza eventi)"""
    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status', 'sent_at'
        ]


class BrevoEmailDetailSerializer(serializers.ModelSerializer):
    """Serializer per dettaglio email (con eventi e messaggio)"""
    message = serializers.SerializerMethodField()

    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'events', 'message', 'blacklist_info'
        ]

    def get_message(self, obj):
        return {
            'id': obj.message.id,
            'subject': obj.message.subject,
            'display_subject': _display_subject(obj.message.subject),
            'sent_date': obj.message.sent_date.isoformat()
        }


class MessageBrevoEmailsSerializer(serializers.Serializer):
    """Serializer per risposta /api/messages/:id/emails/"""
    message = BrevoMessageSerializer()
    emails = BrevoEmailListSerializer(many=True)


class GlobalBrevoEmailsSerializer(serializers.ModelSerializer):
    """Serializer per email globali bounced/blocked (con info messaggio)"""
    message = serializers.SerializerMethodField()

    class Meta:
        model = BrevoEmail
        fields = [
            'id', 'recipient_email', 'current_status',
            'sent_at', 'message'
        ]

    def get_message(self, obj):
        return {
            'subject': obj.message.subject,
            'display_subject': _display_subject(obj.message.subject),
            'sent_date': obj.message.sent_date.isoformat()
        }
