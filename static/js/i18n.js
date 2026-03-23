/**
 * Internationalization (i18n) for ChatBotAI
 * Supports German (default) and English
 */

const translations = {
    de: {
        // Navigation
        'nav.inbox': 'Posteingang',
        'nav.settings': 'Einstellungen',
        'nav.knowledge': 'Wissensdatenbank',
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

        // Inbox Date Groups
        'inbox.group.today': 'Heute',
        'inbox.group.yesterday': 'Gestern',
        'inbox.group.thisWeek': 'Diese Woche',
        'inbox.group.thisMonth': 'Diesen Monat',
        'inbox.group.older': 'Älter',

        // Conversation
        'conversation.title': 'Konversation',
        'conversation.send': 'Senden',
        'conversation.placeholder': 'Nachricht eingeben...',
        'conversation.ai.suggest': 'KI-Vorschlag',
        'conversation.ai.generate': 'KI-Antwort senden',
        'conversation.ai.generating': 'Generiere...',
        'conversation.ai.error': 'KI nicht erreichbar. Läuft Ollama?',
        'conversation.ai.no_response_needed': 'Keine Antwort nötig — Gast hat Ihre Nachricht bestätigt.',
        'conversation.ai.thinking': 'KI denkt nach...',
        'conversation.ai.toggle': 'KI-Antworten',
        'conversation.ai.autoRespond': 'Automatische KI-Antwort',
        'conversation.ai.autoRespond.on': 'Automatische Antwort aktiviert',
        'conversation.ai.autoRespond.off': 'Automatische Antwort deaktiviert',
        'conversation.ai.masterOff': 'KI-Hauptschalter ist AUS (Einstellungen)',
        'conversation.ai.on': 'AN',
        'conversation.ai.off': 'AUS',
        'conversation.guest.profile': 'Gästeprofil anzeigen',
        'conversation.you': 'Sie',
        'conversation.guest': 'Gast',
        'conversation.ai': 'KI-Assistent',
        'conversation.empty': 'Noch keine Nachrichten',
        'conversation.loadOlder': 'Ältere Nachrichten laden',
        'conversation.sendHint': 'Strg+Enter zum Senden',
        'conversation.draft': 'Entwurf gespeichert',
        'conversation.date.today': 'Heute',
        'conversation.date.yesterday': 'Gestern',
        'conversation.sendFailed': 'Nachricht konnte nicht gesendet werden. Bitte versuchen Sie es erneut.',
        'conversation.property.assign': 'Unterkunft zuweisen',
        'conversation.property.none': '-- Unterkunft --',
        'conversation.property.assigned': 'Unterkunft zugewiesen: ',
        'conversation.property.removed': 'Unterkunft entfernt',

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

        // Guest Merge
        'guest.merge.title': 'Zusammenführen',
        'guest.merge.description': 'Wählen Sie einen Gast, der in dieses Profil zusammengeführt werden soll. Alle Konversationen und Erinnerungen werden übertragen.',
        'guest.merge.selectGuest': 'Gast auswählen',
        'guest.merge.preview': 'Vorschau',
        'guest.merge.conversations': 'Konversationen',
        'guest.merge.details': 'Erinnerungen',
        'guest.merge.platforms': 'Plattformen',
        'guest.merge.warning': 'Der ausgewählte Gast wird nach dem Zusammenführen gelöscht. Diese Aktion kann nicht rückgängig gemacht werden.',
        'guest.merge.confirm': 'Zusammenführen bestätigen',
        'guest.merge.success': 'Gäste erfolgreich zusammengeführt',

        // Settings
        'settings.title': 'Einstellungen',
        'settings.ai.title': 'KI-Konfiguration',
        'settings.ai.masterSwitch': 'KI-Hauptschalter',
        'settings.ai.masterSwitch.desc': 'Wenn AUS, werden keine automatischen Antworten gesendet — gilt für alle Konversationen',
        'settings.ai.autoRespondNew': 'Auto-Antwort für neue Konversationen',
        'settings.ai.autoRespondNew.desc': 'Neue Konversationen starten mit aktivierter automatischer Antwort',
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
        'settings.ai.hostInstructions': 'Host-Anweisungen',
        'settings.ai.hostInstructions.desc': 'Eigene Anweisungen, die die KI bei jeder Antwort berücksichtigen soll',
        'settings.ai.hostInstructions.placeholder': 'z.B. WiFi-Passwort: SunnyBeach2024\nErwähne unseren 10% Rabatt bei 7+ Nächten\nCheck-in ab 15 Uhr an der Rezeption',
        'settings.ai.knowledgeLink': 'Für strukturierte Fakten (WLAN, Check-in, Umgebung) nutze die',
        'settings.ai.knowledgeLinkText': 'Wissensdatenbank →',
        'settings.ai.temperature': 'Temperatur',
        'settings.ai.temperature.desc': 'Kreativität der KI-Antworten (0.0 = vorhersagbar, 1.0 = kreativ)',
        'settings.ai.maxTokens': 'Max. Tokens',
        'settings.ai.maxTokens.desc': 'Maximale Länge der KI-Antworten (128-4096)',
        'settings.ai.save': 'Einstellungen speichern',
        'settings.server.title': 'KI-Server Status',
        'settings.server.connected': 'Verbunden und läuft',
        'settings.server.disconnected': 'Nicht verbunden',
        'settings.server.checking': 'Verbindung wird geprüft...',
        'settings.server.test': 'KI-Verbindung testen',
        'settings.server.url': 'Server-URL',
        'settings.server.model': 'Modell',
        'settings.model.title': 'KI-Modell',
        'settings.model.active': 'Aktives Modell',
        'settings.model.change': 'Modell wechseln',
        'settings.model.change.desc': 'Wählen Sie ein installiertes Modell aus. Größere Modelle sind intelligenter, brauchen aber mehr Speicher.',
        'settings.model.loading': 'Modelle werden geladen...',
        'settings.model.quality': 'Qualität',
        'settings.model.speed': 'Geschwindigkeit',
        'settings.model.apply': 'Modell anwenden',
        'settings.model.suggested': 'Empfohlene Modelle',
        'settings.model.suggested.desc': 'Diese Modelle sind noch nicht installiert. Führen Sie den Befehl in Ihrem Terminal aus, um sie herunterzuladen.',
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
        'settings.properties.name': 'Name *',
        'settings.properties.address': 'Adresse',
        'settings.language.title': 'Sprache',
        'settings.language.ui': 'Oberflächensprache',

        // Quick Reply Templates
        'settings.templates.title': 'Schnellantwort-Vorlagen',
        'settings.templates.add': 'Vorlage hinzufügen',
        'settings.templates.empty': 'Noch keine Vorlagen erstellt',
        'settings.templates.help': 'Vorlagen sparen Zeit bei häufig gesendeten Nachrichten.',
        'settings.templates.name': 'Name *',
        'settings.templates.category': 'Kategorie',
        'settings.templates.content': 'Inhalt *',

        // Conversation Templates
        'conversation.templates': 'Vorlagen',
        'conversation.templates.empty': 'Keine Vorlagen vorhanden',

        // Dashboard Stats
        'inbox.stats.conversations': 'Konversationen',
        'inbox.stats.unread': 'Ungelesen',
        'inbox.stats.messagesToday': 'Nachrichten heute',
        'inbox.stats.activeGuests': 'Aktive Gäste',

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
        'notify.sound': 'Sound',
        'notify.desktop': 'Desktop',
        'notify.push': 'Push',
        'notify.sound.enabled': 'Sound aktiviert',
        'notify.sound.disabled': 'Sound deaktiviert',
        'notify.desktop.enabled': 'Benachrichtigungen aktiviert',
        'notify.desktop.disabled': 'Benachrichtigungen deaktiviert',
        'notify.push.enabled': 'Push-Benachrichtigungen aktiviert',
        'notify.push.disabled': 'Push-Benachrichtigungen deaktiviert',
        'notify.push.unsupported': 'Push-Benachrichtigungen werden von diesem Browser nicht unterstützt',
        'notify.push.denied': 'Benachrichtigungsberechtigung verweigert',

        // Auth
        'auth.login': 'Anmelden',
        'auth.logout': 'Abmelden',
        'auth.username': 'Benutzername',
        'auth.password': 'Passwort',
        'auth.passwordConfirm': 'Passwort bestätigen',
        'auth.displayName': 'Anzeigename',
        'auth.displayNameHint': 'Wird in der Anwendung angezeigt',
        'auth.usernameHint': 'Zum Anmelden verwendet',
        'auth.rememberMe': 'Angemeldet bleiben',
        'auth.createAccount': 'Konto erstellen',
        'auth.loginSubtitle': 'Melden Sie sich an, um fortzufahren',
        'auth.setupSubtitle': 'Erstellen Sie den ersten Benutzer',

        // User Management
        'settings.users.title': 'Benutzerverwaltung',
        'settings.users.add': 'Benutzer hinzufügen',
        'settings.users.delete': 'Benutzer löschen',
        'settings.users.resetPassword': 'Passwort zurücksetzen',
        'settings.users.help': 'Alle Benutzer haben gleiche Rechte. Jeder kann andere Benutzer hinzufügen oder entfernen.',

        // Platforms
        'platform.email': 'E-Mail',
        'platform.whatsapp': 'WhatsApp',
        'platform.airbnb': 'Airbnb',
        'platform.booking': 'Booking.com',
        'platform.smoobu': 'Smoobu',

        // Smoobu Integration
        'settings.integrations.smoobu': 'Smoobu',
        'settings.integrations.smoobu.apiKey': 'API-Schlüssel',
        'settings.integrations.smoobu.connect': 'Verbinden',
        'settings.integrations.smoobu.disconnect': 'Trennen',
        'settings.integrations.smoobu.connected': 'Verbunden',
        'settings.integrations.smoobu.syncMessages': 'Nachrichten synchronisieren',
        'settings.integrations.smoobu.syncProperties': 'Unterkünfte synchronisieren',
        'settings.integrations.smoobu.syncing': 'Synchronisiere...',
        'settings.integrations.smoobu.synced': '{count} neue Nachricht(en) synchronisiert',
        'settings.integrations.smoobu.propertiesSynced': '{count} Unterkunft(en) synchronisiert',
        'inbox.syncSmoobu': 'Smoobu Sync',
        'inbox.markAllRead': 'Alle gelesen',
        'inbox.markedAllRead': '{count} als gelesen markiert',
        'inbox.closeChat': 'Gespräch beenden',
        'inbox.closeChat.failed': 'Gespräch konnte nicht beendet werden',

        // Statistics — Team Performance
        'nav.statistics': 'Team-Leistung',
        'stats.title': 'Team-Leistung',
        'stats.overview.teamMembers': 'Teammitglieder',
        'stats.overview.messagesSent': 'Gesendete Nachrichten',
        'stats.overview.thisWeek': 'diese Woche',
        'stats.overview.conversations': 'Konversationen',
        'stats.overview.avgResponse': 'Ø Antwortzeit',
        'stats.overview.noData': 'k.A.',
        'stats.team.title': 'Teamübersicht',
        'stats.team.user': 'Benutzer',
        'stats.team.messagesWeek': 'Nachr. (7 Tage)',
        'stats.team.messagesMonth': 'Nachr. (30 Tage)',
        'stats.team.messagesTotal': 'Nachr. Gesamt',
        'stats.team.assigned': 'Konversationen',
        'stats.team.avgResponse': 'Ø Antwortzeit',
        'stats.team.lastActive': 'Letzte Aktivität',
        'stats.team.inactive': 'Inaktiv',
        'stats.team.justNow': 'Gerade eben',
        'stats.team.comparison': 'Nachrichten pro Benutzer (7 Tage)',
        'stats.team.dailyTitle': 'Tagesaktivität pro Benutzer',
        'stats.loading': 'Statistiken werden geladen...',
        'stats.error': 'Fehler beim Laden der Statistiken',

        // Knowledge Base
        'knowledge.title': 'Wissensdatenbank',
        'knowledge.add': 'Eintrag hinzufügen',
        'knowledge.edit': 'Eintrag bearbeiten',
        'knowledge.save': 'Speichern',
        'knowledge.cancel': 'Abbrechen',
        'knowledge.filter.property': 'Unterkunft:',
        'knowledge.filter.all': 'Alle',
        'knowledge.filter.global': 'Global',
        'knowledge.scope': 'Geltungsbereich',
        'knowledge.scope.global': 'Global',
        'knowledge.scope.property': 'Pro Unterkunft',
        'knowledge.property': 'Unterkunft',
        'knowledge.category': 'Kategorie',
        'knowledge.label': 'Bezeichnung',
        'knowledge.label.placeholder': 'z.B. WLAN-Passwort',
        'knowledge.value': 'Information',
        'knowledge.value.placeholder': 'z.B. SunnyBeach2024',
        'knowledge.loading': 'Lade Einträge...',
        'knowledge.empty': 'Noch keine Einträge vorhanden',
        'knowledge.empty.hint': 'Fügen Sie Fakten hinzu, die die KI bei Gästeanfragen nutzen soll.',
        'knowledge.error.load': 'Fehler beim Laden der Einträge',
        'knowledge.delete.confirm': 'Eintrag wirklich löschen?',
        'knowledge.cat.general': 'Allgemeine Infos',
        'knowledge.cat.checkin': 'Check-in / Check-out',
        'knowledge.cat.nearby': 'In der Nähe',
        'knowledge.cat.rules': 'Hausregeln',
        'knowledge.cat.emergency': 'Notfallkontakte',
        'knowledge.cat.faq': 'Häufige Fragen',
        'knowledge.cat.escalation': 'Eskalation',

        // Mobile Navigation & Account
        'nav.account': 'Konto',
        'conversation.back': 'Zurück',
        'account.darkMode': 'Dunkelmodus',
        'account.sound': 'Ton',
        'account.push': 'Push',
        'account.language': 'Sprache',
        'account.logout': 'Abmelden'
    },

    en: {
        // Navigation
        'nav.inbox': 'Inbox',
        'nav.settings': 'Settings',
        'nav.knowledge': 'Knowledge Base',
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

        // Inbox Date Groups
        'inbox.group.today': 'Today',
        'inbox.group.yesterday': 'Yesterday',
        'inbox.group.thisWeek': 'This Week',
        'inbox.group.thisMonth': 'This Month',
        'inbox.group.older': 'Older',

        // Conversation
        'conversation.title': 'Conversation',
        'conversation.send': 'Send',
        'conversation.placeholder': 'Type a message...',
        'conversation.ai.suggest': 'AI Suggest',
        'conversation.ai.generate': 'Send AI Response',
        'conversation.ai.generating': 'Generating...',
        'conversation.ai.error': 'AI not reachable. Is Ollama running?',
        'conversation.ai.no_response_needed': 'No response needed — guest acknowledged your message.',
        'conversation.ai.thinking': 'AI is thinking...',
        'conversation.ai.toggle': 'AI Responses',
        'conversation.ai.autoRespond': 'Automatic AI Response',
        'conversation.ai.autoRespond.on': 'Auto-respond enabled',
        'conversation.ai.autoRespond.off': 'Auto-respond disabled',
        'conversation.ai.masterOff': 'AI Master Switch is OFF (Settings)',
        'conversation.ai.on': 'ON',
        'conversation.ai.off': 'OFF',
        'conversation.guest.profile': 'View Guest Profile',
        'conversation.you': 'You',
        'conversation.guest': 'Guest',
        'conversation.ai': 'AI Assistant',
        'conversation.empty': 'No messages yet',
        'conversation.loadOlder': 'Load older messages',
        'conversation.sendHint': 'Ctrl+Enter to send',
        'conversation.draft': 'Draft saved',
        'conversation.date.today': 'Today',
        'conversation.date.yesterday': 'Yesterday',
        'conversation.sendFailed': 'Failed to send message. Please try again.',
        'conversation.property.assign': 'Assign property',
        'conversation.property.none': '-- Property --',
        'conversation.property.assigned': 'Property assigned: ',
        'conversation.property.removed': 'Property removed',

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

        // Guest Merge
        'guest.merge.title': 'Merge',
        'guest.merge.description': 'Select a guest to merge into this profile. All conversations and memories will be transferred.',
        'guest.merge.selectGuest': 'Select Guest',
        'guest.merge.preview': 'Preview',
        'guest.merge.conversations': 'Conversations',
        'guest.merge.details': 'Memories',
        'guest.merge.platforms': 'Platforms',
        'guest.merge.warning': 'The selected guest will be deleted after merging. This action cannot be undone.',
        'guest.merge.confirm': 'Confirm Merge',
        'guest.merge.success': 'Guests merged successfully',

        // Settings
        'settings.title': 'Settings',
        'settings.ai.title': 'AI Configuration',
        'settings.ai.masterSwitch': 'AI Master Switch',
        'settings.ai.masterSwitch.desc': 'When OFF, no auto-responses will be sent — applies to all conversations',
        'settings.ai.autoRespondNew': 'Auto-respond for new conversations',
        'settings.ai.autoRespondNew.desc': 'New conversations start with auto-respond enabled',
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
        'settings.ai.hostInstructions': 'Host Instructions',
        'settings.ai.hostInstructions.desc': 'Custom instructions the AI should follow in every response',
        'settings.ai.hostInstructions.placeholder': 'e.g. WiFi password: SunnyBeach2024\nMention our 10% discount for 7+ night stays\nCheck-in from 3 PM at reception',
        'settings.ai.knowledgeLink': 'For structured facts (WiFi, check-in, nearby places), use the',
        'settings.ai.knowledgeLinkText': 'Knowledge Base →',
        'settings.ai.temperature': 'Temperature',
        'settings.ai.temperature.desc': 'AI response creativity (0.0 = predictable, 1.0 = creative)',
        'settings.ai.maxTokens': 'Max Tokens',
        'settings.ai.maxTokens.desc': 'Maximum length of AI responses (128-4096)',
        'settings.ai.save': 'Save Settings',
        'settings.server.title': 'AI Server Status',
        'settings.server.connected': 'Connected and running',
        'settings.server.disconnected': 'Not connected',
        'settings.server.checking': 'Checking connection...',
        'settings.server.test': 'Test AI Connection',
        'settings.server.url': 'Server URL',
        'settings.server.model': 'Model',
        'settings.model.title': 'AI Model',
        'settings.model.active': 'Active Model',
        'settings.model.change': 'Change Model',
        'settings.model.change.desc': 'Select an installed model. Larger models are smarter but need more memory.',
        'settings.model.loading': 'Loading models...',
        'settings.model.quality': 'Quality',
        'settings.model.speed': 'Speed',
        'settings.model.apply': 'Apply Model',
        'settings.model.suggested': 'Recommended Models',
        'settings.model.suggested.desc': 'These models are not installed yet. Run the command in your terminal to download them.',
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
        'settings.properties.name': 'Name *',
        'settings.properties.address': 'Address',
        'settings.language.title': 'Language',
        'settings.language.ui': 'Interface Language',

        // Quick Reply Templates
        'settings.templates.title': 'Quick Reply Templates',
        'settings.templates.add': 'Add Template',
        'settings.templates.empty': 'No templates created yet',
        'settings.templates.help': 'Templates save time for frequently sent messages.',
        'settings.templates.name': 'Name *',
        'settings.templates.category': 'Category',
        'settings.templates.content': 'Content *',

        // Conversation Templates
        'conversation.templates': 'Templates',
        'conversation.templates.empty': 'No templates available',

        // Dashboard Stats
        'inbox.stats.conversations': 'Conversations',
        'inbox.stats.unread': 'Unread',
        'inbox.stats.messagesToday': 'Messages Today',
        'inbox.stats.activeGuests': 'Active Guests',

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
        'notify.sound': 'Sound',
        'notify.desktop': 'Desktop',
        'notify.push': 'Push',
        'notify.sound.enabled': 'Sound enabled',
        'notify.sound.disabled': 'Sound disabled',
        'notify.desktop.enabled': 'Notifications enabled',
        'notify.desktop.disabled': 'Notifications disabled',
        'notify.push.enabled': 'Push notifications enabled',
        'notify.push.disabled': 'Push notifications disabled',
        'notify.push.unsupported': 'Push notifications not supported by this browser',
        'notify.push.denied': 'Notification permission denied',

        // Auth
        'auth.login': 'Login',
        'auth.logout': 'Logout',
        'auth.username': 'Username',
        'auth.password': 'Password',
        'auth.passwordConfirm': 'Confirm Password',
        'auth.displayName': 'Display Name',
        'auth.displayNameHint': 'Shown in the application',
        'auth.usernameHint': 'Used for login',
        'auth.rememberMe': 'Remember me',
        'auth.createAccount': 'Create Account',
        'auth.loginSubtitle': 'Sign in to continue',
        'auth.setupSubtitle': 'Create the first user account',

        // User Management
        'settings.users.title': 'User Management',
        'settings.users.add': 'Add User',
        'settings.users.delete': 'Delete User',
        'settings.users.resetPassword': 'Reset Password',
        'settings.users.help': 'All users have equal rights. Anyone can add or remove other users.',

        // Platforms
        'platform.email': 'Email',
        'platform.whatsapp': 'WhatsApp',
        'platform.airbnb': 'Airbnb',
        'platform.booking': 'Booking.com',
        'platform.smoobu': 'Smoobu',

        // Smoobu Integration
        'settings.integrations.smoobu': 'Smoobu',
        'settings.integrations.smoobu.apiKey': 'API Key',
        'settings.integrations.smoobu.connect': 'Connect',
        'settings.integrations.smoobu.disconnect': 'Disconnect',
        'settings.integrations.smoobu.connected': 'Connected',
        'settings.integrations.smoobu.syncMessages': 'Sync Messages',
        'settings.integrations.smoobu.syncProperties': 'Sync Properties',
        'settings.integrations.smoobu.syncing': 'Syncing...',
        'settings.integrations.smoobu.synced': '{count} new message(s) synced',
        'settings.integrations.smoobu.propertiesSynced': '{count} property(ies) synced',
        'inbox.syncSmoobu': 'Smoobu Sync',
        'inbox.markAllRead': 'Mark all read',
        'inbox.markedAllRead': '{count} marked as read',
        'inbox.closeChat': 'Close chat',
        'inbox.closeChat.failed': 'Failed to close conversation',

        // Statistics — Team Performance
        'nav.statistics': 'Team Performance',
        'stats.title': 'Team Performance',
        'stats.overview.teamMembers': 'Team Members',
        'stats.overview.messagesSent': 'Messages Sent',
        'stats.overview.thisWeek': 'this week',
        'stats.overview.conversations': 'Conversations',
        'stats.overview.avgResponse': 'Avg Response',
        'stats.overview.noData': 'N/A',
        'stats.team.title': 'Team Overview',
        'stats.team.user': 'User',
        'stats.team.messagesWeek': 'Msgs (7 Days)',
        'stats.team.messagesMonth': 'Msgs (30 Days)',
        'stats.team.messagesTotal': 'Msgs Total',
        'stats.team.assigned': 'Conversations',
        'stats.team.avgResponse': 'Avg Response',
        'stats.team.lastActive': 'Last Active',
        'stats.team.inactive': 'Inactive',
        'stats.team.justNow': 'Just now',
        'stats.team.comparison': 'Messages per User (7 Days)',
        'stats.team.dailyTitle': 'Daily Activity per User',
        'stats.loading': 'Loading statistics...',
        'stats.error': 'Error loading statistics',

        // Knowledge Base
        'knowledge.title': 'Knowledge Base',
        'knowledge.add': 'Add Entry',
        'knowledge.edit': 'Edit Entry',
        'knowledge.save': 'Save',
        'knowledge.cancel': 'Cancel',
        'knowledge.filter.property': 'Property:',
        'knowledge.filter.all': 'All',
        'knowledge.filter.global': 'Global',
        'knowledge.scope': 'Scope',
        'knowledge.scope.global': 'Global',
        'knowledge.scope.property': 'Per Property',
        'knowledge.property': 'Property',
        'knowledge.category': 'Category',
        'knowledge.label': 'Label',
        'knowledge.label.placeholder': 'e.g. WiFi Password',
        'knowledge.value': 'Information',
        'knowledge.value.placeholder': 'e.g. SunnyBeach2024',
        'knowledge.loading': 'Loading entries...',
        'knowledge.empty': 'No entries yet',
        'knowledge.empty.hint': 'Add facts that the AI should use when responding to guests.',
        'knowledge.error.load': 'Failed to load entries',
        'knowledge.delete.confirm': 'Really delete this entry?',
        'knowledge.cat.general': 'General Info',
        'knowledge.cat.checkin': 'Check-in / Check-out',
        'knowledge.cat.nearby': 'Nearby Places',
        'knowledge.cat.rules': 'House Rules',
        'knowledge.cat.emergency': 'Emergency Contacts',
        'knowledge.cat.faq': 'FAQ / Common Questions',
        'knowledge.cat.escalation': 'Escalation',

        // Mobile Navigation & Account
        'nav.account': 'Account',
        'conversation.back': 'Back',
        'account.darkMode': 'Dark Mode',
        'account.sound': 'Sound',
        'account.push': 'Push',
        'account.language': 'Language',
        'account.logout': 'Logout'
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
