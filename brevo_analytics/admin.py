from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.conf import settings
from django.utils.safestring import mark_safe
import json
from .models import BrevoMessage, BrevoEmail
from .i18n import get_translations, get_breadcrumb_translations


class BrevoMessageAdmin(admin.ModelAdmin):
    """
    Admin that serves only the Vue.js SPA.
    Standard list/change views are completely replaced.
    """

    # Show in admin sidebar
    def has_module_permission(self, request):
        return request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def get_urls(self):
        """Override all URLs to serve only the SPA"""
        # Custom URLs that bypass all standard admin views
        custom_urls = [
            path('', self.admin_site.admin_view(self.spa_view), name='brevo_analytics_brevomessage_changelist'),
        ]
        return custom_urls

    def spa_view(self, request):
        """Serve Vue.js SPA"""
        # Get language code from Django settings
        language_code = getattr(settings, 'LANGUAGE_CODE', 'en').split('-')[0]

        # Get translations
        translations = get_translations(language_code)
        breadcrumb_translations = get_breadcrumb_translations(language_code)

        # Build breadcrumb
        breadcrumb = [
            {'title': breadcrumb_translations['home'], 'url': '/admin/'},
            {'title': breadcrumb_translations['brevo_analytics'], 'url': '/admin/brevo_analytics/'},
            {'title': breadcrumb_translations['message_analysis'], 'url': None},  # Current page
        ]

        return render(request, 'brevo_analytics/spa.html', {
            'title': breadcrumb_translations['message_analysis'],
            'site_title': admin.site.site_title,
            'site_header': admin.site.site_header,
            'has_permission': True,
            'breadcrumb': breadcrumb,
            'translations_json': mark_safe(json.dumps(translations)),
            'language_code': language_code,
        })

    # Disable all standard admin actions
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BrevoEmailAdmin(admin.ModelAdmin):
    """
    Admin for Blacklist Management SPA.
    Shows as separate menu item in sidebar.
    """

    # Show in admin sidebar with custom name
    def has_module_permission(self, request):
        return request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def get_urls(self):
        """Override all URLs to serve only the Blacklist Management SPA"""
        custom_urls = [
            path('', self.admin_site.admin_view(self.blacklist_spa_view), name='brevo_analytics_brevoemail_changelist'),
        ]
        return custom_urls

    def blacklist_spa_view(self, request):
        """Serve Blacklist Management Vue.js SPA"""
        # Get language code from Django settings
        language_code = getattr(settings, 'LANGUAGE_CODE', 'en').split('-')[0]

        # Get translations
        translations = get_translations(language_code)
        breadcrumb_translations = get_breadcrumb_translations(language_code)

        # Build breadcrumb
        breadcrumb = [
            {'title': breadcrumb_translations['home'], 'url': '/admin/'},
            {'title': breadcrumb_translations['brevo_analytics'], 'url': '/admin/brevo_analytics/'},
            {'title': breadcrumb_translations['blacklist_management'], 'url': None},  # Current page
        ]

        return render(request, 'brevo_analytics/blacklist_spa.html', {
            'title': breadcrumb_translations['blacklist_management'],
            'site_title': admin.site.site_title,
            'site_header': admin.site.site_header,
            'has_permission': True,
            'breadcrumb': breadcrumb,
            'translations_json': mark_safe(json.dumps(translations)),
            'language_code': language_code,
        })

    # Disable all standard admin actions
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# Conditional registration based on BLACKLIST_ONLY_MODE
brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
blacklist_only = brevo_config.get('BLACKLIST_ONLY_MODE', False)

if not blacklist_only:
    # Register Message Analysis (analytics with subject grouping)
    admin.site.register(BrevoMessage, BrevoMessageAdmin)

# Always register Blacklist Management
admin.site.register(BrevoEmail, BrevoEmailAdmin)
