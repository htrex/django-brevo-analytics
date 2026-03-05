"""
Internationalization support for Brevo Analytics SPA.
Provides translations based on Django LANGUAGE_CODE setting.
"""

from django.conf import settings


def get_translations(language_code=None):
    """
    Get translations dictionary for JavaScript based on language code.

    Args:
        language_code: Language code (e.g., 'it', 'en'). If None, uses Django settings.

    Returns:
        Dictionary with all translated strings for the SPA.
    """
    if language_code is None:
        language_code = getattr(settings, 'LANGUAGE_CODE', 'en').split('-')[0]

    translations = {
        'en': {
            # Common
            'loading': 'Loading...',
            'error': 'Error',
            'search_placeholder': '🔍 Search by email...',
            'close': 'Close',

            # Brevo Analytics Dashboard
            'dashboard_title': 'Brevo Analytics',
            'emails_sent': 'Emails Sent',
            'delivery_rate': 'Delivery Rate',
            'open_rate': 'Open Rate',
            'click_rate': 'Click Rate',
            'emails_bounced': 'Emails Bounced',
            'emails_blocked': 'Emails Blocked',
            'recent_messages': 'Recent Messages',
            'all_messages': 'All Messages',
            'show_all': 'Show all →',
            'subject': 'Subject',
            'date': 'Date',
            'sent_datetime': 'Date - Time Sent',
            'sent': 'Sent',
            'delivery': 'Delivery',
            'open': 'Open',
            'click': 'Click',
            'bounced': 'Bounced',
            'blocked': 'Blocked',

            # Message Emails View
            'sent_status': 'Sent',
            'delivered_status': 'Delivered',
            'opened_status': 'Opened',
            'clicked_status': 'Clicked',
            'bounced_status': 'Bounced',
            'blocked_status': 'Blocked',
            'deferred_status': 'Deferred',
            'unsubscribed_status': 'Unsubscribed',
            'recipient': 'Recipient',
            'status': 'Status',

            # Email Detail Modal
            'event_timeline': 'Event Timeline',
            'reason': 'Reason',
            'type': 'Type',
            'url': 'URL',
            'ip_address': 'IP',
            'user_agent': 'User Agent',
            'blacklist_info_title': '🚫 Email in Brevo Blacklist',
            'blocked_date': 'Block date',
            'blocked_senders': 'Blocked senders',
            'remove_from_blacklist': 'Remove from Blacklist',
            'removing_from_blacklist': 'Removing...',
            'opened_info_note': 'ℹ️ Note: The "Opened" event is based on loading an invisible pixel. It may be missing or appear after "Clicked" if the user has blocked images or clicked before the pixel loaded.',
            'hard_bounce_type': 'Hard Bounce',
            'soft_bounce_type': 'Soft Bounce',
            'success_removed_blacklist': 'Email successfully removed from blacklist!',

            # Blacklist Management
            'blacklist_title': 'Blacklist Management',
            'check_email_tab': 'Check Email',
            'manage_blacklist_tab': 'Manage Blacklist',
            'check_email_description': 'Search for a single email to check if it\'s blocked and discover why.',
            'enter_email_placeholder': 'Enter email to check...',
            'verify_button': 'Verify',
            'verifying': 'Verifying...',
            'email_in_blacklist': '⚠️ Email in Blacklist',
            'email_not_in_blacklist': '✅ Email Not in Blacklist',
            'email_not_blocked_message': 'This email address is not blocked.',
            'unblock_button': 'Unblock or remove',
            'unblocking': 'Unblocking...',
            'manage_description': 'View and manage all blacklisted emails across all campaigns.',
            'total_blacklisted': 'Total blacklisted',
            'sync_with_brevo': 'Sync with Brevo',
            'syncing': 'Syncing...',
            'export_csv': 'Export CSV',
            'email': 'Email',
            'email_count': 'Emails',
            'last_blocked': 'Last Blocked',
            'actions': 'Actions',
            'remove': 'Remove',
            'removing': 'Removing...',
            'confirm_remove': 'Are you sure you want to remove this email from the blacklist?',

            # Blacklist Reasons
            'invalid_email': 'Invalid Email',
            'hard_bounce': 'Hard Bounce',
            'manual_blacklist': 'Manual Blacklist',
            'unsubscribe': 'Unsubscribed',
            'spam_complaint': 'Spam Complaint',
            'unknown': 'Unknown',

            # Error Messages
            'load_error': 'Error loading data',
            'email_detail_load_error': 'Error loading email details',
            'blacklist_check_error': 'Error checking blacklist',
            'blacklist_sync_error': 'Error syncing with Brevo',
            'remove_error': 'Error removing from blacklist',
        },
        'it': {
            # Common
            'loading': 'Caricamento...',
            'error': 'Errore',
            'search_placeholder': '🔍 Cerca per email...',
            'close': 'Chiudi',

            # Brevo Analytics Dashboard
            'dashboard_title': 'Analisi Invii',
            'emails_sent': 'Email Inviate',
            'delivery_rate': 'Tasso di Consegna',
            'open_rate': 'Tasso di Apertura',
            'click_rate': 'Tasso di Clic',
            'emails_bounced': 'Email Rimbalzate',
            'emails_blocked': 'Email Bloccate',
            'recent_messages': 'Messaggi Recenti',
            'all_messages': 'Tutti i Messaggi',
            'show_all': 'Mostra tutti →',
            'subject': 'Oggetto',
            'date': 'Data',
            'sent_datetime': 'Data - Ora Invio',
            'sent': 'Inviati',
            'delivery': 'Consegna',
            'open': 'Apertura',
            'click': 'Clic',
            'bounced': 'Rimbalzati',
            'blocked': 'Bloccati',

            # Message Emails View
            'sent_status': 'Inviata',
            'delivered_status': 'Consegnata',
            'opened_status': 'Aperta',
            'clicked_status': 'Cliccata',
            'bounced_status': 'Rimbalzata',
            'blocked_status': 'Bloccata',
            'deferred_status': 'Differita',
            'unsubscribed_status': 'Disiscritto',
            'recipient': 'Destinatario',
            'status': 'Stato',

            # Email Detail Modal
            'event_timeline': 'Cronologia Eventi',
            'reason': 'Motivo',
            'type': 'Tipo',
            'url': 'Collegamento',
            'ip_address': 'Indirizzo IP',
            'user_agent': 'Browser/Dispositivo',
            'blacklist_info_title': '🚫 Email Bloccata da Brevo',
            'blocked_date': 'Data blocco',
            'blocked_senders': 'Mittenti bloccati',
            'remove_from_blacklist': 'Sblocca Email',
            'removing_from_blacklist': 'Sblocco in corso...',
            'opened_info_note': 'ℹ️ Nota: L\'apertura dell\'email viene rilevata quando il destinatario carica le immagini. Potrebbe non essere rilevata se il destinatario ha bloccato le immagini o ha cliccato un link prima di caricarle.',
            'hard_bounce_type': 'Rimbalzo Permanente',
            'soft_bounce_type': 'Rimbalzo Temporaneo',
            'success_removed_blacklist': 'Email sbloccata con successo!',

            # Blacklist Management
            'blacklist_title': 'Gestione Destinatari Bloccati',
            'check_email_tab': 'Verifica Email',
            'manage_blacklist_tab': 'Gestisci Bloccati',
            'check_email_description': 'Cerca un indirizzo email per verificare se è bloccato e scoprire il motivo.',
            'enter_email_placeholder': 'Inserisci indirizzo email da verificare...',
            'verify_button': 'Verifica',
            'verifying': 'Verifica in corso...',
            'email_in_blacklist': '⚠️ Email Bloccata',
            'email_not_in_blacklist': '✅ Email Non Bloccata',
            'email_not_blocked_message': 'L\'indirizzo email non è bloccato.',
            'unblock_button': 'Sblocca',
            'unblocking': 'Sblocco in corso...',
            'manage_description': 'Visualizza e gestisci tutti gli indirizzi email bloccati.',
            'total_blacklisted': 'Totale bloccati',
            'sync_with_brevo': 'Aggiorna da Brevo',
            'syncing': 'Aggiornamento in corso...',
            'export_csv': 'Esporta in Excel',
            'email': 'Indirizzo Email',
            'email_count': 'Numero Email',
            'last_blocked': 'Data Blocco',
            'actions': 'Azioni',
            'remove': 'Sblocca',
            'removing': 'Sblocco...',
            'confirm_remove': 'Sei sicuro di voler sbloccare questo indirizzo email?',

            # Blacklist Reasons
            'invalid_email': 'Indirizzo Non Valido',
            'hard_bounce': 'Rimbalzo Permanente',
            'manual_blacklist': 'Bloccato Manualmente',
            'unsubscribe': 'Cancellato dalla Lista',
            'spam_complaint': 'Segnalato come Spam',
            'unknown': 'Motivo Sconosciuto',

            # Error Messages
            'load_error': 'Errore nel caricamento dei dati',
            'email_detail_load_error': 'Errore nel caricamento dei dettagli',
            'blacklist_check_error': 'Errore nella verifica',
            'blacklist_sync_error': 'Errore nell\'aggiornamento da Brevo',
            'remove_error': 'Errore nello sblocco',
        }
    }

    return translations.get(language_code, translations['en'])


def get_breadcrumb_translations(language_code=None):
    """Get breadcrumb translations."""
    if language_code is None:
        language_code = getattr(settings, 'LANGUAGE_CODE', 'en').split('-')[0]

    breadcrumbs = {
        'en': {
            'home': 'Home',
            'brevo_analytics': 'Brevo Analytics',
            'message_analysis': 'Message Analysis',
            'blacklist_management': 'Blocked Addresses',
        },
        'it': {
            'home': 'Pagina Iniziale',
            'brevo_analytics': 'Brevo Analytics',
            'message_analysis': 'Analisi Invii',
            'blacklist_management': 'Indirizzi Bloccati',
        }
    }

    return breadcrumbs.get(language_code, breadcrumbs['en'])
