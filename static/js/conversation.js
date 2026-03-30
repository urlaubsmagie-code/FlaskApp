/**
 * ChatBotAI - Conversation Page JavaScript
 * Extracted from inline <script> in conversation.html for browser caching.
 *
 * Requires window.CONV_CONFIG to be set by the template before this script loads:
 *   { conversationId, aiEnabled, autoRespond, platform, gmailConnected,
 *     smoobuConnected, currentPropertyId, guestName, guestNotifyName,
 *     propertyName, checkInTime }
 */

const cfg = window.CONV_CONFIG;
const conversationId = cfg.conversationId;
let aiEnabled = cfg.aiEnabled;
let autoRespond = cfg.autoRespond;
const conversationPlatform = cfg.platform;
const gmailConnected = cfg.gmailConnected;
const smoobuConnected = cfg.smoobuConnected;
const currentPropertyId = cfg.currentPropertyId;
const draftKey = 'chatbot_draft_' + conversationId;
let approvalQueueEnabled = cfg.approvalQueueEnabled || false;
let autoApprove = cfg.autoApprove || false;

// Pending correction: stores original AI text when host edits a draft
let pendingCorrectionOriginal = null;

// Load properties into the selector
function loadPropertySelector() {
    fetch('/chatbot/api/properties')
        .then(r => r.json())
        .then(data => {
            const select = document.getElementById('propertySelector');
            const defaultOption = select.querySelector('option[value=""]');
            select.innerHTML = '';
            select.appendChild(defaultOption);

            (data.properties || []).forEach(prop => {
                const option = document.createElement('option');
                option.value = prop.id;
                option.textContent = prop.name;
                if (currentPropertyId && prop.id === currentPropertyId) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        })
        .catch(err => console.error('Failed to load properties:', err));
}

function assignProperty(propertyId) {
    fetch(`/chatbot/api/conversations/${conversationId}/property`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ property_id: propertyId || null })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const name = data.property_name;
            showNotification(
                name ? (i18n.t('conversation.property.assigned') || 'Property assigned: ') + name
                     : (i18n.t('conversation.property.removed') || 'Property removed'),
                'success'
            );
        }
    })
    .catch(err => console.error('Failed to assign property:', err));
}

// Track known message IDs to prevent duplicates
let knownMessageIds = new Set();
let maxKnownMessageId = 0;

// Build set of message IDs on page load
document.querySelectorAll('[data-message-id]').forEach(el => {
    const id = parseInt(el.dataset.messageId);
    knownMessageIds.add(id);
    if (id > maxKnownMessageId) maxKnownMessageId = id;
});

// Load older messages (pagination)
function loadOlderMessages() {
    const btn = document.getElementById('loadOlderBtn');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Laden...';

    let minId = Infinity;
    knownMessageIds.forEach(id => { if (id < minId) minId = id; });

    fetch(`/chatbot/api/conversations/${conversationId}/messages?before=${minId}&limit=50`)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('messagesContainer');
            const wrapper = document.getElementById('loadOlderWrapper');

            const scrollHeightBefore = container.scrollHeight;

            const fragment = document.createDocumentFragment();
            data.messages.forEach(msg => {
                if (knownMessageIds.has(msg.id)) return;
                knownMessageIds.add(msg.id);

                const msgDiv = document.createElement('div');
                msgDiv.className = `message ${msg.sender_type}`;
                msgDiv.dataset.messageId = msg.id;
                msgDiv.dataset.sentAt = msg.sent_at || '';

                const icon = msg.sender_type === 'guest' ? 'fa-user' : (msg.sender_type === 'owner' ? 'fa-home' : 'fa-robot');
                const name = msg.sender_type === 'guest' ? cfg.guestName
                    : (msg.sender_type === 'owner' ? (msg.sender_name || 'Team') : 'KI');
                let time = '';
                if (msg.sent_at) {
                    const d = new Date(msg.sent_at);
                    time = d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                }
                const suggestBtn = msg.sender_type === 'guest'
                    ? `<button class="btn-suggest-for-message" onclick="suggestForMessage(${msg.id})"
                        data-i18n-title="conversation.ai.suggestForMessage"
                        title="${i18n.t('conversation.ai.suggestForMessage')}"
                        ${!aiEnabled ? 'disabled' : ''}>
                        <i class="fas fa-lightbulb"></i>
                       </button>`
                    : '';
                msgDiv.innerHTML = `
                    <div class="message-avatar"><i class="fas ${icon}"></i></div>
                    <div class="message-content">
                        <div class="message-header">
                            <span class="sender-name">${name}</span>
                            <span class="message-header-right">
                                ${suggestBtn}
                                <span class="message-time">${time}</span>
                            </span>
                        </div>
                        <div class="message-text">${escapeHtml(msg.content || '')}</div>
                    </div>
                `;
                fragment.appendChild(msgDiv);
            });

            if (wrapper) {
                wrapper.after(fragment);
            } else {
                container.prepend(fragment);
            }

            const scrollHeightAfter = container.scrollHeight;
            container.scrollTop += (scrollHeightAfter - scrollHeightBefore);

            if (data.has_more) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-arrow-up"></i> <span data-i18n="conversation.loadOlder">Ältere Nachrichten laden</span>';
            } else {
                if (wrapper) wrapper.remove();
            }

            insertInitialDateDividers();
        })
        .catch(err => {
            console.error('Failed to load older messages:', err);
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-arrow-up"></i> <span data-i18n="conversation.loadOlder">Ältere Nachrichten laden</span>';
        });
}

// =========================================================================
// Message Date Dividers
// =========================================================================
let knownDateDividers = new Set();

function getDateKey(dateString) {
    if (!dateString) return null;
    const d = new Date(dateString);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function formatDateDivider(dateString) {
    const d = new Date(dateString);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const msgDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((today - msgDay) / 86400000);

    if (diffDays === 0) return i18n.t('conversation.date.today');
    if (diffDays === 1) return i18n.t('conversation.date.yesterday');

    const lang = i18n.getLanguage() === 'de' ? 'de-DE' : 'en-US';
    return d.toLocaleDateString(lang, { day: 'numeric', month: 'long', year: 'numeric' });
}

function createDateDivider(dateString) {
    const div = document.createElement('div');
    div.className = 'message-date-divider';
    div.dataset.dateKey = getDateKey(dateString);
    div.innerHTML = `<span>${formatDateDivider(dateString)}</span>`;
    return div;
}

function insertInitialDateDividers() {
    const container = document.getElementById('messagesContainer');
    // Remove existing dividers to avoid duplicates on re-insert
    container.querySelectorAll('.message-date-divider').forEach(d => d.remove());
    knownDateDividers.clear();

    const messages = container.querySelectorAll('.message[data-sent-at]');
    let lastDateKey = null;

    messages.forEach(msg => {
        const dateKey = getDateKey(msg.dataset.sentAt);
        if (dateKey && dateKey !== lastDateKey) {
            const divider = createDateDivider(msg.dataset.sentAt);
            container.insertBefore(divider, msg);
            knownDateDividers.add(dateKey);
            lastDateKey = dateKey;
        }
    });
}

// Ctrl+Enter / Cmd+Enter to send
document.getElementById('messageInput').addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        sendMessage(e);
    }
});

// Auto-save draft with debounce
let draftTimeout = null;
document.getElementById('messageInput').addEventListener('input', function() {
    const value = this.value;
    const indicator = document.getElementById('draftIndicator');
    if (draftTimeout) clearTimeout(draftTimeout);
    draftTimeout = setTimeout(() => {
        if (value.trim()) {
            localStorage.setItem(draftKey, value);
            if (indicator) indicator.classList.add('visible');
            setTimeout(() => { if (indicator) indicator.classList.remove('visible'); }, 2000);
        } else {
            localStorage.removeItem(draftKey);
        }
    }, 500);
});

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    const lastMessage = container.querySelector('.message:last-child');
    if (lastMessage) {
        lastMessage.scrollIntoView({ behavior: 'smooth', block: 'end' });
    } else {
        container.scrollTop = container.scrollHeight;
    }
}

// =========================================================================
// Quick Reply Templates
// =========================================================================

let replyTemplates = [];

function loadReplyTemplates() {
    fetch('/chatbot/api/reply-templates')
        .then(r => r.json())
        .then(data => {
            replyTemplates = data.templates || [];
            buildTemplateMenu();
        })
        .catch(err => console.error('Failed to load templates:', err));
}

function buildTemplateMenu() {
    const menu = document.getElementById('templateMenu');
    if (!replyTemplates.length) {
        menu.innerHTML = '<div class="template-menu-empty" data-i18n="conversation.templates.empty">Keine Vorlagen vorhanden</div>';
        return;
    }

    const grouped = {};
    replyTemplates.forEach(tpl => {
        const cat = tpl.category || 'general';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(tpl);
    });

    let html = '';
    Object.entries(grouped).forEach(([category, templates]) => {
        html += `<div class="template-menu-category">${escapeHtml(category)}</div>`;
        templates.forEach(tpl => {
            html += `<button class="template-menu-item" onclick="insertTemplate(${tpl.id})" type="button">
                <span class="template-menu-name">${escapeHtml(tpl.name)}</span>
                <span class="template-menu-preview">${escapeHtml(tpl.content.substring(0, 50))}${tpl.content.length > 50 ? '...' : ''}</span>
            </button>`;
        });
    });

    menu.innerHTML = html;
}

function toggleTemplateDropdown() {
    const menu = document.getElementById('templateMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function insertTemplate(templateId) {
    const tpl = replyTemplates.find(t => t.id === templateId);
    if (!tpl) return;

    const input = document.getElementById('messageInput');
    let content = tpl.content
        .replace(/\{guest_name\}/g, cfg.guestName)
        .replace(/\{property_name\}/g, cfg.propertyName)
        .replace(/\{check_in_time\}/g, cfg.checkInTime);

    input.value = content;
    localStorage.setItem(draftKey, content);
    input.focus();
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';

    document.getElementById('templateMenu').style.display = 'none';
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    const dropdown = document.getElementById('templateDropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        document.getElementById('templateMenu').style.display = 'none';
    }
});

// Load templates and properties on page init
loadReplyTemplates();
loadPropertySelector();

function sendMessage(e) {
    e.preventDefault();
    const input = document.getElementById('messageInput');
    const content = input.value.trim();

    if (!content) {
        pendingCorrectionOriginal = null;
        return;
    }

    const tempId = Date.now();
    addMessageToUI({ id: tempId, content: content, sent_at: new Date().toISOString() }, 'owner');
    knownMessageIds.add(tempId);
    input.value = '';
    input.style.height = 'auto';
    localStorage.removeItem(draftKey);
    scrollToBottom();

    // Capture and clear correction tracking before dispatching
    const correctionOriginal = pendingCorrectionOriginal;
    pendingCorrectionOriginal = null;

    if (conversationPlatform === 'email' && gmailConnected) {
        sendViaGmail(content, tempId, correctionOriginal);
    } else if (conversationPlatform === 'smoobu' && smoobuConnected) {
        sendViaSmoobu(content, tempId, correctionOriginal);
    } else {
        sendLocal(content, tempId, correctionOriginal);
    }
}

function sendLocal(content, tempId, correctionOriginal) {
    fetch(`/chatbot/api/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            content: content,
            ...(correctionOriginal && { original_ai_content: correctionOriginal })
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.id) {
            knownMessageIds.delete(tempId);
            knownMessageIds.add(data.id);
            const el = document.querySelector(`[data-message-id="${tempId}"]`);
            if (el) el.dataset.messageId = data.id;
        }
        if (data.correction_saved) {
            showNotification(i18n.t('knowledge.corrections.autoSaved'), 'info', 3000);
        }
    })
    .catch(err => {
        console.error('Failed to send message:', err);
        showNotification(i18n.t('conversation.sendFailed'), 'error');
    });
}

function sendViaGmail(content, tempId, correctionOriginal) {
    fetch(`/chatbot/api/gmail/reply/${conversationId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, ...(correctionOriginal && { original_ai_content: correctionOriginal }) })
    })
    .then(response => {
        if (response.status === 401) {
            console.warn('Gmail disconnected, falling back to local send');
            sendLocal(content, tempId, correctionOriginal);
            return null;
        }
        return response.json();
    })
    .then(data => {
        if (!data) return;
        if (data.error) {
            console.warn('Gmail send failed, falling back to local:', data.error);
            sendLocal(content, tempId, correctionOriginal);
            return;
        }
        if (data.message_id) {
            knownMessageIds.delete(tempId);
            knownMessageIds.add(data.message_id);
            const el = document.querySelector(`[data-message-id="${tempId}"]`);
            if (el) el.dataset.messageId = data.message_id;
        }
        showNotification(i18n.t('conversation.gmail.sent') || 'Email sent via Gmail', 'success');
        if (correctionOriginal) {
            showNotification(i18n.t('knowledge.corrections.autoSaved'), 'info', 3000);
        }
    })
    .catch(err => {
        console.error('Gmail send error, falling back to local:', err);
        sendLocal(content, tempId, correctionOriginal);
    });
}

function sendViaSmoobu(content, tempId, correctionOriginal) {
    fetch(`/chatbot/api/smoobu/reply/${conversationId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, ...(correctionOriginal && { original_ai_content: correctionOriginal }) })
    })
    .then(response => {
        if (!response.ok && response.status !== 200) {
            return response.json().then(data => { throw new Error(data.error || 'Send failed'); });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            console.warn('Smoobu send failed, falling back to local:', data.error);
            sendLocal(content, tempId, correctionOriginal);
            return;
        }
        if (data.message_id) {
            knownMessageIds.delete(tempId);
            knownMessageIds.add(data.message_id);
            const el = document.querySelector(`[data-message-id="${tempId}"]`);
            if (el) el.dataset.messageId = data.message_id;
        }
        showNotification('Message sent via Smoobu', 'success');
        if (correctionOriginal) {
            showNotification(i18n.t('knowledge.corrections.autoSaved'), 'info', 3000);
        }
    })
    .catch(err => {
        console.error('Smoobu send error, falling back to local:', err);
        sendLocal(content, tempId, correctionOriginal);
    });
}

// Active AbortControllers for AI requests
let activeAiController = null;

function showAiError(message) {
    const container = document.querySelector('.message-input-container');
    const existing = container.querySelector('.ai-error-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.className = 'ai-error-banner';
    banner.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`;
    banner.style.cssText = 'background:#991b1b;color:#fff;padding:8px 16px;border-radius:6px;margin-bottom:8px;font-size:0.9em;display:flex;align-items:center;gap:8px;';
    container.insertBefore(banner, container.firstChild);
    setTimeout(() => banner.remove(), 6000);
}

function showTypingIndicator() {
    removeTypingIndicator();
    const container = document.getElementById('messagesContainer');
    const typing = document.createElement('div');
    typing.className = 'message typing-indicator message-slide-in';
    typing.id = 'aiTypingIndicator';
    typing.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-content">
            <div class="typing-dots"><span></span><span></span><span></span></div>
            <div class="typing-label" data-i18n="conversation.ai.thinking">${i18n.t('conversation.ai.thinking')}</div>
        </div>
    `;
    container.appendChild(typing);
    scrollToBottom();
}

function removeTypingIndicator() {
    const el = document.getElementById('aiTypingIndicator');
    if (el) el.remove();
}

function generateAIResponse() {
    pendingCorrectionOriginal = null;
    const btn = document.getElementById('generateAiBtn');
    const suggestBtn = document.getElementById('suggestAiBtn');
    btn.disabled = true;
    suggestBtn.disabled = true;
    btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> <span data-i18n="conversation.ai.generating">${i18n.t('conversation.ai.generating')}</span>`;

    showTypingIndicator();

    if (activeAiController) activeAiController.abort();
    activeAiController = new AbortController();
    const signal = activeAiController.signal;

    fetch(`/chatbot/api/conversations/${conversationId}/ai-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: signal
    })
    .then(response => response.json())
    .then(data => {
        removeTypingIndicator();
        if (data.error) {
            showAiError(data.error);
        } else {
            // Handle approval queue response
            const msg = data.message || data;
            if (msg.id) {
                knownMessageIds.add(msg.id);
            }
            addMessageToUI(msg, 'ai');
            scrollToBottom();

            if (data.approval_status === 'pending') {
                showNotification(i18n.t('conversation.approval.created'), 'info');
            } else if (conversationPlatform === 'email') {
                if (data.email_sent) {
                    showNotification(i18n.t('conversation.ai.emailSent') || 'AI response sent via email', 'success');
                } else if (gmailConnected) {
                    showNotification(i18n.t('conversation.ai.emailFailed') || 'AI response saved but email delivery failed', 'warning');
                }
            }
        }
    })
    .catch(err => {
        removeTypingIndicator();
        if (err.name === 'AbortError') return;
        console.error('Failed to generate AI response:', err);
        showAiError(i18n.t('conversation.ai.error') || 'AI not reachable. Is Ollama running?');
    })
    .finally(() => {
        activeAiController = null;
        btn.disabled = !aiEnabled;
        suggestBtn.disabled = !aiEnabled;
        btn.innerHTML = `<i class="fas fa-magic"></i> <span data-i18n="conversation.ai.create">${i18n.t('conversation.ai.create')}</span>`;
    });
}

function suggestAIResponse() {
    pendingCorrectionOriginal = null;
    const btn = document.getElementById('suggestAiBtn');
    const generateBtn = document.getElementById('generateAiBtn');
    const input = document.getElementById('messageInput');
    btn.disabled = true;
    generateBtn.disabled = true;
    btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> <span data-i18n="conversation.ai.generating">${i18n.t('conversation.ai.generating')}</span>`;

    if (activeAiController) activeAiController.abort();
    activeAiController = new AbortController();
    const signal = activeAiController.signal;

    fetch(`/chatbot/api/conversations/${conversationId}/ai-suggest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ debug: true }),
        signal: signal
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showAiError(data.error);
        } else if (data.skipped) {
            // Acknowledgment detected — no AI response needed
            const msg = i18n.t('conversation.ai.no_response_needed') || 'No response needed — guest acknowledged your message.';
            showNotification(msg, 'info', 5000);
            if (data.debug_context) {
                console.log('AI Skipped:', data.debug_context);
            }
        } else {
            input.value = data.suggestion;
            localStorage.setItem(draftKey, data.suggestion);
            input.focus();
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 200) + 'px';

            if (data.debug_context) {
                const ctx = data.debug_context;
                console.log('AI Context:', ctx);
                const contextInfo = `AI read: "${ctx.latest_guest_message?.substring(0, 50) || '?'}..." | ${ctx.messages_count} msgs | Profile: ${ctx.guest_profile?.name || 'none'} | Property: ${ctx.property || 'none'} | Reservation: ${ctx.reservation ? 'yes' : 'no'}`;
                showNotification(contextInfo, 'info', 8000);
            }
        }
    })
    .catch(err => {
        if (err.name === 'AbortError') return;
        console.error('Failed to generate AI suggestion:', err);
        showAiError(i18n.t('conversation.ai.error') || 'AI not reachable. Is Ollama running?');
    })
    .finally(() => {
        activeAiController = null;
        btn.disabled = !aiEnabled;
        generateBtn.disabled = !aiEnabled;
        btn.innerHTML = `<i class="fas fa-lightbulb"></i> <span data-i18n="conversation.ai.suggest">${i18n.t('conversation.ai.suggest')}</span>`;
    });
}

function suggestForMessage(messageId) {
    pendingCorrectionOriginal = null;
    const input = document.getElementById('messageInput');
    const suggestBtn = document.getElementById('suggestAiBtn');
    const generateBtn = document.getElementById('generateAiBtn');

    // Find and animate the clicked lightbulb button
    const msgDiv = document.querySelector(`.message[data-message-id="${messageId}"]`);
    const perMsgBtn = msgDiv ? msgDiv.querySelector('.btn-suggest-for-message') : null;

    // Disable all AI buttons during generation
    suggestBtn.disabled = true;
    generateBtn.disabled = true;
    if (perMsgBtn) {
        perMsgBtn.disabled = true;
        perMsgBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    if (activeAiController) activeAiController.abort();
    activeAiController = new AbortController();
    const signal = activeAiController.signal;

    fetch(`/chatbot/api/conversations/${conversationId}/ai-suggest-for-message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId }),
        signal: signal
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showAiError(data.error);
        } else {
            input.value = data.suggestion;
            localStorage.setItem(draftKey, data.suggestion);
            input.focus();
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 200) + 'px';
            // Scroll to the input area so the host sees the draft
            input.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    })
    .catch(err => {
        if (err.name === 'AbortError') return;
        console.error('Failed to generate per-message AI suggestion:', err);
        showAiError(i18n.t('conversation.ai.error') || 'AI not reachable. Is Ollama running?');
    })
    .finally(() => {
        activeAiController = null;
        suggestBtn.disabled = !aiEnabled;
        generateBtn.disabled = !aiEnabled;
        if (perMsgBtn) {
            perMsgBtn.disabled = !aiEnabled;
            perMsgBtn.innerHTML = '<i class="fas fa-lightbulb"></i>';
        }
    });
}

function toggleAI() {
    fetch(`/chatbot/api/conversations/${conversationId}/toggle-ai`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        aiEnabled = data.ai_enabled;
        autoRespond = data.auto_respond;
        const btn = document.getElementById('aiToggleBtn');
        btn.querySelector('.toggle-status').textContent = aiEnabled ? 'ON' : 'OFF';
        document.getElementById('generateAiBtn').disabled = !aiEnabled;
        document.getElementById('suggestAiBtn').disabled = !aiEnabled;

        const autoBtn = document.getElementById('autoRespondBtn');
        autoBtn.disabled = !aiEnabled;
        document.getElementById('autoRespondStatus').textContent = autoRespond ? 'ON' : 'OFF';
        autoBtn.classList.toggle('auto-respond-active', autoRespond);

        // Sync mobile overflow menu status
        const mobileAiStatus = document.getElementById('mobileAiStatus');
        if (mobileAiStatus) mobileAiStatus.textContent = aiEnabled ? 'ON' : 'OFF';
        const mobileAutoRespondBtn = document.getElementById('mobileAutoRespondBtn');
        if (mobileAutoRespondBtn) mobileAutoRespondBtn.disabled = !aiEnabled;
        const mobileAutoRespondStatus = document.getElementById('mobileAutoRespondStatus');
        if (mobileAutoRespondStatus) mobileAutoRespondStatus.textContent = autoRespond ? 'ON' : 'OFF';

        // Sync per-message suggest lightbulb buttons
        document.querySelectorAll('.btn-suggest-for-message').forEach(btn => {
            btn.disabled = !aiEnabled;
        });
    })
    .catch(err => console.error('Failed to toggle AI:', err));
}

function toggleAutoRespond() {
    if (!masterAiEnabled) {
        showNotification(i18n.t('conversation.ai.masterOff'), 'error');
        return;
    }
    fetch(`/chatbot/api/conversations/${conversationId}/toggle-auto-respond`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, 'error');
            return;
        }
        autoRespond = data.auto_respond;
        const btn = document.getElementById('autoRespondBtn');
        document.getElementById('autoRespondStatus').textContent = autoRespond ? 'ON' : 'OFF';
        btn.classList.toggle('auto-respond-active', autoRespond);

        // Sync mobile overflow menu status
        const mobileAutoRespondStatus = document.getElementById('mobileAutoRespondStatus');
        if (mobileAutoRespondStatus) mobileAutoRespondStatus.textContent = autoRespond ? 'ON' : 'OFF';

        showNotification(
            autoRespond
                ? (i18n.t('conversation.ai.autoRespond.on') || 'Auto-respond enabled')
                : (i18n.t('conversation.ai.autoRespond.off') || 'Auto-respond disabled'),
            'success'
        );
    })
    .catch(err => console.error('Failed to toggle auto-respond:', err));
}

function resolveEscalation() {
    fetch(`/chatbot/api/conversations/${conversationId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            // Remove escalation UI elements
            const banner = document.getElementById('escalationBanner');
            if (banner) banner.remove();

            const resolveBtn = document.getElementById('resolveEscalationBtn');
            if (resolveBtn) resolveBtn.remove();

            const mobileResolveBtn = document.getElementById('mobileResolveBtn');
            if (mobileResolveBtn) mobileResolveBtn.remove();

            showNotification(i18n.t('conversation.escalation.resolved') || 'Eskalation gelöst', 'success');
        }
    })
    .catch(err => console.error('Failed to resolve escalation:', err));
}

// =========================================================================
// Approval Queue Functions
// =========================================================================

async function approveMessage(messageId) {
    pendingCorrectionOriginal = null;
    try {
        const response = await fetch(`/chatbot/api/messages/${messageId}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        if (data.success) {
            const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
            if (msgEl) {
                msgEl.classList.remove('pending-approval');
                const label = msgEl.querySelector('.pending-approval-label');
                if (label) label.remove();
                const actions = msgEl.querySelector('.pending-approval-actions');
                if (actions) actions.remove();
            }
            showNotification(i18n.t('conversation.approval.sent'), 'success');

            if (!data.email_sent && !data.smoobu_sent) {
                showNotification(i18n.t('conversation.approval.sendWarning'), 'warning');
            }
        }
    } catch (error) {
        showNotification(i18n.t('conversation.approval.error'), 'error');
    }
}

async function editMessage(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    const content = msgEl?.querySelector('.message-text')?.textContent || '';

    // Save original AI text for correction tracking
    pendingCorrectionOriginal = content;

    const textarea = document.getElementById('messageInput');
    if (textarea) {
        textarea.value = content;
        textarea.focus();
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }

    try {
        await fetch(`/chatbot/api/messages/${messageId}/reject`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        if (msgEl) msgEl.remove();
    } catch (error) {
        console.error('Failed to remove pending draft:', error);
    }
}

async function rejectMessage(messageId) {
    try {
        const response = await fetch(`/chatbot/api/messages/${messageId}/reject`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        if (data.success) {
            const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
            if (msgEl) msgEl.remove();
            showNotification(i18n.t('conversation.approval.rejected'), 'info');
        }
    } catch (error) {
        showNotification(i18n.t('conversation.approval.error'), 'error');
    }
}

async function toggleAutoApprove() {
    try {
        const response = await fetch(`/chatbot/api/conversations/${conversationId}/toggle-auto-approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        autoApprove = data.auto_approve;
        updateAutoApproveButton(autoApprove);
    } catch (error) {
        showNotification(i18n.t('conversation.approval.toggleError'), 'error');
    }
}

function updateAutoApproveButton(isEnabled) {
    const btn = document.getElementById('autoApproveToggle');
    if (btn) {
        btn.classList.toggle('auto-approve-active', isEnabled);
        const status = document.getElementById('autoApproveStatus');
        if (status) status.textContent = isEnabled ? 'AN' : 'AUS';
        btn.title = isEnabled
            ? i18n.t('conversation.autoApprove.on')
            : i18n.t('conversation.autoApprove.off');
    }
}

/**
 * Add a message to the UI
 */
function addMessageToUI(message, senderType) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');

    const actualSenderType = message.sender_type || senderType;
    messageDiv.className = `message ${actualSenderType}`;

    if (message.id) {
        messageDiv.dataset.messageId = message.id;
    }

    const sentAt = message.sent_at || new Date().toISOString();
    messageDiv.dataset.sentAt = sentAt;

    const icon = actualSenderType === 'guest' ? 'fa-user' : (actualSenderType === 'owner' ? 'fa-home' : 'fa-robot');
    const name = actualSenderType === 'guest' ? cfg.guestName : (actualSenderType === 'owner' ? (message.sender_name || 'Team') : 'KI');

    let time;
    if (message.sent_at) {
        const date = new Date(message.sent_at);
        time = date.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } else {
        time = new Date().toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    const perMsgSuggestBtn = actualSenderType === 'guest' && message.id
        ? `<button class="btn-suggest-for-message" onclick="suggestForMessage(${message.id})"
            data-i18n-title="conversation.ai.suggestForMessage"
            title="${i18n.t('conversation.ai.suggestForMessage')}"
            ${!aiEnabled ? 'disabled' : ''}>
            <i class="fas fa-lightbulb"></i>
           </button>`
        : '';
    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas ${icon}"></i></div>
        <div class="message-content">
            <div class="message-header">
                <span class="sender-name">${name}</span>
                <span class="message-header-right">
                    ${perMsgSuggestBtn}
                    <span class="message-time">${time}</span>
                </span>
            </div>
            <div class="message-text">${escapeHtml(message.content || '')}</div>
        </div>
    `;

    // Pending approval styling
    if (message.approval_status === 'pending') {
        messageDiv.classList.add('pending-approval');
        const label = document.createElement('div');
        label.className = 'pending-approval-label';
        label.textContent = i18n.t('conversation.approval.waiting');
        messageDiv.querySelector('.message-content').prepend(label);

        const actions = document.createElement('div');
        actions.className = 'pending-approval-actions';
        actions.innerHTML = `
            <button class="btn btn-sm btn-success" onclick="approveMessage(${message.id})">
                <i class="fas fa-check"></i> ${i18n.t('conversation.approval.send')}
            </button>
            <button class="btn btn-sm btn-secondary" onclick="editMessage(${message.id})">
                <i class="fas fa-edit"></i> ${i18n.t('conversation.approval.edit')}
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="rejectMessage(${message.id})">
                <i class="fas fa-times"></i> ${i18n.t('conversation.approval.reject')}
            </button>
        `;
        messageDiv.querySelector('.message-content').appendChild(actions);
    }

    const dateKey = getDateKey(sentAt);
    if (dateKey && !knownDateDividers.has(dateKey)) {
        container.appendChild(createDateDivider(sentAt));
        knownDateDividers.add(dateKey);
    }

    messageDiv.classList.add('message-slide-in');
    container.appendChild(messageDiv);
}

/**
 * Update messages from poll response - append only new messages
 */
function updateMessages(messages) {
    const container = document.getElementById('messagesContainer');
    let hasNewMessages = false;

    messages.forEach(msg => {
        if (!knownMessageIds.has(msg.id)) {
            addMessageToUI(msg, msg.sender_type);
            knownMessageIds.add(msg.id);
            if (msg.id > maxKnownMessageId) maxKnownMessageId = msg.id;
            hasNewMessages = true;

            if (msg.sender_type === 'guest') {
                const preview = (msg.content || '').substring(0, 80);
                showBrowserNotification(
                    cfg.guestNotifyName,
                    preview,
                    window.location.href
                );
            }
        }
    });

    if (hasNewMessages) {
        scrollToBottom();
        // Advance read cursor to include newly arrived messages
        fetch(`/chatbot/api/conversations/${conversationId}/read`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ last_message_id: maxKnownMessageId })
        }).catch(err => console.error('Failed to advance read cursor:', err));
    }

    const emptyState = container.querySelector('.empty-messages');
    if (emptyState && messages.length > 0) {
        emptyState.remove();
    }
}

// Initialize message polling (only fetches NEW messages after last known ID)
const messagePoller = new PollingManager({
    fetchFn: async (signal) => {
        const afterParam = maxKnownMessageId ? `?after=${maxKnownMessageId}` : '';
        const response = await fetch(
            `/chatbot/api/conversations/${conversationId}/messages${afterParam}`,
            { signal }
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    },
    onUpdate: (data) => {
        updateMessages(data.messages);
    },
    interval: 10000
});

// Gmail auto-sync for email conversations
let gmailSyncPoller = null;

function initGmailSync() {
    if (conversationPlatform !== 'email' || !gmailConnected) return;

    gmailSyncPoller = new PollingManager({
        fetchFn: async (signal) => {
            const response = await fetch(
                '/chatbot/api/gmail/process?max_results=5&auto_respond=false',
                { method: 'POST', signal }
            );
            if (response.status === 401) {
                throw new Error('GMAIL_DISCONNECTED');
            }
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        },
        onUpdate: (data) => {
            if (data.processed > 0) {
                messagePoller.stop();
                messagePoller.start();
            }
        },
        interval: 15000,
        onError: (err) => {
            if (err.message === 'GMAIL_DISCONNECTED') {
                console.warn('Gmail disconnected, stopping sync');
                if (gmailSyncPoller) gmailSyncPoller.stop();
            } else {
                console.error('Gmail sync error:', err);
            }
        }
    });
    gmailSyncPoller.start();
}

// Smoobu auto-sync for Smoobu conversations
let smoobuSyncPoller = null;

function initSmoobuSync() {
    if (conversationPlatform !== 'smoobu' || !smoobuConnected) return;

    smoobuSyncPoller = new PollingManager({
        fetchFn: async (signal) => {
            const response = await fetch(
                `/chatbot/api/smoobu/sync/${conversationId}`,
                { method: 'POST', signal }
            );
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        },
        onUpdate: (data) => {
            if (data.imported > 0) {
                messagePoller.stop();
                messagePoller.start();
            }
        },
        interval: 30000,
        onError: (err) => {
            console.error('Smoobu sync error:', err);
        }
    });
    smoobuSyncPoller.start();
}

// Track master AI switch state globally
let masterAiEnabled = true;

function checkMasterAiSwitch() {
    fetch('/chatbot/api/settings')
        .then(r => r.json())
        .then(data => {
            masterAiEnabled = data.master_ai_enabled !== 'false';

            const autoBtn = document.getElementById('autoRespondBtn');
            const autoStatus = document.getElementById('autoRespondStatus');
            if (!masterAiEnabled) {
                autoBtn.classList.add('master-off');
                autoBtn.classList.remove('auto-respond-active');
                autoBtn.disabled = true;
                autoBtn.title = i18n.t('conversation.ai.masterOff');
                autoStatus.textContent = 'OFF';
            } else {
                autoBtn.classList.remove('master-off');
                autoBtn.disabled = !aiEnabled;
                autoBtn.title = i18n.t('conversation.ai.autoRespond');
                autoStatus.textContent = autoRespond ? 'ON' : 'OFF';
                autoBtn.classList.toggle('auto-respond-active', autoRespond);
            }
        })
        .catch(err => console.error('Failed to check master AI switch:', err));
}

// Start polling and scroll to bottom on page load
document.addEventListener('DOMContentLoaded', function() {
    // Mark read with the latest known message ID for precise cursor tracking
    fetch(`/chatbot/api/conversations/${conversationId}/read`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ last_message_id: maxKnownMessageId || null })
    }).catch(err => console.error('Failed to mark as read:', err));

    insertInitialDateDividers();

    // Restore draft from localStorage
    const savedDraft = localStorage.getItem(draftKey);
    if (savedDraft) {
        const input = document.getElementById('messageInput');
        input.value = savedDraft;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 200) + 'px';
    }

    scrollToBottom();
    messagePoller.start();

    initGmailSync();
    initSmoobuSync();
    checkMasterAiSwitch();

    // Show auto-approve toggle if approval queue is enabled
    if (approvalQueueEnabled) {
        document.getElementById('autoApproveToggle').style.display = '';
        updateAutoApproveButton(autoApprove);
    }
});

// --- Mobile overflow menu ---
document.addEventListener('DOMContentLoaded', function() {
    const overflowBtn = document.getElementById('mobileOverflowBtn');
    const overflowMenu = document.getElementById('mobileOverflowMenu');

    if (overflowBtn && overflowMenu) {
        overflowBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            overflowMenu.classList.toggle('open');
        });

        document.addEventListener('click', function(e) {
            if (overflowMenu.classList.contains('open') &&
                !overflowMenu.contains(e.target) &&
                !overflowBtn.contains(e.target)) {
                overflowMenu.classList.remove('open');
            }
        });
    }

    // Sync mobile property selector with desktop one after properties load.
    // loadPropertySelector() runs on DOMContentLoaded in conversation.js and populates
    // the desktop selector via fetch. We wait briefly then copy options to mobile.
    const mobilePropertySelector = document.getElementById('mobilePropertySelector');
    const desktopPropertySelector = document.getElementById('propertySelector');
    if (mobilePropertySelector && desktopPropertySelector) {
        function syncMobilePropertySelector() {
            if (desktopPropertySelector.options.length > 1) {
                mobilePropertySelector.innerHTML = desktopPropertySelector.innerHTML;
                mobilePropertySelector.value = desktopPropertySelector.value;
            }
        }
        // Also listen for changes on the desktop selector
        desktopPropertySelector.addEventListener('change', function() {
            mobilePropertySelector.value = desktopPropertySelector.value;
        });
        mobilePropertySelector.addEventListener('change', function() {
            desktopPropertySelector.value = mobilePropertySelector.value;
        });
        // Initial sync after properties have loaded (loadPropertySelector uses fetch)
        setTimeout(syncMobilePropertySelector, 500);
    }
});
