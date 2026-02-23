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
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('de-DE');
}

/**
 * Show notification toast
 */
function showNotification(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `notification-toast ${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;

    // Stack above existing toasts
    const existingToasts = document.querySelectorAll('.notification-toast');
    const offset = existingToasts.length * 56;
    toast.style.bottom = `${20 + offset}px`;

    // Add to page
    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after delay and reposition remaining toasts
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
            // Reposition remaining toasts
            document.querySelectorAll('.notification-toast').forEach((t, i) => {
                t.style.bottom = `${20 + i * 56}px`;
            });
        }, 300);
    }, 3000);
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
 * Show a browser notification (only when tab is hidden)
 */
function showBrowserNotification(title, body, url) {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    if (document.visibilityState === 'visible') return;

    const notification = new Notification(title, {
        body: body,
        icon: '/chatbot/static/favicon.ico'
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
    // Request notification permission
    initNotifications();

    // Apply avatar colors
    applyAvatarColors();

    // Add notification toast styles if not present
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            .notification-toast {
                position: fixed;
                bottom: 20px;
                right: 20px;
                padding: 12px 20px;
                background: #1e293b;
                color: white;
                border-radius: 8px;
                display: flex;
                align-items: center;
                gap: 10px;
                transform: translateX(120%);
                transition: transform 0.3s ease;
                z-index: 9999;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }
            .notification-toast.show {
                transform: translateX(0);
            }
            .notification-toast.success {
                background: #166534;
            }
            .notification-toast.error {
                background: #991b1b;
            }
            .notification-toast.info {
                background: #1e40af;
            }
        `;
        document.head.appendChild(style);
    }

    console.log('ChatBotAI initialized');
});
