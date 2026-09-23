/**
 * UMI page: personality settings + quick-reply templates.
 *
 * These used to be inline in settings.html, which is admin-only — so the team
 * that actually answers guests could not reach them. Loaded by both pages: the
 * admin sections of settings.html still use the save* helpers.
 */

// ============================================
// Instant-save helpers for global settings
// ============================================

function _saveSetting(key, value, okMessage) {
    const data = {};
    data[key] = value;
    return fetch('/chatbot/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (!result.success) {
            showNotification('Failed to save setting', 'error');
        } else if (okMessage) {
            showNotification(okMessage, 'success');
        }
    })
    .catch(err => showNotification('Error: ' + err.message, 'error'));
}

function saveRangeSetting(key, value) {
    return _saveSetting(key, String(value), null);
}

function saveToggleSetting(key, checked) {
    return _saveSetting(key, checked ? 'true' : 'false', checked ? 'Enabled' : 'Disabled');
}

function saveTextSetting(key, value) {
    return _saveSetting(key, value, 'Gespeichert');
}

// ============================================
// Bulk Auto-Approve
// ============================================

async function bulkAutoApprove(enabled) {
    try {
        const response = await fetch('/chatbot/api/settings/bulk-auto-approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
        });
        const data = await response.json();
        if (data.success) {
            showNotification(
                `Auto-Freigabe für ${data.updated_count} Konversationen ${enabled ? 'aktiviert' : 'deaktiviert'}`,
                'success'
            );
        }
    } catch (error) {
        showNotification('Fehler beim Aktualisieren', 'error');
    }
}

// ============================================
// Personality form
// ============================================

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('aiSettingsForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        // Temperature and max-tokens render for admins only — read them defensively,
        // a non-admin must still be able to save the rest of the form.
        const val = (id) => {
            const el = document.getElementById(id);
            return el ? el.value : null;
        };
        const settings = {
            memory_extraction_enabled: document.getElementById('memoryExtraction').checked ? 'true' : 'false',
            ai_response_tone: val('responseTone'),
            max_conversation_history: val('maxHistory'),
            host_instructions: val('hostInstructions'),
        };
        if (val('aiTemperature') !== null) settings.ai_temperature = val('aiTemperature');
        if (val('aiMaxTokens') !== null) settings.ai_max_tokens = val('aiMaxTokens');

        fetch('/chatbot/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        })
        .then(response => response.json())
        .then(data => {
            showNotification(
                data.success ? 'Einstellungen gespeichert' : 'Failed to save settings',
                data.success ? 'success' : 'error'
            );
        })
        .catch(err => showNotification('Error saving settings: ' + err.message, 'error'));
    });
});

// ============================================
// Reply Templates Management
// ============================================

let editingTemplateId = null;

function _tplEscape(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function loadTemplates() {
    const list = document.getElementById('templatesList');
    if (!list) return;
    fetch('/chatbot/api/reply-templates')
        .then(response => response.json())
        .then(data => {
            const empty = document.getElementById('templatesEmpty');
            if (!data.templates || data.templates.length === 0) {
                list.innerHTML = '';
                empty.style.display = 'block';
                return;
            }
            empty.style.display = 'none';
            list.innerHTML = data.templates.map(tpl => `
                <div class="template-item" data-template-id="${tpl.id}">
                    <div class="template-info">
                        <span class="template-name">${_tplEscape(tpl.name)}</span>
                        <span class="template-category">${_tplEscape(tpl.category)}</span>
                        <span class="template-preview">${_tplEscape(tpl.content.substring(0, 80))}${tpl.content.length > 80 ? '...' : ''}</span>
                    </div>
                    <div class="template-actions">
                        <button class="btn btn-icon btn-sm" onclick="editTemplate(${tpl.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-icon btn-sm" onclick="deleteTemplate(${tpl.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `).join('');
        })
        .catch(err => console.error('Failed to load templates:', err));
}

function openTemplateModal(templateData) {
    editingTemplateId = templateData ? templateData.id : null;
    const modal = document.getElementById('templateModal');
    const form = document.getElementById('templateForm');
    const title = modal.querySelector('.modal-header h2');

    title.textContent = editingTemplateId ? 'Vorlage bearbeiten' : 'Vorlage hinzufügen';
    form.reset();

    if (templateData) {
        document.getElementById('tplName').value = templateData.name || '';
        document.getElementById('tplCategory').value = templateData.category || 'general';
        document.getElementById('tplContent').value = templateData.content || '';
    }

    modal.showModal();
}

function editTemplate(templateId) {
    fetch('/chatbot/api/reply-templates')
        .then(r => r.json())
        .then(data => {
            const tpl = data.templates.find(t => t.id === templateId);
            if (tpl) openTemplateModal(tpl);
        });
}

function deleteTemplate(templateId) {
    if (!confirm('Vorlage wirklich löschen?')) return;

    fetch(`/chatbot/api/reply-templates/${templateId}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showNotification('Vorlage gelöscht', 'success');
                loadTemplates();
            }
        })
        .catch(err => showNotification('Error: ' + err.message, 'error'));
}

function saveTemplate() {
    const data = {
        name: document.getElementById('tplName').value.trim(),
        category: document.getElementById('tplCategory').value.trim() || 'general',
        content: document.getElementById('tplContent').value.trim()
    };

    if (!data.name || !data.content) {
        showNotification('Name und Inhalt sind erforderlich', 'error');
        return;
    }

    const url = editingTemplateId
        ? `/chatbot/api/reply-templates/${editingTemplateId}`
        : '/chatbot/api/reply-templates';

    fetch(url, {
        method: editingTemplateId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(result => {
        if (result.error) {
            showNotification('Error: ' + result.error, 'error');
        } else {
            showNotification(editingTemplateId ? 'Vorlage aktualisiert' : 'Vorlage hinzugefügt', 'success');
            document.getElementById('templateModal').close();
            loadTemplates();
        }
    })
    .catch(err => showNotification('Error: ' + err.message, 'error'));
}
