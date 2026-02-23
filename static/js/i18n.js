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
        'inbox.empty.hint': 'Wenn Gäste Ihnen schreiben, erscheinen ihre Konversationen hier.',
        'inbox.unread': 'Ungelesen',
        'inbox.ai.enabled': 'KI aktiviert',
        'inbox.ai.disabled': 'KI deaktiviert',
        'inbox.filter.allGuests': 'Alle Gäste',
        'inbox.search.noResults': 'Keine Ergebnisse gefunden',
        'inbox.search.noMatches': 'Keine Treffer für',
        'inbox.search.suggestions': 'Vorschläge:',
        'inbox.search.suggestion1': 'Überprüfen Sie die Rechtschreibung',
        'inbox.search.suggestion2': 'Versuchen Sie andere Suchbegriffe',
        'inbox.search.suggestion3': 'Suchen Sie nach Gastnamen oder Nachrichteninhalt',
        'inbox.search.clear': 'Suche löschen',

        // Conversation
        'conversation.title': 'Konversation',
        'conversation.send': 'Senden',
        'conversation.placeholder': 'Nachricht eingeben...',
        'conversation.ai.suggest': 'KI-Vorschlag',
        'conversation.ai.generate': 'KI-Antwort senden',
        'conversation.ai.generating': 'Generiere...',
        'conversation.ai.error': 'KI nicht erreichbar. Läuft Ollama?',
        'conversation.ai.thinking': 'KI denkt nach...',
        'conversation.ai.toggle': 'KI-Antworten',
        'conversation.ai.on': 'AN',
        'conversation.ai.off': 'AUS',
        'conversation.guest.profile': 'Gästeprofil anzeigen',
        'conversation.you': 'Sie',
        'conversation.guest': 'Gast',
        'conversation.ai': 'KI-Assistent',
        'conversation.empty': 'Noch keine Nachrichten',
        'conversation.sendHint': 'Strg+Enter zum Senden',
        'conversation.sendFailed': 'Nachricht konnte nicht gesendet werden. Bitte versuchen Sie es erneut.',

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
        'guest.conversations.empty': 'Noch keine Konversationen',
        'guest.stats.stays': 'Aufenthalte',
        'guest.stats.first': 'Erster Kontakt',
        'guest.stats.last': 'Letzter Kontakt',
        'guest.language': 'Bevorzugte Sprache',
        'guest.memories.aiExtracted': 'KI-extrahiert',
        'guest.memories.noFamily': 'Keine Familienmitglieder erfasst',
        'guest.memories.noPets': 'Keine Haustiere erfasst',
        'guest.memories.noPreferences': 'Keine Vorlieben erfasst',
        'guest.memories.noAllergies': 'Keine Allergien erfasst',
        'guest.memories.noInterests': 'Keine Interessen erfasst',
        'guest.memories.noRequests': 'Keine Sonderwünsche erfasst',
        'guest.notes': 'Private Notizen',
        'guest.notes.placeholder': 'Private Notizen über diesen Gast hinzufügen...',
        'guest.notes.save': 'Notizen speichern',
        'guest.edit.title': 'Gastinformationen bearbeiten',

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
        'settings.ai.tone.desc': 'Ton für KI-generierte Antworten auswählen',
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
        'settings.integrations.configure': 'Konfigurieren',
        'settings.integrations.fetchEmails': 'E-Mails abrufen',
        'settings.integrations.processUnread': 'Ungelesene verarbeiten',
        'settings.integrations.gmailHelp': 'Abrufen importiert E-Mails in den Posteingang. Verarbeiten führt KI auf ungelesene E-Mails aus.',
        'settings.properties.help': 'Unterkünfte helfen der KI, relevantere Antworten zu geben.',
        'settings.filter.mode.desc': 'Wie Domain- und Schlüsselwortfilter angewendet werden',
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
        'common.refresh': 'Aktualisieren',

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
        'inbox.empty.hint': 'When guests message you, their conversations will appear here.',
        'inbox.unread': 'Unread',
        'inbox.ai.enabled': 'AI enabled',
        'inbox.ai.disabled': 'AI disabled',
        'inbox.filter.allGuests': 'All Guests',
        'inbox.search.noResults': 'No results found',
        'inbox.search.noMatches': 'No matches for',
        'inbox.search.suggestions': 'Suggestions:',
        'inbox.search.suggestion1': 'Check your spelling',
        'inbox.search.suggestion2': 'Try different keywords',
        'inbox.search.suggestion3': 'Search for guest names or message content',
        'inbox.search.clear': 'Clear Search',

        // Conversation
        'conversation.title': 'Conversation',
        'conversation.send': 'Send',
        'conversation.placeholder': 'Type a message...',
        'conversation.ai.suggest': 'AI Suggest',
        'conversation.ai.generate': 'Send AI Response',
        'conversation.ai.generating': 'Generating...',
        'conversation.ai.error': 'AI not reachable. Is Ollama running?',
        'conversation.ai.thinking': 'AI is thinking...',
        'conversation.ai.toggle': 'AI Responses',
        'conversation.ai.on': 'ON',
        'conversation.ai.off': 'OFF',
        'conversation.guest.profile': 'View Guest Profile',
        'conversation.you': 'You',
        'conversation.guest': 'Guest',
        'conversation.ai': 'AI Assistant',
        'conversation.empty': 'No messages yet',
        'conversation.sendHint': 'Ctrl+Enter to send',
        'conversation.sendFailed': 'Failed to send message. Please try again.',

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
        'guest.conversations.empty': 'No conversations yet',
        'guest.stats.stays': 'Stays',
        'guest.stats.first': 'First Contact',
        'guest.stats.last': 'Last Contact',
        'guest.language': 'Preferred Language',
        'guest.memories.aiExtracted': 'AI-Extracted',
        'guest.memories.noFamily': 'No family members recorded',
        'guest.memories.noPets': 'No pets recorded',
        'guest.memories.noPreferences': 'No preferences recorded',
        'guest.memories.noAllergies': 'No allergies recorded',
        'guest.memories.noInterests': 'No interests recorded',
        'guest.memories.noRequests': 'No special requests recorded',
        'guest.notes': 'Private Notes',
        'guest.notes.placeholder': 'Add private notes about this guest...',
        'guest.notes.save': 'Save Notes',
        'guest.edit.title': 'Edit Guest Information',

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
        'settings.ai.tone.desc': 'Select the tone for AI-generated responses',
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
        'settings.integrations.configure': 'Configure',
        'settings.integrations.fetchEmails': 'Fetch Emails',
        'settings.integrations.processUnread': 'Process Unread',
        'settings.integrations.gmailHelp': 'Fetch imports emails into inbox. Process runs AI on unread emails.',
        'settings.properties.help': 'Properties help the AI provide more relevant responses about your rentals.',
        'settings.filter.title': 'Email Filtering',
        'settings.filter.mode.desc': 'How to apply domain and keyword filters',
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
        'common.refresh': 'Refresh',

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
