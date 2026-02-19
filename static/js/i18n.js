/**
 * Internationalization (i18n) for ChatBotAI
 * Supports German (default) and English
 */

const translations = {
    de: {
        // Navigation
        'nav.inbox': 'Posteingang',
        'nav.settings': 'Einstellungen',
        'nav.guests': 'Gäste',

        // Inbox
        'inbox.title': 'Posteingang',
        'inbox.search': 'Konversationen durchsuchen...',
        'inbox.filter.all': 'Alle',
        'inbox.filter.active': 'Aktiv',
        'inbox.filter.pending': 'Ausstehend',
        'inbox.filter.closed': 'Geschlossen',
        'inbox.filter.platform': 'Plattform',
        'inbox.filter.status': 'Status',
        'inbox.filter.guest': 'Gast',
        'inbox.filter.clear': 'Filter löschen',
        'inbox.empty': 'Keine Konversationen gefunden',
        'inbox.empty.hint': 'Versuchen Sie, die Filter anzupassen oder eine neue Konversation zu starten.',
        'inbox.unread': 'Ungelesen',
        'inbox.ai.enabled': 'KI aktiviert',
        'inbox.ai.disabled': 'KI deaktiviert',

        // Conversation
        'conversation.title': 'Konversation',
        'conversation.send': 'Senden',
        'conversation.placeholder': 'Nachricht eingeben...',
        'conversation.ai.generate': 'KI-Antwort generieren',
        'conversation.ai.generating': 'Generiere...',
        'conversation.ai.toggle': 'KI-Antworten',
        'conversation.ai.on': 'AN',
        'conversation.ai.off': 'AUS',
        'conversation.guest.profile': 'Gästeprofil anzeigen',
        'conversation.you': 'Sie',
        'conversation.guest': 'Gast',
        'conversation.ai': 'KI-Assistent',
        'conversation.empty': 'Noch keine Nachrichten',

        // Guest Profile
        'guest.title': 'Gästeprofil',
        'guest.info': 'Kontaktinformationen',
        'guest.info.name': 'Name',
        'guest.info.email': 'E-Mail',
        'guest.info.phone': 'Telefon',
        'guest.info.edit': 'Bearbeiten',
        'guest.info.save': 'Speichern',
        'guest.info.cancel': 'Abbrechen',
        'guest.memories': 'Erinnerungen',
        'guest.memories.family': 'Familie',
        'guest.memories.pets': 'Haustiere',
        'guest.memories.preferences': 'Vorlieben',
        'guest.memories.allergies': 'Allergien',
        'guest.memories.interests': 'Interessen',
        'guest.memories.requests': 'Sonderwünsche',
        'guest.memories.empty': 'Noch keine Erinnerungen',
        'guest.memories.add': 'Hinzufügen',
        'guest.memories.delete': 'Löschen',
        'guest.conversations': 'Konversationen',
        'guest.conversations.view': 'Anzeigen',
        'guest.stats.stays': 'Aufenthalte',
        'guest.stats.first': 'Erster Kontakt',
        'guest.stats.last': 'Letzter Kontakt',
        'guest.language': 'Bevorzugte Sprache',

        // Settings
        'settings.title': 'Einstellungen',
        'settings.ai.title': 'KI-Konfiguration',
        'settings.ai.autoResponse': 'Automatische Antwort',
        'settings.ai.autoResponse.desc': 'Automatisch KI-Antworten auf Gastnachrichten generieren',
        'settings.ai.memoryExtraction': 'Erinnerungsextraktion',
        'settings.ai.memoryExtraction.desc': 'Gästeinformationen aus Nachrichten extrahieren und speichern',
        'settings.ai.tone': 'Antwortton',
        'settings.ai.tone.friendly': 'Freundlich & Professionell',
        'settings.ai.tone.formal': 'Formell',
        'settings.ai.tone.casual': 'Locker',
        'settings.ai.tone.concise': 'Prägnant',
        'settings.ai.history': 'Konversationsverlauf',
        'settings.ai.history.desc': 'Anzahl der vorherigen Nachrichten für KI-Kontext',
        'settings.ai.save': 'Einstellungen speichern',
        'settings.server.title': 'KI-Server Status',
        'settings.server.connected': 'Verbunden und läuft',
        'settings.server.disconnected': 'Nicht verbunden',
        'settings.server.checking': 'Verbindung wird geprüft...',
        'settings.server.test': 'KI-Verbindung testen',
        'settings.server.url': 'Server-URL',
        'settings.server.model': 'Modell',
        'settings.integrations.title': 'Plattform-Integrationen',
        'settings.integrations.gmail': 'Gmail',
        'settings.integrations.whatsapp': 'WhatsApp',
        'settings.integrations.airbnb': 'Airbnb',
        'settings.integrations.booking': 'Booking.com',
        'settings.integrations.connect': 'Verbinden',
        'settings.integrations.disconnect': 'Trennen',
        'settings.integrations.connected': 'Verbunden',
        'settings.integrations.notConfigured': 'Nicht konfiguriert',
        'settings.integrations.comingSoon': 'Demnächst verfügbar',
        'settings.filter.title': 'E-Mail-Filterung',
        'settings.filter.desc': 'Nur E-Mails, die diesen Filtern entsprechen, werden verarbeitet.',
        'settings.filter.mode': 'Filtermodus',
        'settings.filter.mode.either': 'Entweder (Domain ODER Schlüsselwort)',
        'settings.filter.mode.domain': 'Nur Domain',
        'settings.filter.mode.keyword': 'Nur Schlüsselwort',
        'settings.filter.mode.both': 'Beides (Domain UND Schlüsselwort)',
        'settings.filter.domains': 'Erlaubte Domains',
        'settings.filter.domains.desc': 'Nur E-Mails VON diesen Domains verarbeiten (eine pro Zeile)',
        'settings.filter.keywords': 'Betreff-Schlüsselwörter',
        'settings.filter.keywords.desc': 'Nur E-Mails mit diesen Wörtern im Betreff verarbeiten (eines pro Zeile)',
        'settings.filter.save': 'Filter speichern',
        'settings.properties.title': 'Unterkünfte',
        'settings.properties.add': 'Unterkunft hinzufügen',
        'settings.properties.empty': 'Noch keine Unterkünfte konfiguriert',
        'settings.language.title': 'Sprache',
        'settings.language.ui': 'Oberflächensprache',

        // Common
        'common.save': 'Speichern',
        'common.cancel': 'Abbrechen',
        'common.delete': 'Löschen',
        'common.edit': 'Bearbeiten',
        'common.add': 'Hinzufügen',
        'common.close': 'Schließen',
        'common.confirm': 'Bestätigen',
        'common.loading': 'Laden...',
        'common.error': 'Fehler',
        'common.success': 'Erfolg',
        'common.noData': 'Keine Daten verfügbar',

        // Notifications
        'notify.saved': 'Erfolgreich gespeichert',
        'notify.deleted': 'Erfolgreich gelöscht',
        'notify.error': 'Ein Fehler ist aufgetreten',
        'notify.emailSent': 'E-Mail gesendet',
        'notify.aiResponse': 'KI-Antwort generiert',

        // Platforms
        'platform.email': 'E-Mail',
        'platform.whatsapp': 'WhatsApp',
        'platform.airbnb': 'Airbnb',
        'platform.booking': 'Booking.com'
    },

    en: {
        // Navigation
        'nav.inbox': 'Inbox',
        'nav.settings': 'Settings',
        'nav.guests': 'Guests',

        // Inbox
        'inbox.title': 'Inbox',
        'inbox.search': 'Search conversations...',
        'inbox.filter.all': 'All',
        'inbox.filter.active': 'Active',
        'inbox.filter.pending': 'Pending',
        'inbox.filter.closed': 'Closed',
        'inbox.filter.platform': 'Platform',
        'inbox.filter.status': 'Status',
        'inbox.filter.guest': 'Guest',
        'inbox.filter.clear': 'Clear filters',
        'inbox.empty': 'No conversations found',
        'inbox.empty.hint': 'Try adjusting your filters or start a new conversation.',
        'inbox.unread': 'Unread',
        'inbox.ai.enabled': 'AI enabled',
        'inbox.ai.disabled': 'AI disabled',

        // Conversation
        'conversation.title': 'Conversation',
        'conversation.send': 'Send',
        'conversation.placeholder': 'Type a message...',
        'conversation.ai.generate': 'Generate AI Response',
        'conversation.ai.generating': 'Generating...',
        'conversation.ai.toggle': 'AI Responses',
        'conversation.ai.on': 'ON',
        'conversation.ai.off': 'OFF',
        'conversation.guest.profile': 'View Guest Profile',
        'conversation.you': 'You',
        'conversation.guest': 'Guest',
        'conversation.ai': 'AI Assistant',
        'conversation.empty': 'No messages yet',

        // Guest Profile
        'guest.title': 'Guest Profile',
        'guest.info': 'Contact Information',
        'guest.info.name': 'Name',
        'guest.info.email': 'Email',
        'guest.info.phone': 'Phone',
        'guest.info.edit': 'Edit',
        'guest.info.save': 'Save',
        'guest.info.cancel': 'Cancel',
        'guest.memories': 'Memories',
        'guest.memories.family': 'Family',
        'guest.memories.pets': 'Pets',
        'guest.memories.preferences': 'Preferences',
        'guest.memories.allergies': 'Allergies',
        'guest.memories.interests': 'Interests',
        'guest.memories.requests': 'Special Requests',
        'guest.memories.empty': 'No memories yet',
        'guest.memories.add': 'Add',
        'guest.memories.delete': 'Delete',
        'guest.conversations': 'Conversations',
        'guest.conversations.view': 'View',
        'guest.stats.stays': 'Stays',
        'guest.stats.first': 'First Contact',
        'guest.stats.last': 'Last Contact',
        'guest.language': 'Preferred Language',

        // Settings
        'settings.title': 'Settings',
        'settings.ai.title': 'AI Configuration',
        'settings.ai.autoResponse': 'Auto Response',
        'settings.ai.autoResponse.desc': 'Automatically generate AI responses to guest messages',
        'settings.ai.memoryExtraction': 'Memory Extraction',
        'settings.ai.memoryExtraction.desc': 'Extract and remember guest information from messages',
        'settings.ai.tone': 'Response Tone',
        'settings.ai.tone.friendly': 'Friendly & Professional',
        'settings.ai.tone.formal': 'Formal',
        'settings.ai.tone.casual': 'Casual',
        'settings.ai.tone.concise': 'Concise',
        'settings.ai.history': 'Conversation History',
        'settings.ai.history.desc': 'Number of previous messages to include in AI context',
        'settings.ai.save': 'Save Settings',
        'settings.server.title': 'AI Server Status',
        'settings.server.connected': 'Connected and running',
        'settings.server.disconnected': 'Not connected',
        'settings.server.checking': 'Checking connection...',
        'settings.server.test': 'Test AI Connection',
        'settings.server.url': 'Server URL',
        'settings.server.model': 'Model',
        'settings.integrations.title': 'Platform Integrations',
        'settings.integrations.gmail': 'Gmail',
        'settings.integrations.whatsapp': 'WhatsApp',
        'settings.integrations.airbnb': 'Airbnb',
        'settings.integrations.booking': 'Booking.com',
        'settings.integrations.connect': 'Connect',
        'settings.integrations.disconnect': 'Disconnect',
        'settings.integrations.connected': 'Connected',
        'settings.integrations.notConfigured': 'Not configured',
        'settings.integrations.comingSoon': 'Coming soon',
        'settings.filter.title': 'Email Filtering',
        'settings.filter.desc': 'Only emails matching these filters will be processed.',
        'settings.filter.mode': 'Filter Mode',
        'settings.filter.mode.either': 'Either (domain OR keyword)',
        'settings.filter.mode.domain': 'Domain only',
        'settings.filter.mode.keyword': 'Keyword only',
        'settings.filter.mode.both': 'Both (domain AND keyword)',
        'settings.filter.domains': 'Allowed Domains',
        'settings.filter.domains.desc': 'Only process emails FROM these domains (one per line)',
        'settings.filter.keywords': 'Subject Keywords',
        'settings.filter.keywords.desc': 'Only process emails with these words in subject (one per line)',
        'settings.filter.save': 'Save Filters',
        'settings.properties.title': 'Properties',
        'settings.properties.add': 'Add Property',
        'settings.properties.empty': 'No properties configured yet',
        'settings.language.title': 'Language',
        'settings.language.ui': 'Interface Language',

        // Common
        'common.save': 'Save',
        'common.cancel': 'Cancel',
        'common.delete': 'Delete',
        'common.edit': 'Edit',
        'common.add': 'Add',
        'common.close': 'Close',
        'common.confirm': 'Confirm',
        'common.loading': 'Loading...',
        'common.error': 'Error',
        'common.success': 'Success',
        'common.noData': 'No data available',

        // Notifications
        'notify.saved': 'Successfully saved',
        'notify.deleted': 'Successfully deleted',
        'notify.error': 'An error occurred',
        'notify.emailSent': 'Email sent',
        'notify.aiResponse': 'AI response generated',

        // Platforms
        'platform.email': 'Email',
        'platform.whatsapp': 'WhatsApp',
        'platform.airbnb': 'Airbnb',
        'platform.booking': 'Booking.com'
    }
};

// i18n Manager
const i18n = {
    currentLanguage: localStorage.getItem('chatbot_language') || 'de',

    /**
     * Get translation for a key
     */
    t(key) {
        const lang = translations[this.currentLanguage] || translations.de;
        return lang[key] || translations.de[key] || key;
    },

    /**
     * Set current language
     */
    setLanguage(lang) {
        if (translations[lang]) {
            this.currentLanguage = lang;
            localStorage.setItem('chatbot_language', lang);
            this.updatePage();
            return true;
        }
        return false;
    },

    /**
     * Get current language
     */
    getLanguage() {
        return this.currentLanguage;
    },

    /**
     * Get all available languages
     */
    getAvailableLanguages() {
        return [
            { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
            { code: 'en', name: 'English', flag: '🇬🇧' }
        ];
    },

    /**
     * Update all translatable elements on the page
     */
    updatePage() {
        // Update elements with data-i18n attribute
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            el.textContent = this.t(key);
        });

        // Update placeholders with data-i18n-placeholder attribute
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            el.placeholder = this.t(key);
        });

        // Update titles with data-i18n-title attribute
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            el.title = this.t(key);
        });

        // Update the language selector if it exists
        const langSelector = document.getElementById('languageSelector');
        if (langSelector) {
            langSelector.value = this.currentLanguage;
        }

        // Dispatch event for custom handlers
        document.dispatchEvent(new CustomEvent('languageChanged', {
            detail: { language: this.currentLanguage }
        }));
    },

    /**
     * Initialize i18n on page load
     */
    init() {
        // Apply translations on DOM ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.updatePage());
        } else {
            this.updatePage();
        }
    }
};

// Auto-initialize
i18n.init();

// Export for use in other scripts
window.i18n = i18n;
window.t = (key) => i18n.t(key);
