/**
 * Knowledge Base management
 * CRUD operations, property filtering, category grouping
 */

const CATEGORY_LABELS = {
    general: { de: 'Allgemeine Infos', en: 'General Info' },
    checkin_checkout: { de: 'Check-in / Check-out', en: 'Check-in / Check-out' },
    nearby: { de: 'In der Nähe', en: 'Nearby Places' },
    house_rules: { de: 'Hausregeln', en: 'House Rules' },
    emergency: { de: 'Notfallkontakte', en: 'Emergency Contacts' },
    faq: { de: 'Häufige Fragen', en: 'FAQ / Common Questions' },
    escalation: { de: 'Eskalation', en: 'Escalation' },
};

const CATEGORY_ICONS = {
    general: 'fa-info-circle',
    checkin_checkout: 'fa-key',
    nearby: 'fa-map-marker-alt',
    house_rules: 'fa-clipboard-list',
    emergency: 'fa-phone-alt',
    faq: 'fa-question-circle',
    escalation: 'fa-exclamation-triangle',
};

const CATEGORY_ORDER = ['general', 'checkin_checkout', 'nearby', 'house_rules', 'emergency', 'faq', 'escalation'];

const knowledgeApp = {
    entries: [],

    async loadEntries() {
        const filter = document.getElementById('propertyFilter').value;
        let url = '/chatbot/api/knowledge';
        if (filter) url += `?property_id=${encodeURIComponent(filter)}`;

        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error('Failed to load');
            this.entries = await resp.json();
            this.renderEntries();
        } catch (e) {
            console.error('Failed to load knowledge entries:', e);
            document.getElementById('entriesContainer').innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas fa-exclamation-triangle" style="font-size:24px;color:var(--danger-color);"></i>' +
                '<p>' + (typeof i18n !== 'undefined' ? i18n.t('knowledge.error.load') : 'Fehler beim Laden') + '</p></div></div>';
        }
    },

    renderEntries() {
        const container = document.getElementById('entriesContainer');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';

        if (!this.entries.length) {
            container.innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas fa-book-open" style="font-size:48px;margin-bottom:15px;opacity:0.3;"></i>' +
                '<p style="font-size:16px;">' + (typeof i18n !== 'undefined' ? i18n.t('knowledge.empty') : 'Noch keine Einträge vorhanden') + '</p>' +
                '<p style="font-size:14px;opacity:0.7;">' + (typeof i18n !== 'undefined' ? i18n.t('knowledge.empty.hint') : 'Fügen Sie Fakten hinzu, die die KI bei Gästeanfragen nutzen soll.') + '</p></div></div>';
            return;
        }

        // Group by category
        const grouped = {};
        for (const entry of this.entries) {
            const cat = entry.category || 'general';
            if (!grouped[cat]) grouped[cat] = [];
            grouped[cat].push(entry);
        }

        let html = '';
        for (const cat of CATEGORY_ORDER) {
            const entries = grouped[cat];
            if (!entries || !entries.length) continue;

            const catLabel = CATEGORY_LABELS[cat] ? CATEGORY_LABELS[cat][lang] || CATEGORY_LABELS[cat].de : cat;
            const catIcon = CATEGORY_ICONS[cat] || 'fa-folder';

            html += '<div class="settings-card" style="margin-bottom: 15px;">';
            html += '<div class="card-header"><h2><i class="fas ' + catIcon + '"></i> ' + this.escapeHtml(catLabel) + '</h2></div>';
            html += '<div class="card-body" style="padding: 0;">';

            for (const entry of entries) {
                const scopeBadge = entry.property_name
                    ? '<span class="badge" style="background:var(--primary-color);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">' + this.escapeHtml(entry.property_name) + '</span>'
                    : '<span class="badge" style="background:var(--text-secondary);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">Global</span>';

                html += '<div class="setting-item" style="padding: 12px 20px; border-bottom: 1px solid var(--border-color);">';
                html += '<div style="flex: 1; min-width: 0;">';
                html += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;">';
                html += '<strong>' + this.escapeHtml(entry.label) + '</strong>' + scopeBadge;
                html += '</div>';
                html += '<div style="color:var(--text-secondary);margin-top:4px;white-space:pre-line;">' + this.escapeHtml(entry.value) + '</div>';
                html += '</div>';
                html += '<div style="display:flex;gap:8px;margin-left:10px;">';
                html += '<button class="btn btn-icon" onclick="knowledgeApp.openEditModal(' + entry.id + ')" title="Edit"><i class="fas fa-pencil-alt"></i></button>';
                html += '<button class="btn btn-icon" onclick="knowledgeApp.deleteEntry(' + entry.id + ')" title="Delete" style="color:var(--danger-color);"><i class="fas fa-trash"></i></button>';
                html += '</div>';
                html += '</div>';
            }

            html += '</div></div>';
        }

        container.innerHTML = html;
    },

    openAddModal() {
        document.getElementById('entryId').value = '';
        document.getElementById('knowledgeForm').reset();
        document.querySelector('input[name="scope"][value="global"]').checked = true;
        this.toggleScope();
        const titleEl = document.getElementById('modalTitle');
        titleEl.setAttribute('data-i18n', 'knowledge.add');
        titleEl.textContent = typeof i18n !== 'undefined' ? i18n.t('knowledge.add') : 'Eintrag hinzufügen';
        document.getElementById('knowledgeModal').showModal();
    },

    openEditModal(id) {
        const entry = this.entries.find(e => e.id === id);
        if (!entry) return;

        document.getElementById('entryId').value = entry.id;
        document.getElementById('entryCategory').value = entry.category;
        document.getElementById('entryLabel').value = entry.label;
        document.getElementById('entryValue').value = entry.value;

        if (entry.property_id) {
            document.querySelector('input[name="scope"][value="property"]').checked = true;
            document.getElementById('entryPropertyId').value = entry.property_id;
        } else {
            document.querySelector('input[name="scope"][value="global"]').checked = true;
        }
        this.toggleScope();

        const titleEl = document.getElementById('modalTitle');
        titleEl.setAttribute('data-i18n', 'knowledge.edit');
        titleEl.textContent = typeof i18n !== 'undefined' ? i18n.t('knowledge.edit') : 'Eintrag bearbeiten';
        document.getElementById('knowledgeModal').showModal();
    },

    closeModal() {
        document.getElementById('knowledgeModal').close();
    },

    toggleScope() {
        const isProperty = document.querySelector('input[name="scope"][value="property"]').checked;
        document.getElementById('propertySelectRow').style.display = isProperty ? 'flex' : 'none';
    },

    async saveEntry(event) {
        event.preventDefault();
        const id = document.getElementById('entryId').value;
        const isProperty = document.querySelector('input[name="scope"][value="property"]').checked;

        const data = {
            category: document.getElementById('entryCategory').value,
            label: document.getElementById('entryLabel').value.trim(),
            value: document.getElementById('entryValue').value.trim(),
            property_id: isProperty ? parseInt(document.getElementById('entryPropertyId').value) : null,
        };

        try {
            const url = id ? `/chatbot/api/knowledge/${id}` : '/chatbot/api/knowledge';
            const method = id ? 'PUT' : 'POST';
            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });

            if (!resp.ok) {
                const err = await resp.json();
                alert(err.error || 'Save failed');
                return;
            }

            this.closeModal();
            this.loadEntries();
        } catch (e) {
            console.error('Save failed:', e);
            alert('Save failed');
        }
    },

    async deleteEntry(id) {
        const msg = typeof i18n !== 'undefined' ? i18n.t('knowledge.delete.confirm') : 'Eintrag wirklich löschen?';
        if (!confirm(msg)) return;

        try {
            const resp = await fetch(`/chatbot/api/knowledge/${id}`, { method: 'DELETE' });
            if (!resp.ok) throw new Error('Delete failed');
            this.loadEntries();
        } catch (e) {
            console.error('Delete failed:', e);
            alert('Delete failed');
        }
    },

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// Load entries on page ready
document.addEventListener('DOMContentLoaded', () => knowledgeApp.loadEntries());
