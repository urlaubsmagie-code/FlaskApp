/**
 * Knowledge Base management
 * CRUD operations, property filtering, category grouping, tabbed layout
 */

const CATEGORY_LABELS = {
    general: { de: 'Allgemeine Infos', en: 'General Info' },
    checkin_checkout: { de: 'Check-in / Check-out', en: 'Check-in / Check-out' },
    nearby: { de: 'In der Nähe', en: 'Nearby Places' },
    house_rules: { de: 'Hausregeln', en: 'House Rules' },
    emergency: { de: 'Notfallkontakte', en: 'Emergency Contacts' },
    faq: { de: 'Häufige Fragen', en: 'FAQ / Common Questions' },
    esc_maintenance: { de: 'Wartung / Reparatur', en: 'Maintenance / Repair' },
    esc_cleanliness: { de: 'Sauberkeit', en: 'Cleanliness' },
    esc_noise: { de: 'Lärm / Nachbarn', en: 'Noise / Neighbors' },
    esc_payment: { de: 'Zahlung / Erstattung', en: 'Payment / Refund' },
    esc_access: { de: 'Schlüssel / Zugang', en: 'Keys / Access' },
    esc_emergency: { de: 'Notfall', en: 'Emergency' },
    esc_other: { de: 'Sonstiges', en: 'Other' },
    correction: { de: 'Korrektur', en: 'Correction' },
};

const CATEGORY_ICONS = {
    general: 'fa-info-circle',
    checkin_checkout: 'fa-key',
    nearby: 'fa-map-marker-alt',
    house_rules: 'fa-clipboard-list',
    emergency: 'fa-phone-alt',
    faq: 'fa-question-circle',
    esc_maintenance: 'fa-wrench',
    esc_cleanliness: 'fa-broom',
    esc_noise: 'fa-volume-up',
    esc_payment: 'fa-credit-card',
    esc_access: 'fa-key',
    esc_emergency: 'fa-ambulance',
    esc_other: 'fa-ellipsis-h',
    correction: 'fa-spell-check',
};

const CATEGORY_ORDER = ['general', 'checkin_checkout', 'nearby', 'house_rules', 'emergency', 'faq',
    'esc_maintenance', 'esc_cleanliness', 'esc_noise', 'esc_payment', 'esc_access', 'esc_emergency', 'esc_other',
    'correction'];

const KNOWLEDGE_CATEGORIES = ['general', 'checkin_checkout', 'nearby', 'house_rules', 'emergency', 'faq'];
const ESCALATION_CATEGORIES = ['esc_maintenance', 'esc_cleanliness', 'esc_noise', 'esc_payment', 'esc_access', 'esc_emergency', 'esc_other'];

const knowledgeApp = {
    entries: [],
    currentTab: 'knowledge',

    switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.knowledge-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        // Update URL param without reload
        const url = new URL(window.location);
        url.searchParams.set('tab', tab);
        history.replaceState(null, '', url);
        this.renderEntries();
    },

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
        // Filter entries based on current tab
        let filtered;
        if (this.currentTab === 'knowledge') {
            filtered = this.entries.filter(e => KNOWLEDGE_CATEGORIES.includes(e.category || 'general'));
        } else if (this.currentTab === 'escalation') {
            filtered = this.entries.filter(e => ESCALATION_CATEGORIES.includes(e.category) || e.category === 'escalation');
        } else if (this.currentTab === 'corrections') {
            filtered = this.entries.filter(e => e.category === 'correction');
            this.renderCorrections(filtered);
            return;
        }

        const container = document.getElementById('entriesContainer');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';

        if (!filtered.length) {
            let emptyText, hintText, icon;
            if (this.currentTab === 'escalation') {
                emptyText = typeof i18n !== 'undefined' ? i18n.t('knowledge.empty') : 'Noch keine Einträge vorhanden';
                hintText = typeof i18n !== 'undefined' ? i18n.t('knowledge.empty.hint') : 'Fügen Sie Fakten hinzu, die UMI bei Gästeanfragen nutzen soll.';
                icon = 'fa-exclamation-triangle';
            } else {
                emptyText = typeof i18n !== 'undefined' ? i18n.t('knowledge.empty') : 'Noch keine Einträge vorhanden';
                hintText = typeof i18n !== 'undefined' ? i18n.t('knowledge.empty.hint') : 'Fügen Sie Fakten hinzu, die UMI bei Gästeanfragen nutzen soll.';
                icon = 'fa-book-open';
            }
            container.innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas ' + icon + '" style="font-size:48px;margin-bottom:15px;opacity:0.3;"></i>' +
                '<p style="font-size:16px;">' + emptyText + '</p>' +
                '<p style="font-size:14px;opacity:0.7;">' + hintText + '</p></div></div>';
            return;
        }

        // Group by category
        const grouped = {};
        for (const entry of filtered) {
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

    renderCorrections(entries) {
        const container = document.getElementById('entriesContainer');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';

        if (!entries.length) {
            const emptyText = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.empty') : 'Noch keine Korrekturen';
            const hintText = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.empty.hint') : 'Wenn Sie UMI-Entwürfe bearbeiten, lernt UMI automatisch daraus.';
            container.innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas fa-spell-check" style="font-size:48px;margin-bottom:15px;opacity:0.3;"></i>' +
                '<p style="font-size:16px;">' + emptyText + '</p>' +
                '<p style="font-size:14px;opacity:0.7;">' + hintText + '</p></div></div>';
            return;
        }

        const originalLabel = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.original') : 'UMI sagte';
        const correctedLabel = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.corrected') : 'Richtig ist';

        let html = '<div class="settings-card"><div class="card-body" style="padding: 0;">';

        for (const entry of entries) {
            const scopeBadge = entry.property_name
                ? '<span class="badge" style="background:var(--primary-color);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">' + this.escapeHtml(entry.property_name) + '</span>'
                : '<span class="badge" style="background:var(--text-secondary);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">Global</span>';

            // Parse FALSCH:/RICHTIG: format
            let originalText = '';
            let correctedText = '';
            const value = entry.value || '';
            if (value.includes('\nRICHTIG: ')) {
                const parts = value.split('\nRICHTIG: ');
                originalText = parts[0].replace('FALSCH: ', '');
                correctedText = parts[1];
            } else {
                correctedText = value;
            }

            const date = entry.created_at ? new Date(entry.created_at).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-US') : '';

            html += '<div class="correction-entry">';
            html += '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:5px;">';
            html += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;">';
            html += '<strong>' + this.escapeHtml(entry.label) + '</strong>' + scopeBadge;
            html += '<span style="color:var(--text-light);font-size:12px;margin-left:8px;">' + date + '</span>';
            html += '</div>';
            html += '<div style="display:flex;gap:8px;">';
            html += '<button class="btn btn-icon" onclick="knowledgeApp.openEditModal(' + entry.id + ')" title="Edit"><i class="fas fa-pencil-alt"></i></button>';
            html += '<button class="btn btn-icon" onclick="knowledgeApp.deleteEntry(' + entry.id + ')" title="Delete" style="color:var(--danger-color);"><i class="fas fa-trash"></i></button>';
            html += '</div></div>';

            html += '<div class="correction-pair">';
            if (originalText) {
                html += '<div class="correction-original"><strong>' + originalLabel + ':</strong> ' + this.escapeHtml(originalText.substring(0, 200)) + (originalText.length > 200 ? '...' : '') + '</div>';
            }
            html += '<div class="correction-corrected"><strong>' + correctedLabel + ':</strong> ' + this.escapeHtml(correctedText.substring(0, 200)) + (correctedText.length > 200 ? '...' : '') + '</div>';
            html += '</div></div>';
        }

        html += '</div></div>';
        container.innerHTML = html;
    },

    // Filter category dropdown to show only options relevant to the current tab
    updateCategoryOptions(selectedValue) {
        const select = document.getElementById('entryCategory');
        const categoryRow = select.closest('.setting-item');
        const valueRow = document.getElementById('entryValue').closest('.setting-item');
        const allOptions = select.querySelectorAll('option');

        // Hide category entirely for corrections
        if (this.currentTab === 'corrections') {
            categoryRow.style.display = 'none';
            valueRow.style.display = '';
            select.value = 'correction';
            return;
        }

        // Hide Information field for escalation (category + label is enough)
        valueRow.style.display = this.currentTab === 'escalation' ? 'none' : '';
        categoryRow.style.display = '';

        let allowedCategories;
        if (this.currentTab === 'escalation') {
            allowedCategories = ESCALATION_CATEGORIES;
        } else {
            allowedCategories = KNOWLEDGE_CATEGORIES;
        }

        allOptions.forEach(opt => {
            opt.style.display = allowedCategories.includes(opt.value) ? '' : 'none';
        });

        // Set selected value
        if (selectedValue && allowedCategories.includes(selectedValue)) {
            select.value = selectedValue;
        } else {
            select.value = allowedCategories[0];
        }
    },

    openAddModal() {
        document.getElementById('entryId').value = '';
        document.getElementById('knowledgeForm').reset();
        document.querySelector('input[name="scope"][value="global"]').checked = true;
        this.toggleScope();
        this.updateCategoryOptions();

        const titleEl = document.getElementById('modalTitle');
        titleEl.setAttribute('data-i18n', 'knowledge.add');
        titleEl.textContent = typeof i18n !== 'undefined' ? i18n.t('knowledge.add') : 'Eintrag hinzufügen';
        document.getElementById('knowledgeModal').showModal();
    },

    openEditModal(id) {
        const entry = this.entries.find(e => e.id === id);
        if (!entry) return;

        document.getElementById('entryId').value = entry.id;
        document.getElementById('entryLabel').value = entry.label;
        document.getElementById('entryValue').value = entry.value;
        this.updateCategoryOptions(entry.category);

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

// Load entries on page ready, restore tab from URL
document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab && ['knowledge', 'escalation', 'corrections'].includes(tab)) {
        knowledgeApp.currentTab = tab;
        document.querySelectorAll('.knowledge-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
    }
    knowledgeApp.loadEntries();
});
