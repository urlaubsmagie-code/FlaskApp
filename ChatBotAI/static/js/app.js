/**
 * ChatBotAI - Main JavaScript
 */

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Make API requests with JSON
 */
async function apiRequest(url, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(url, options);
        const json = await response.json();

        if (!response.ok) {
            throw new Error(json.error || 'Request failed');
        }

        return json;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

/**
 * Format date/time
 */
function formatDateTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Format relative time
 */
function formatRelativeTime(dateString) {
    if (!dateString) return '';
    const ds = (!dateString.endsWith('Z') && !dateString.includes('+')) ? dateString + 'Z' : dateString;
    const date = new Date(ds);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    // Use calendar day boundaries (not raw hours) for "yesterday" etc.
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const msgDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((today - msgDay) / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffDays === 0) return `${diffHours}h ago`;
    if (diffDays === 1) return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('de-DE');
}

/**
 * Show notification toast
 */
function showNotification(message, type = 'info', duration = 3000) {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `notification-toast ${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
        <button class="toast-close" onclick="this.parentElement.classList.remove('show');setTimeout(()=>{this.parentElement.remove();_repositionToasts();},300);" aria-label="Close">&times;</button>
    `;

    // Add to page, then stack — _repositionToasts measures real heights.
    document.body.appendChild(toast);
    _repositionToasts();

    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after delay and reposition remaining toasts
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
            _repositionToasts();
        }, 300);
    }, duration);
}

function _repositionToasts() {
    const toasts = [...document.querySelectorAll('.notification-toast')];
    if (!toasts.length) return;

    const header = document.querySelector('.conversation-header-bar, .page-header');
    // Clamp floor: a .page-header scrolls away with the page, and an unclamped
    // negative offset would drag the toast off the top of the screen.
    const headerBottom = Math.max(12, header ? header.getBoundingClientRect().bottom + 8 : 12);
    const composer = document.querySelector('.message-input-container');

    // Heights are measured, never assumed: a message that wraps to two lines on
    // a narrow phone is taller than any fixed step and would overlap its neighbour.
    if (composer) {
        // In a chat, stack upward from just above the composer + UMI buttons.
        // Anchored to the composer's real top edge rather than the viewport, so
        // the phone keyboard pushes the toast up with it instead of hiding it —
        // and the buttons underneath stay visible and clickable.
        let anchor = composer.getBoundingClientRect().top - 8;
        for (let i = toasts.length - 1; i >= 0; i--) {
            const top = anchor - toasts[i].offsetHeight;
            toasts[i].style.top = `${Math.max(headerBottom, top)}px`;
            anchor = top - 8;
        }
        return;
    }

    // Pages without a composer (inbox, profile, …): hang under the header.
    let offset = 0;
    toasts.forEach(t => {
        t.style.top = `${headerBottom + offset}px`;
        offset += t.offsetHeight + 8;
    });
}

// The on-screen keyboard resizes the visual viewport and moves the composer;
// re-anchor so an open toast follows it instead of being left behind.
if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', _repositionToasts);
}

/**
 * Get a consistent avatar color index from a name string (0-7)
 */
function getAvatarColorIndex(name) {
    if (!name) return 0;
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = ((hash << 5) - hash) + name.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash) % 8;
}

/**
 * Get CSS variable name for avatar color
 */
function getAvatarColor(name) {
    return `var(--avatar-${getAvatarColorIndex(name)})`;
}

/**
 * Apply avatar colors to elements with data-guest-name attribute
 */
function applyAvatarColors() {
    document.querySelectorAll('[data-guest-name]').forEach(el => {
        el.style.background = getAvatarColor(el.dataset.guestName);
    });
}

/**
 * Request browser notification permission (called once on first visit)
 */
function initNotifications() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

/**
 * WebPush module — registers SW, subscribes/unsubscribes push.
 * Uses localStorage for UI state (like NotificationSound), browser
 * push subscription for actual delivery.
 */
const WebPush = {
    _registration: null,
    _vapidKey: null,
    _supported: false,

    isEnabled() {
        return localStorage.getItem('chatbot_push_enabled') === 'true';
    },

    _setEnabled(enabled) {
        localStorage.setItem('chatbot_push_enabled', String(enabled));
        updateBrowserNotifyToggleUI(enabled);
    },

    async init() {
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            this._supported = false;
            return;
        }

        try {
            await navigator.serviceWorker.register('/chatbot/sw.js', { scope: '/chatbot/' });
            this._registration = await navigator.serviceWorker.ready;
            this._supported = true;

            // Auto-heal: if push was enabled, verify subscription is valid
            if (this.isEnabled()) {
                await this._ensureSubscriptionFresh();
            }
        } catch (e) {
            this._supported = false;
        }
    },

    async _ensureSubscriptionFresh() {
        try {
            const existingSub = await this._registration.pushManager.getSubscription();
            const vapidKey = await this._fetchVapidKey();
            const expectedKey = this._urlBase64ToUint8Array(vapidKey);

            let needsResub = false;

            if (!existingSub) {
                // No subscription but push is "enabled" — re-subscribe
                needsResub = true;
            } else {
                // Compare applicationServerKey with current VAPID key
                const subKey = existingSub.options && existingSub.options.applicationServerKey
                    ? new Uint8Array(existingSub.options.applicationServerKey)
                    : null;

                if (!subKey || subKey.length !== expectedKey.length) {
                    needsResub = true;
                } else {
                    for (let i = 0; i < subKey.length; i++) {
                        if (subKey[i] !== expectedKey[i]) {
                            needsResub = true;
                            break;
                        }
                    }
                }
            }

            if (needsResub) {
                console.log('[WebPush] Subscription stale or missing, re-subscribing...');
                // Unsubscribe old if exists
                if (existingSub) {
                    await fetch('/chatbot/api/push/unsubscribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ endpoint: existingSub.endpoint })
                    });
                    await existingSub.unsubscribe();
                }
                // Create fresh subscription
                const newSub = await this._registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: expectedKey
                });
                const subJson = newSub.toJSON();
                await fetch('/chatbot/api/push/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        endpoint: subJson.endpoint,
                        keys: subJson.keys,
                        user_agent: navigator.userAgent
                    })
                });
                console.log('[WebPush] Re-subscribed successfully');
            }
        } catch (e) {
            console.warn('[WebPush] Auto-heal failed:', e);
        }
    },

    async _fetchVapidKey() {
        if (this._vapidKey) return this._vapidKey;
        const res = await fetch('/chatbot/api/push/vapid-key');
        const data = await res.json();
        this._vapidKey = data.publicKey;
        return this._vapidKey;
    },

    _urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; i++) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    },

    async subscribe() {
        if (!this._supported || !this._registration) return false;

        try {
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                showNotification(i18n.t('notify.push.denied'), 'error');
                return false;
            }

            const vapidKey = await this._fetchVapidKey();
            const sub = await this._registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this._urlBase64ToUint8Array(vapidKey)
            });

            const subJson = sub.toJSON();
            await fetch('/chatbot/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    endpoint: subJson.endpoint,
                    keys: subJson.keys,
                    user_agent: navigator.userAgent
                })
            });

            this._setEnabled(true);
            showNotification(i18n.t('notify.push.enabled'), 'success');
            return true;
        } catch (e) {
            console.error('[WebPush] subscribe failed:', e);
            showNotification(i18n.t('notify.push.unsupported'), 'error');
            return false;
        }
    },

    async unsubscribe() {
        if (!this._supported || !this._registration) return false;

        try {
            const sub = await this._registration.pushManager.getSubscription();
            if (sub) {
                const endpoint = sub.endpoint;
                await sub.unsubscribe();
                await fetch('/chatbot/api/push/unsubscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ endpoint: endpoint })
                });
            }
            this._setEnabled(false);
            showNotification(i18n.t('notify.push.disabled'), 'info');
            return true;
        } catch (e) {
            console.error('[WebPush] unsubscribe failed:', e);
            return false;
        }
    },

    async toggle() {
        if (!this._supported || !this._registration) {
            showNotification(i18n.t('notify.push.unsupported'), 'error');
            return;
        }
        if (this.isEnabled()) {
            await this.unsubscribe();
        } else {
            await this.subscribe();
        }
    },

    isSupported() {
        return this._supported;
    }
};

/**
 * Notification Sound module — plays audio ding for new messages
 */
const NotificationSound = {
    audio: null,

    init() {
        this.audio = new Audio('/chatbot/static/sounds/notification.wav');
        this.audio.volume = 0.5;
    },

    isEnabled() {
        const stored = localStorage.getItem('chatbot_sound_enabled');
        return stored === null ? true : stored === 'true';
    },

    setEnabled(enabled) {
        localStorage.setItem('chatbot_sound_enabled', String(enabled));
        updateSoundToggleUI(enabled);
    },

    toggle() {
        const next = !this.isEnabled();
        this.setEnabled(next);
        return next;
    },

    play() {
        if (!this.isEnabled()) return;
        if (document.visibilityState === 'visible') return;
        if (!this.audio) return;
        this.audio.currentTime = 0;
        this.audio.play().catch(() => { /* autoplay blocked */ });
    }
};

/**
 * Browser notification preference helpers
 */
function isBrowserNotificationEnabled() {
    const stored = localStorage.getItem('chatbot_browser_notification_enabled');
    return stored === null ? true : stored === 'true';
}

function setBrowserNotificationEnabled(enabled) {
    localStorage.setItem('chatbot_browser_notification_enabled', String(enabled));
    updateBrowserNotifyToggleUI(enabled);
}

/**
 * Show a browser notification (only when tab is hidden)
 */
function showBrowserNotification(title, body, url) {
    if (!isBrowserNotificationEnabled()) return;
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    if (document.visibilityState === 'visible') return;

    NotificationSound.play();

    const notification = new Notification(title, {
        body: body,
        icon: '/chatbot/chatbot/static/img/pwa/icon-192.png'
    });

    if (url) {
        notification.onclick = function() {
            window.focus();
            window.location.href = url;
            notification.close();
        };
    }

    setTimeout(() => notification.close(), 8000);
}

/**
 * Check if a conversation is relevant to the current user
 * (unassigned or assigned to me)
 */
function isConversationRelevantToMe(conv) {
    if (!window.CHATBOT_USER || !window.CHATBOT_USER.id) return true;
    return !conv.user_id || conv.user_id === window.CHATBOT_USER.id;
}

/**
 * Set the sidebar inbox badge + tab title. The count is the server's total of
 * unread chats — the same number as the inbox "Ungelesen" tile. It used to be
 * counted from page 1 of the list (50 chats) minus chats assigned to others,
 * so it showed 11 next to a tile reading 33.
 */
function setInboxBadge(count) {
    const badge = document.getElementById('inboxBadge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? '' : 'none';
    }
    // Update document title
    const baseTitle = document.title.replace(/^\(\d+\)\s*/, '');
    document.title = count > 0 ? `(${count}) ${baseTitle}` : baseTitle;
}

/**
 * Fetch online users and update sidebar + mobile panel
 */
function updateOnlineUsers() {
    fetch('/chatbot/api/users/online')
        .then(r => r.json())
        .then(data => {
            const users = data.users || [];
            const html = users.map(u =>
                `<div class="online-user"><span class="online-avatar">${u.display_name[0].toUpperCase()}</span><span class="online-name">${u.display_name}</span></div>`
            ).join('');

            // Update sidebar
            const sidebarList = document.getElementById('sidebarOnlineList');
            const sidebarCount = document.getElementById('sidebarOnlineCount');
            const sidebarWrap = document.getElementById('sidebarOnlineUsers');
            if (sidebarList) sidebarList.innerHTML = html;
            if (sidebarCount) sidebarCount.textContent = users.length;
            if (sidebarWrap) sidebarWrap.style.display = users.length ? '' : 'none';

            // Update mobile panel
            const mobileList = document.getElementById('mobileOnlineList');
            const mobileCount = document.getElementById('mobileOnlineCount');
            const mobileWrap = document.getElementById('mobileOnlineUsers');
            if (mobileList) mobileList.innerHTML = html;
            if (mobileCount) mobileCount.textContent = users.length;
            if (mobileWrap) mobileWrap.style.display = users.length ? '' : 'none';
        })
        .catch(() => { /* silent */ });
}

/**
 * Fetch conversations and update badge (for non-inbox pages)
 */
function updateInboxBadge() {
    fetch('/chatbot/api/conversations/last-updated')
        .then(r => r.json())
        .then(data => setInboxBadge(data.unread || 0))
        .catch(() => { /* silent */ });
}

/**
 * Toggle notification sound on/off
 */
function toggleNotificationSound() {
    NotificationSound.toggle();
}

/**
 * Update sound toggle button UI
 */
function updateSoundToggleUI(enabled) {
    const icons = [document.getElementById('soundToggleIcon'), document.getElementById('mobileSoundToggleIcon')];
    const btns = [document.getElementById('soundToggleBtn'), document.getElementById('mobileSoundToggleBtn')];
    icons.forEach(icon => {
        if (!icon) return;
        icon.className = enabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
    });
    btns.forEach(btn => {
        if (!btn) return;
        enabled ? btn.classList.remove('disabled') : btn.classList.add('disabled');
    });
}

/**
 * Toggle browser/push notifications on/off
 */
function toggleBrowserNotifications() {
    if (WebPush.isSupported()) {
        WebPush.toggle();
    } else {
        const next = !isBrowserNotificationEnabled();
        setBrowserNotificationEnabled(next);
        if (next && 'Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }
}

/**
 * Update browser notification toggle button UI
 */
function updateBrowserNotifyToggleUI(enabled) {
    const icons = [document.getElementById('browserNotifyToggleIcon'), document.getElementById('mobilePushToggleIcon')];
    const btns = [document.getElementById('browserNotifyToggleBtn'), document.getElementById('mobilePushToggleBtn')];
    icons.forEach(icon => {
        if (!icon) return;
        icon.className = enabled ? 'fas fa-bell' : 'fas fa-bell-slash';
    });
    btns.forEach(btn => {
        if (!btn) return;
        enabled ? btn.classList.remove('disabled') : btn.classList.add('disabled');
    });
}

/**
 * Initialize dark mode from localStorage
 */
function initTheme() {
    const theme = localStorage.getItem('chatbot_theme') || 'light';
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);
}

/**
 * Toggle dark mode
 */
function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('chatbot_theme', next);
    updateThemeIcon(next);
}

/**
 * Update theme toggle button icon
 */
function updateThemeIcon(theme) {
    const btn = document.getElementById('themeToggleBtn');
    if (!btn) return;
    const icon = btn.querySelector('i');
    const label = btn.querySelector('span');
    if (theme === 'dark') {
        icon.className = 'fas fa-sun';
        if (label) label.textContent = 'Light Mode';
    } else {
        icon.className = 'fas fa-moon';
        if (label) label.textContent = 'Dark Mode';
    }

    const mobileBtn = document.getElementById('mobileThemeToggleBtn');
    if (mobileBtn) {
        const mobileIcon = mobileBtn.querySelector('i');
        mobileIcon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

/**
 * Debounce function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Escape HTML but preserve <mark>...</mark> tags used by server-side
 * search to highlight matches. Defense-in-depth so a regression in the
 * backend sanitizer cannot inject script tags via search snippets.
 */
function escapeHtmlAllowMark(text) {
    if (text == null) return '';
    const escaped = escapeHtml(String(text));
    return escaped
        .replace(/&lt;mark&gt;/g, '<mark>')
        .replace(/&lt;\/mark&gt;/g, '</mark>');
}

// ============================================================================
// Conversation Functions
// ============================================================================

/**
 * Load conversations via API
 */
async function loadConversations(page = 1, status = null) {
    try {
        let url = `/chatbot/api/conversations?page=${page}`;
        if (status && status !== 'all') {
            url += `&status=${status}`;
        }

        const data = await apiRequest(url);
        return data;
    } catch (error) {
        showNotification('Failed to load conversations', 'error');
        return null;
    }
}

/**
 * Load messages for a conversation
 */
async function loadMessages(conversationId) {
    try {
        const data = await apiRequest(`/chatbot/api/conversations/${conversationId}/messages`);
        return data.messages;
    } catch (error) {
        showNotification('Failed to load messages', 'error');
        return [];
    }
}

/**
 * Send a message
 */
async function sendMessageAPI(conversationId, content) {
    try {
        const data = await apiRequest(
            `/chatbot/api/conversations/${conversationId}/messages`,
            'POST',
            { content }
        );
        return data;
    } catch (error) {
        showNotification('Failed to send message', 'error');
        return null;
    }
}

/**
 * Generate AI response
 */
async function generateAIResponseAPI(conversationId) {
    try {
        const data = await apiRequest(
            `/chatbot/api/conversations/${conversationId}/ai-response`,
            'POST'
        );
        return data;
    } catch (error) {
        showNotification(error.message || 'Failed to generate AI response', 'error');
        return null;
    }
}

/**
 * Toggle AI for conversation
 */
async function toggleAIAPI(conversationId) {
    try {
        const data = await apiRequest(
            `/chatbot/api/conversations/${conversationId}/toggle-ai`,
            'POST'
        );
        return data;
    } catch (error) {
        showNotification('Failed to toggle AI', 'error');
        return null;
    }
}

// ============================================================================
// Guest Functions
// ============================================================================

/**
 * Load guest profile
 */
async function loadGuestProfile(guestId) {
    try {
        const data = await apiRequest(`/chatbot/api/guests/${guestId}`);
        return data;
    } catch (error) {
        showNotification('Failed to load guest profile', 'error');
        return null;
    }
}

/**
 * Add guest detail
 */
async function addGuestDetail(guestId, detailType, detailKey, detailValue) {
    try {
        const data = await apiRequest(
            `/chatbot/api/guests/${guestId}/details`,
            'POST',
            { detail_type: detailType, detail_key: detailKey, detail_value: detailValue }
        );
        showNotification('Detail added successfully', 'success');
        return data;
    } catch (error) {
        showNotification('Failed to add detail', 'error');
        return null;
    }
}

/**
 * Delete guest detail
 */
async function deleteGuestDetail(guestId, detailId) {
    try {
        await apiRequest(
            `/chatbot/api/guests/${guestId}/details/${detailId}`,
            'DELETE'
        );
        showNotification('Detail deleted', 'success');
        return true;
    } catch (error) {
        showNotification('Failed to delete detail', 'error');
        return false;
    }
}

// ============================================================================
// Settings Functions
// ============================================================================

/**
 * Load settings
 */
async function loadSettings() {
    try {
        const data = await apiRequest('/chatbot/api/settings');
        return data;
    } catch (error) {
        showNotification('Failed to load settings', 'error');
        return null;
    }
}

/**
 * Update settings
 */
async function updateSettings(settings) {
    try {
        await apiRequest('/chatbot/api/settings', 'PUT', settings);
        showNotification('Settings saved', 'success');
        return true;
    } catch (error) {
        showNotification('Failed to save settings', 'error');
        return false;
    }
}

/**
 * Test AI connection
 */
async function testAIConnection(message) {
    try {
        const data = await apiRequest('/chatbot/api/test-ai', 'POST', { message });
        return data;
    } catch (error) {
        showNotification('AI test failed', 'error');
        return null;
    }
}

// ============================================================================
// Initialization
// ============================================================================

// Apply theme immediately (before DOMContentLoaded to prevent flash)
initTheme();

document.addEventListener('DOMContentLoaded', function() {
    // Initialize notification sound
    NotificationSound.init();

    // Initialize Web Push (registers SW, checks subscription state)
    WebPush.init();

    // Initialize toggle button UI states (synchronous, from localStorage)
    updateSoundToggleUI(NotificationSound.isEnabled());
    updateBrowserNotifyToggleUI(WebPush.isEnabled());

    // Badge polling on non-inbox pages (inbox updates badge via its own poller)
    if (!document.getElementById('conversationList')) {
        updateInboxBadge();
        window._badgeInterval = setInterval(updateInboxBadge, 30000);
    }

    // Online users polling (every 30s on all pages)
    updateOnlineUsers();
    window._onlineInterval = setInterval(updateOnlineUsers, 30000);

    // Pause all polling when tab is hidden (saves CPU, network, and battery)
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            // Pause badge polling
            if (window._badgeInterval) {
                clearInterval(window._badgeInterval);
                window._badgeInterval = null;
            }
            // Pause online users polling
            if (window._onlineInterval) {
                clearInterval(window._onlineInterval);
                window._onlineInterval = null;
            }
        } else {
            // Resume badge polling (non-inbox pages only)
            if (!document.getElementById('conversationList') && !window._badgeInterval) {
                updateInboxBadge();
                window._badgeInterval = setInterval(updateInboxBadge, 30000);
            }
            // Resume online users polling
            if (!window._onlineInterval) {
                updateOnlineUsers();
                window._onlineInterval = setInterval(updateOnlineUsers, 30000);
            }
        }
    });

    // Apply avatar colors
    applyAvatarColors();

    // Toast styles live in style.css. They used to be injected here as a <style>
    // block appended to <head>, which silently outranked the stylesheet and kept
    // the toast bottom-anchored over the composer no matter what style.css said.

    // --- Mobile: sync language selector with sidebar ---
    const mobileLangSelector = document.getElementById('mobileLanguageSelector');
    const desktopLangSelector = document.getElementById('languageSelector');
    if (mobileLangSelector && desktopLangSelector) {
        mobileLangSelector.value = desktopLangSelector.value;
    }

    console.log('ChatBotAI initialized');
});
