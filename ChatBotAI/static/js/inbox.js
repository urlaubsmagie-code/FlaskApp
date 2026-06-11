/**
 * ChatBotAI - Inbox Page JavaScript
 * Extracted from inline <script> in inbox.html for browser caching.
 */

// =========================================================================
// Conversation Card DOM Helpers
// =========================================================================

function getPlatformIcon(platform) {
    switch (platform) {
        case 'email': return 'fas fa-envelope';
        case 'whatsapp': return 'fab fa-whatsapp';
        case 'airbnb': return 'fab fa-airbnb';
        case 'smoobu': return 'fas fa-building';
        default: return 'fas fa-comment';
    }
}

function ensureUTC(dateString) {
    if (!dateString) return dateString;
    return dateString.endsWith('Z') || dateString.includes('+') ? dateString : dateString + 'Z';
}

function formatAbsoluteTime(dateString) {
    if (!dateString) return '';
    const date = new Date(ensureUTC(dateString));
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${day}.${month} ${hours}:${minutes}`;
}

function refreshRelativeTimestamps() {
    document.querySelectorAll('.conversation-time[data-timestamp]').forEach(el => {
        const ts = el.dataset.timestamp;
        if (ts) {
            el.textContent = formatRelativeTime(ts);
        }
    });
}

function formatStatus(status) {
    return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatStayDates(checkIn, checkOut) {
    if (!checkIn || !checkOut) return '';
    const ci = new Date(checkIn + 'T00:00:00');
    const co = new Date(checkOut + 'T00:00:00');
    const nights = Math.round((co - ci) / 86400000);
    const fmt = d => `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
    return `${fmt(ci)} \u2013 ${fmt(co)} (${nights}n)`;
}

function createConversationCard(conv) {
    const card = document.createElement('a');
    card.href = `/chatbot/conversation/${conv.id}`;
    card.className = 'conversation-card' + (!conv.is_read ? ' unread' : '');
    card.dataset.conversationId = conv.id;
    card.dataset.updatedAt = conv.updated_at || '';
    card.dataset.platform = conv.platform;
    card.dataset.status = conv.status;
    card.dataset.guestId = conv.guest_id || '';
    card.dataset.isRead = conv.is_read ? 'true' : 'false';
    card.dataset.escalated = conv.escalated ? 'true' : 'false';
    card.dataset.autoRespond = conv.auto_respond ? 'true' : 'false';
    card.dataset.hasPendingApproval = conv.has_pending_approval ? 'true' : 'false';
    if (conv.escalated) card.classList.add('escalated');

    const guestName = (conv.guest && (conv.guest.name || conv.guest.email)) || 'Unknown Guest';

    let preview = 'No messages yet';
    if (conv.last_message && conv.last_message.content) {
        let prefix = '';
        if (conv.last_message.sender_type === 'owner') prefix = (conv.last_message.sender_name || i18n.t('inbox.senderMe') || 'Ich') + ': ';
        else if (conv.last_message.sender_type === 'ai') prefix = (i18n.t('inbox.senderAI') || 'UMI') + ': ';
        const content = conv.last_message.content;
        const maxLen = 80 - prefix.length;
        preview = prefix + (content.length > maxLen ? content.substring(0, maxLen) + '...' : content);
    }

    const aiBadge = conv.ai_enabled
        ? `<span class="ai-badge ${conv.auto_respond ? 'auto-respond-on' : 'auto-respond-off'}" title="${conv.auto_respond ? (i18n.t('inbox.aiActive') || 'UMI aktiv') : (i18n.t('inbox.aiPaused') || 'UMI pausiert')}"><i class="fas fa-robot"></i></span>`
        : '';
    const escalationLabel = conv.escalated
        ? `<span class="escalation-badge"><i class="fas fa-exclamation-triangle"></i> ${i18n.t('inbox.needsAttention') || 'Braucht Aufmerksamkeit'}</span>`
        : '';
    const approvalLabel = conv.has_pending_approval
        ? `<span class="badge badge-approval"><i class="fas fa-clock"></i> ${i18n.t('inbox.badge.pendingApproval') || 'UMI-Freigabe'}</span>`
        : '';
    const cancellationLabel = conv.cancelled_at
        ? `<span class="cancellation-badge" title="${escapeHtml(conv.cancelled_at)}"><i class="fas fa-ban"></i> ${i18n.t('inbox.badge.cancelled') || 'Storniert'}</span>`
        : '';
    const srText = !conv.is_read ? '<span class="sr-only">Unread</span>' : '';

    card.innerHTML = `
        ${srText}
        <div class="conversation-avatar" data-guest-name="${escapeHtml(guestName)}" style="background: ${getAvatarColor(guestName)}">
            <i class="${getPlatformIcon(conv.platform)}"></i>
        </div>
        <div class="conversation-info">
            <div class="conversation-header">
                <span class="guest-name">${escapeHtml(guestName)}</span>
                <span class="conversation-time" data-timestamp="${conv.updated_at || ''}" title="${formatAbsoluteTime(conv.updated_at)}">${formatRelativeTime(conv.updated_at)}</span>
            </div>
            <div class="conversation-subject">${escapeHtml(conv.property_name || conv.subject || 'No subject')}${conv.check_in && conv.check_out ? ` <span class="stay-dates">${formatStayDates(conv.check_in, conv.check_out)}</span>` : ''}</div>
            <div class="conversation-preview">${escapeHtml(preview)}</div>
        </div>
        <div class="conversation-meta">
            <span class="platform-badge ${(conv.display_platform || conv.platform).toLowerCase().replace('booking.com', 'booking').replace(/\s/g, '')}">${escapeHtml(conv.display_platform || conv.platform)}</span>
            ${aiBadge}
            ${escalationLabel}
            ${approvalLabel}
            ${cancellationLabel}
            <span class="status-badge ${conv.status}">${formatStatus(conv.status)}</span>
            ${conv.status !== 'closed' ? `<button class="btn-close-conv" onclick="closeConversation(event, ${conv.id})" title="${i18n.t('inbox.closeChat') || 'Gespräch beenden'}"><i class="fas fa-times"></i></button>` : ''}
        </div>
    `;

    return card;
}

function updateConversationCard(card, conv) {
    card.dataset.updatedAt = conv.updated_at || '';
    card.dataset.status = conv.status;
    card.dataset.isRead = conv.is_read ? 'true' : 'false';
    card.dataset.escalated = conv.escalated ? 'true' : 'false';
    card.dataset.autoRespond = conv.auto_respond ? 'true' : 'false';
    card.dataset.hasPendingApproval = conv.has_pending_approval ? 'true' : 'false';
    card.classList.toggle('escalated', !!conv.escalated);

    if (conv.is_read) {
        card.classList.remove('unread');
        const srOnly = card.querySelector('.sr-only');
        if (srOnly) srOnly.remove();
    } else {
        card.classList.add('unread');
        if (!card.querySelector('.sr-only')) {
            const srSpan = document.createElement('span');
            srSpan.className = 'sr-only';
            srSpan.textContent = 'Unread';
            card.insertBefore(srSpan, card.firstChild);
        }
    }

    const timeEl = card.querySelector('.conversation-time');
    if (timeEl) {
        timeEl.dataset.timestamp = conv.updated_at || '';
        timeEl.title = formatAbsoluteTime(conv.updated_at);
        timeEl.textContent = formatRelativeTime(conv.updated_at);
    }

    const previewEl = card.querySelector('.conversation-preview');
    if (previewEl) {
        let preview = 'No messages yet';
        if (conv.last_message && conv.last_message.content) {
            let prefix = '';
            if (conv.last_message.sender_type === 'owner') prefix = (conv.last_message.sender_name || i18n.t('inbox.senderMe') || 'Ich') + ': ';
            else if (conv.last_message.sender_type === 'ai') prefix = (i18n.t('inbox.senderAI') || 'UMI') + ': ';
            const content = conv.last_message.content;
            const maxLen = 80 - prefix.length;
            preview = prefix + (content.length > maxLen ? content.substring(0, maxLen) + '...' : content);
        }
        previewEl.textContent = preview;
    }

    const statusEl = card.querySelector('.status-badge');
    if (statusEl) {
        statusEl.className = `status-badge ${conv.status}`;
        statusEl.textContent = formatStatus(conv.status);
    }

    const metaEl = card.querySelector('.conversation-meta');
    const existingAiBadge = card.querySelector('.ai-badge');
    if (conv.ai_enabled && !existingAiBadge) {
        const aiBadge = document.createElement('span');
        aiBadge.className = 'ai-badge';
        aiBadge.innerHTML = '<i class="fas fa-robot"></i>';
        metaEl.insertBefore(aiBadge, statusEl);
    } else if (!conv.ai_enabled && existingAiBadge) {
        existingAiBadge.remove();
    }

    // Update escalation badge
    const existingEscalation = card.querySelector('.escalation-badge');
    if (conv.escalated && !existingEscalation) {
        const badge = document.createElement('span');
        badge.className = 'escalation-badge';
        badge.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${i18n.t('inbox.needsAttention') || 'Braucht Aufmerksamkeit'}`;
        metaEl.insertBefore(badge, statusEl);
    } else if (!conv.escalated && existingEscalation) {
        existingEscalation.remove();
    }

    // Update pending approval badge
    const existingApprovalBadge = card.querySelector('.badge-approval');
    if (conv.has_pending_approval && !existingApprovalBadge) {
        const approvalBadge = document.createElement('span');
        approvalBadge.className = 'badge badge-approval';
        approvalBadge.innerHTML = `<i class="fas fa-clock"></i> ${i18n.t('inbox.badge.pendingApproval') || 'UMI-Freigabe'}`;
        metaEl.insertBefore(approvalBadge, statusEl);
    } else if (!conv.has_pending_approval && existingApprovalBadge) {
        existingApprovalBadge.remove();
    }

    // Update cancellation badge (set by cancelReservation webhook).
    // Once cancelled, the field stays set — we only need to ADD when it
    // appears. (Un-cancellation is unusual but we still handle removal
    // symmetrically for cleanliness.)
    const existingCancelBadge = card.querySelector('.cancellation-badge');
    if (conv.cancelled_at && !existingCancelBadge) {
        const cancelBadge = document.createElement('span');
        cancelBadge.className = 'cancellation-badge';
        cancelBadge.title = conv.cancelled_at;
        cancelBadge.innerHTML = `<i class="fas fa-ban"></i> ${i18n.t('inbox.badge.cancelled') || 'Storniert'}`;
        metaEl.insertBefore(cancelBadge, statusEl);
    } else if (!conv.cancelled_at && existingCancelBadge) {
        existingCancelBadge.remove();
    }

    // Update AI badge auto-respond state
    if (existingAiBadge) {
        existingAiBadge.classList.toggle('auto-respond-on', !!conv.auto_respond);
        existingAiBadge.classList.toggle('auto-respond-off', !conv.auto_respond);
        existingAiBadge.title = conv.auto_respond
            ? (i18n.t('inbox.aiActive') || 'UMI aktiv')
            : (i18n.t('inbox.aiPaused') || 'UMI pausiert');
    }
}

function updateInboxList(conversations) {
    if (typeof isSearchMode !== 'undefined' && isSearchMode) return;

    const container = document.getElementById('conversationList');
    if (!container) return;

    if (!conversations || conversations.length === 0) {
        const existingEmpty = container.querySelector('.empty-state');
        if (!existingEmpty) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-inbox"></i>
                    <h3>No conversations yet</h3>
                    <p>When guests message you, their conversations will appear here.</p>
                </div>
            `;
        }
        return;
    }

    // Cache data in sessionStorage for instant rendering on next visit
    cacheInboxData(conversations);

    const emptyState = container.querySelector('.empty-state:not(.search-empty)');
    if (emptyState) emptyState.remove();
    container.querySelectorAll('.date-group-header').forEach(h => h.remove());

    // Build lookup of existing cards
    const existingCards = new Map();
    container.querySelectorAll('.conversation-card').forEach(card => {
        existingCards.set(card.dataset.conversationId, card);
    });

    // Build new list in a DocumentFragment (single DOM reflow instead of N)
    const fragment = document.createDocumentFragment();
    const newIds = new Set();

    conversations.forEach(conv => {
        const convId = String(conv.id);
        newIds.add(convId);

        const existingCard = existingCards.get(convId);

        if (existingCard) {
            const isReadChanged = existingCard.dataset.isRead !== (conv.is_read ? 'true' : 'false');
            if (existingCard.dataset.updatedAt !== conv.updated_at || isReadChanged) {
                updateConversationCard(existingCard, conv);
            }
            // appendChild moves node from container to fragment (no clone needed)
            fragment.appendChild(existingCard);
        } else {
            const newCard = createConversationCard(conv);
            fragment.appendChild(newCard);

            if (!conv.is_read && isConversationRelevantToMe(conv)) {
                const gName = (conv.guest && (conv.guest.name || conv.guest.email)) || 'Guest';
                const preview = (conv.last_message && conv.last_message.content) || '';
                showBrowserNotification(
                    gName,
                    preview.substring(0, 80),
                    `/chatbot/conversation/${conv.id}`
                );
            }
        }
    });

    // Remove cards no longer in the conversation list (but keep "load more" cards)
    existingCards.forEach((card, id) => {
        if (!newIds.has(id) && card.parentNode && !card.dataset.loadedMore) card.remove();
    });

    // Single DOM update — insert cards before the load-more button (keep it at bottom)
    const loadMoreEl = document.getElementById('loadMoreContainer');
    if (loadMoreEl) {
        container.insertBefore(fragment, loadMoreEl);
    } else {
        container.appendChild(fragment);
    }

    filterState.applyFilters();
    insertDateGroupHeaders();
    applyAvatarColors();
}

// =========================================================================
// SessionStorage Cache — instant rendering on revisit
// =========================================================================

const INBOX_CACHE_KEY = 'chatbot_inbox_cache';

function cacheInboxData(conversations) {
    try {
        sessionStorage.setItem(INBOX_CACHE_KEY, JSON.stringify({
            conversations: conversations,
            ts: Date.now()
        }));
    } catch (e) {
        // sessionStorage may be full or unavailable — ignore
    }
}

function loadCachedInbox() {
    try {
        const raw = sessionStorage.getItem(INBOX_CACHE_KEY);
        if (!raw) return null;
        const data = JSON.parse(raw);
        // Only use if less than 5 minutes old
        if (Date.now() - data.ts < 300000 && data.conversations) {
            return data.conversations;
        }
    } catch (e) {}
    return null;
}

// =========================================================================
// Date Group Headers
// =========================================================================

function getDateGroup(dateString) {
    if (!dateString) return 'older';
    const d = new Date(ensureUTC(dateString));
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const cardDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((today - cardDay) / 86400000);

    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 7) return 'thisWeek';
    if (diffDays < 30) return 'thisMonth';
    return 'older';
}

function createDateGroupHeader(groupKey) {
    const div = document.createElement('div');
    div.className = 'date-group-header';
    div.dataset.dateGroup = groupKey;
    const label = i18n.t('inbox.group.' + groupKey);
    div.innerHTML = `<span>${label}</span>`;
    return div;
}

function insertDateGroupHeaders() {
    const container = document.getElementById('conversationList');
    if (!container) return;

    container.querySelectorAll('.date-group-header').forEach(h => h.remove());

    const cards = container.querySelectorAll('.conversation-card');
    let lastGroup = null;

    cards.forEach(card => {
        const updatedAt = card.dataset.updatedAt;
        const group = getDateGroup(updatedAt);
        if (group !== lastGroup) {
            container.insertBefore(createDateGroupHeader(group), card);
            lastGroup = group;
        }
    });
}

// =========================================================================
// Filter and Search (using FilterState module)
// =========================================================================

document.querySelectorAll('[data-filter-platform]').forEach(btn => {
    btn.addEventListener('click', function() {
        filterState.setPlatform(this.dataset.filterPlatform || null);
    });
});

document.querySelectorAll('[data-filter-status]').forEach(btn => {
    btn.addEventListener('click', function() {
        filterState.setStatus(this.dataset.filterStatus || null);
    });
});

const guestFilterEl = document.getElementById('guestFilter');
if (guestFilterEl) {
    guestFilterEl.addEventListener('change', function() {
        filterState.setGuest(this.value || null);
    });
}

document.getElementById('clearFiltersBtn').addEventListener('click', function() {
    filterState.reset();
});

let searchTimeout = null;
let isSearchMode = false;

document.getElementById('searchInput').addEventListener('input', function() {
    const query = this.value.trim();
    const clearBtn = document.getElementById('searchClearBtn');
    if (clearBtn) clearBtn.classList.toggle('visible', query.length > 0);

    if (searchTimeout) clearTimeout(searchTimeout);

    filterState.applyFilters();

    searchTimeout = setTimeout(async () => {
        if (query.length >= 2) {
            filterState.setSearch(query);
            const results = await fetchSearchResults(query);
            renderSearchResults(results);
        } else if (query.length === 0) {
            clearSearchMode();
        }
    }, 500);
});

document.getElementById('searchClearBtn').addEventListener('click', function() {
    clearSearch();
    this.classList.remove('visible');
    document.getElementById('searchInput').focus();
});

// =========================================================================
// Search Functions
// =========================================================================

async function fetchSearchResults(query) {
    const params = new URLSearchParams({ q: query });

    if (filterState.state.platform) {
        params.set('platform', filterState.state.platform);
    }
    if (filterState.state.status) {
        params.set('status', filterState.state.status);
    }

    try {
        const response = await fetch(`/chatbot/api/search?${params}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('Search error:', error);
        return { results: [], query: query, total: 0 };
    }
}

function renderSearchResults(data) {
    const container = document.getElementById('conversationList');
    const emptyState = document.getElementById('searchEmptyState');
    const normalEmpty = container.querySelector('.empty-state:not(.search-empty)');

    isSearchMode = true;

    // Remove any previously injected search-only cards
    container.querySelectorAll('.conversation-card.search-injected').forEach(c => c.remove());

    if (normalEmpty) normalEmpty.style.display = 'none';

    if (data.results.length === 0) {
        const queryTextEl = document.getElementById('searchQueryText');
        if (queryTextEl) queryTextEl.textContent = data.query;
        if (emptyState) emptyState.style.display = 'block';

        container.querySelectorAll('.conversation-card').forEach(card => {
            card.style.display = 'none';
        });
        return;
    }

    if (emptyState) emptyState.style.display = 'none';

    const matchingIds = new Set(data.results.map(r => String(r.conversation_id)));

    // Hide non-matching existing cards, annotate matching ones
    container.querySelectorAll('.conversation-card').forEach(card => {
        const convId = card.dataset.conversationId;

        if (matchingIds.has(convId)) {
            card.style.display = 'flex';
            card.classList.add('search-result');

            const result = data.results.find(r => String(r.conversation_id) === convId);

            let snippetEl = card.querySelector('.search-snippet');
            if (!snippetEl) {
                snippetEl = document.createElement('div');
                snippetEl.className = 'search-snippet';
                const previewEl = card.querySelector('.conversation-preview');
                if (previewEl) {
                    previewEl.insertAdjacentElement('afterend', snippetEl);
                }
            }

            if (result.first_snippet) {
                // Defense-in-depth: escape everything, re-allow <mark> only.
                snippetEl.innerHTML = (typeof escapeHtmlAllowMark === 'function')
                    ? escapeHtmlAllowMark(result.first_snippet)
                    : escapeHtml(result.first_snippet);
            }

            let countEl = card.querySelector('.match-count');
            if (!countEl && result.match_count > 1) {
                countEl = document.createElement('span');
                countEl.className = 'match-count';
                const headerEl = card.querySelector('.conversation-header');
                if (headerEl) headerEl.appendChild(countEl);
            }
            if (countEl) {
                countEl.textContent = result.match_count > 1 ? `(${result.match_count} matches)` : '';
            }
        } else {
            card.style.display = 'none';
        }
    });

    // Create cards for search results not already in the DOM (older conversations)
    const existingIds = new Set(
        Array.from(container.querySelectorAll('.conversation-card'))
            .map(c => c.dataset.conversationId)
    );

    const platformIcons = {
        email: 'fas fa-envelope',
        whatsapp: 'fab fa-whatsapp',
        airbnb: 'fab fa-airbnb',
        smoobu: 'fas fa-building',
    };

    for (const result of data.results) {
        const convId = String(result.conversation_id);
        if (existingIds.has(convId)) continue;

        const iconClass = platformIcons[result.platform] || 'fas fa-comment';
        const guestName = escapeHtml(result.guest_name || 'Unknown Guest');
        const subject = escapeHtml(result.property_name || result.subject || '');
        const matchLabel = result.match_count > 1 ? `<span class="match-count">(${result.match_count} matches)</span>` : '';
        // Defense-in-depth: escape everything, re-allow <mark> only.
        const snippet = (typeof escapeHtmlAllowMark === 'function')
            ? escapeHtmlAllowMark(result.first_snippet || '')
            : escapeHtml(result.first_snippet || '');

        const card = document.createElement('a');
        card.href = `/chatbot/conversation/${result.conversation_id}`;
        card.className = 'conversation-card search-result search-injected';
        card.dataset.conversationId = convId;
        card.dataset.platform = result.platform || '';
        card.dataset.guestId = result.guest_id || '';
        card.style.display = 'flex';
        card.innerHTML = `
            <div class="conversation-avatar" data-guest-name="${guestName}">
                <i class="${iconClass}"></i>
            </div>
            <div class="conversation-info">
                <div class="conversation-header">
                    <span class="guest-name">${guestName}</span>
                    ${matchLabel}
                </div>
                <div class="conversation-subject">${subject}</div>
                <div class="conversation-preview" style="display:none;"></div>
                <div class="search-snippet">${snippet}</div>
            </div>
            <div class="conversation-meta">
                <span class="platform-badge ${(result.display_platform || result.platform || '').toLowerCase().replace('booking.com', 'booking').replace(/\s/g, '')}">${escapeHtml(result.display_platform || result.platform || '')}</span>
            </div>
        `;

        // Insert before the search empty state
        const searchEmpty = container.querySelector('#searchEmptyState');
        if (searchEmpty) {
            container.insertBefore(card, searchEmpty);
        } else {
            container.appendChild(card);
        }
    }
}

function clearSearchMode() {
    isSearchMode = false;
    filterState.setSearch(null);

    const emptyState = document.getElementById('searchEmptyState');
    emptyState.style.display = 'none';

    // Remove injected search-only cards (conversations not in the original page)
    document.querySelectorAll('.conversation-card.search-injected').forEach(c => c.remove());

    document.querySelectorAll('.conversation-card').forEach(card => {
        card.classList.remove('search-result');
        const snippetEl = card.querySelector('.search-snippet');
        if (snippetEl) snippetEl.remove();
        const countEl = card.querySelector('.match-count');
        if (countEl) countEl.remove();
    });

    filterState.applyFilters();
}

function clearSearch() {
    document.getElementById('searchInput').value = '';
    const clearBtn = document.getElementById('searchClearBtn');
    if (clearBtn) clearBtn.classList.remove('visible');
    clearSearchMode();
}

// =========================================================================
// Guest Dropdown Population
// =========================================================================

async function populateGuestDropdown() {
    const dropdown = document.getElementById('guestFilter');
    if (!dropdown) return;

    try {
        const response = await fetch('/chatbot/api/guests');
        if (!response.ok) throw new Error('Failed to fetch guests');
        const data = await response.json();

        const counts = {};
        document.querySelectorAll('.conversation-card').forEach(card => {
            const guestId = card.dataset.guestId;
            if (guestId) counts[guestId] = (counts[guestId] || 0) + 1;
        });

        dropdown.innerHTML = '<option value="">All Guests</option>';

        const sortedGuests = data.guests.sort((a, b) => {
            const nameA = (a.name || a.email || '').toLowerCase();
            const nameB = (b.name || b.email || '').toLowerCase();
            return nameA.localeCompare(nameB);
        });

        sortedGuests.forEach(guest => {
            const count = counts[guest.id] || 0;
            if (count > 0) {
                const option = document.createElement('option');
                option.value = guest.id;
                const displayName = guest.name || guest.email || 'Unknown Guest';
                option.textContent = `${displayName} (${count})`;
                dropdown.appendChild(option);
            }
        });

        if (filterState.state.guest) {
            dropdown.value = filterState.state.guest;
        }
    } catch (error) {
        console.error('Failed to populate guest dropdown:', error);
    }
}

// =========================================================================
// Load More
// =========================================================================

let loadMorePage = 1;  // Page 1 is already loaded on initial render

function loadMoreConversations() {
    const btn = document.getElementById('loadMoreBtn');
    if (!btn || btn.disabled) return;

    btn.disabled = true;
    const icon = btn.querySelector('i');
    if (icon) { icon.className = 'fas fa-spinner fa-spin'; }

    loadMorePage++;

    fetch(`/chatbot/api/conversations?page=${loadMorePage}&per_page=50`)
    .then(r => r.json())
    .then(data => {
        const container = document.getElementById('conversationList');
        const loadMoreContainer = document.getElementById('loadMoreContainer');

        if (data.conversations && data.conversations.length > 0) {
            // Build set of already-displayed conversation IDs
            const existingIds = new Set();
            container.querySelectorAll('.conversation-card').forEach(card => {
                existingIds.add(card.dataset.conversationId);
            });

            // Append only new cards (skip duplicates)
            data.conversations.forEach(conv => {
                if (!existingIds.has(String(conv.id))) {
                    const card = createConversationCard(conv);
                    card.dataset.loadedMore = 'true';
                    // Insert before the load-more button container
                    if (loadMoreContainer) {
                        container.insertBefore(card, loadMoreContainer);
                    } else {
                        container.appendChild(card);
                    }
                }
            });

            filterState.applyFilters();
            insertDateGroupHeaders();
            applyAvatarColors();

            // Update count display
            const loadedCount = container.querySelectorAll('.conversation-card').length;
            const countEl = btn.querySelector('.load-more-count');
            if (countEl) {
                countEl.textContent = `(${loadedCount} / ${data.total})`;
            }

            // Hide button if all loaded
            if (loadMorePage >= data.pages) {
                if (loadMoreContainer) loadMoreContainer.style.display = 'none';
            }
        } else {
            if (loadMoreContainer) loadMoreContainer.style.display = 'none';
        }
    })
    .catch(err => {
        console.error('Failed to load more conversations:', err);
        loadMorePage--;  // Revert so user can retry
    })
    .finally(() => {
        btn.disabled = false;
        const ic = btn.querySelector('i');
        if (ic) { ic.className = 'fas fa-angle-down'; }
    });
}

// =========================================================================
// Polling Setup
// =========================================================================

let lastKnownTimestamp = null;
let lastKnownUnread = null;

async function fullInboxFetch(signal) {
    let url = '/chatbot/api/conversations?per_page=50';
    if (filterState.getState().status === 'escalated') {
        url += '&escalated=true';
    }
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    updateInboxList(data.conversations);
    updateInboxBadgeFromData(data.conversations);
    loadStats();
}

const inboxPoller = new PollingManager({
    fetchFn: async (signal) => {
        const checkResp = await fetch('/chatbot/api/conversations/last-updated', { signal });
        if (!checkResp.ok) throw new Error(`HTTP ${checkResp.status}`);
        const { ts, unread } = await checkResp.json();

        if (lastKnownTimestamp === null || ts !== lastKnownTimestamp || unread !== lastKnownUnread) {
            lastKnownTimestamp = ts;
            lastKnownUnread = unread;
            await fullInboxFetch(signal);
        }
        return null;
    },
    onUpdate: () => {},
    // 10s tripwire — was 3s, but 3s × every open tab × all day was the single
    // largest source of constant tunnel traffic, making the app feel "live" at
    // the cost of being uniquely vulnerable to mobile-network hiccups. 10s
    // still feels responsive (the average new-message wait drops by ~5s, not
    // a noticeable degradation), and total inbox requests/day drop ~70%.
    // PollingManager (polling.js) already pauses entirely when the tab is
    // hidden, so background tabs cost zero.
    interval: 10000,
    onError: (err) => {
        console.error('Inbox polling error:', err);
    }
});

async function closeConversation(event, convId) {
    event.preventDefault();
    event.stopPropagation();
    const card = document.querySelector(`.conversation-card[data-conversation-id="${convId}"]`);
    try {
        const resp = await fetch(`/chatbot/api/conversations/${convId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'closed' })
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        if (card) {
            card.style.transition = 'opacity 0.3s, transform 0.3s';
            card.style.opacity = '0';
            card.style.transform = 'translateX(30px)';
            setTimeout(() => {
                card.dataset.status = 'closed';
                card.style.opacity = '';
                card.style.transform = '';
                card.style.transition = '';
                filterState.applyFilters();
                loadStats();
            }, 300);
        }
    } catch (err) {
        console.error('Close conversation failed:', err);
        showNotification(i18n.t('inbox.closeChat.failed') || 'Failed to close conversation', 'error');
    }
}

async function markAllRead() {
    const btn = document.getElementById('markAllReadBtn');
    btn.disabled = true;
    try {
        const resp = await fetch('/chatbot/api/conversations/mark-all-read', { method: 'PATCH' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        document.querySelectorAll('.conversation-card.unread').forEach(card => {
            card.classList.remove('unread');
            const sr = card.querySelector('.sr-only');
            if (sr) sr.remove();
        });
        if (data.marked > 0) {
            showNotification(
                (i18n.t('inbox.markedAllRead') || '{count} marked as read').replace('{count}', data.marked),
                'success'
            );
        }
        loadStats();
    } catch (err) {
        console.error('Mark all read failed:', err);
        showNotification('Failed to mark all as read', 'error');
    } finally {
        btn.disabled = false;
    }
}

function refreshConversations() {
    lastKnownTimestamp = null;
    inboxPoller.stop();
    inboxPoller.start();
}

// =========================================================================
// Gmail Auto-Sync
// =========================================================================

let gmailPoller = null;

function initGmailAutoSync() {
    fetch('/chatbot/gmail/status')
        .then(r => r.json())
        .then(status => {
            if (status.authenticated) {
                const btn = document.getElementById('syncGmailBtn');
                if (btn) btn.style.display = '';

                gmailPoller = new PollingManager({
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
                            showNotification(
                                (i18n.t('inbox.gmail.synced') || '{count} new email(s) synced')
                                    .replace('{count}', data.processed),
                                'success'
                            );
                            inboxPoller.stop();
                            inboxPoller.start();
                        }
                    },
                    interval: 60000,
                    onError: (err) => {
                        if (err.message === 'GMAIL_DISCONNECTED') {
                            console.warn('Gmail disconnected, stopping auto-sync');
                            if (gmailPoller) gmailPoller.stop();
                            const btn = document.getElementById('syncGmailBtn');
                            if (btn) btn.style.display = 'none';
                        } else {
                            console.error('Gmail sync error:', err);
                        }
                    }
                });
                gmailPoller.start();
            }
        })
        .catch(err => {
            console.debug('Gmail status check failed:', err);
        });
}

function syncGmailNow() {
    const btn = document.getElementById('syncGmailBtn');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';

    fetch('/chatbot/api/gmail/process?max_results=10&auto_respond=false', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.processed > 0) {
                showNotification(
                    (i18n.t('inbox.gmail.synced') || '{count} new email(s) synced')
                        .replace('{count}', data.processed),
                    'success'
                );
                inboxPoller.stop();
                inboxPoller.start();
            } else {
                showNotification(i18n.t('inbox.gmail.noNew') || 'No new emails', 'info');
            }
        })
        .catch(err => {
            console.error('Manual Gmail sync failed:', err);
            showNotification(i18n.t('inbox.gmail.syncFailed') || 'Gmail sync failed', 'error');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        });
}

// =========================================================================
// Smoobu Auto-Sync
// =========================================================================

let smoobuPoller = null;

function initSmoobuAutoSync() {
    // Reveal the manual Smoobu Sync button if Smoobu is connected.
    // The 60s frontend auto-sync poller was removed: each /api/smoobu/sync
    // call takes 2+ minutes for large accounts, so a 60s poll per open tab
    // was holding Waitress threads continuously and causing remote users to
    // see 2-3 minute page loads. The server-side daemon already syncs every
    // 2 minutes, and the inbox's regular polling surfaces new messages.
    fetch('/chatbot/smoobu/status')
        .then(r => r.json())
        .then(status => {
            if (status.authenticated) {
                const btn = document.getElementById('syncSmoobuBtn');
                if (btn) btn.style.display = '';
            }
        })
        .catch(err => {
            console.debug('Smoobu status check failed:', err);
        });
}

function syncSmoobuNow() {
    // Fire-and-forget: the server hands the sync to a daemon thread and
    // returns immediately. New messages appear via the inbox's regular
    // polling within ~30s. We do NOT block the button waiting for the full
    // sync — that used to take 2+ minutes and trip Cloudflare's 100s timeout.
    const btn = document.getElementById('syncSmoobuBtn');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';

    fetch('/chatbot/api/smoobu/sync', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                showNotification(data.error, 'error');
            } else {
                showNotification(
                    i18n.t('settings.integrations.smoobu.syncStarted') || 'Smoobu sync gestartet — neue Nachrichten erscheinen in Kürze',
                    'info'
                );
                // Nudge the inbox poller so new messages surface ASAP once
                // the daemon finishes.
                inboxPoller.stop();
                inboxPoller.start();
            }
        })
        .catch(err => {
            console.error('Manual Smoobu sync trigger failed:', err);
            showNotification('Smoobu sync failed', 'error');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        });
}

// =========================================================================
// Dashboard Statistics
// =========================================================================

function loadStats() {
    fetch('/chatbot/api/stats')
        .then(r => r.json())
        .then(data => {
            document.getElementById('statConversations').textContent = data.total_conversations || 0;
            document.getElementById('statUnread').textContent = data.unread_count || 0;
            document.getElementById('statMessagesToday').textContent = data.messages_today || 0;

            const unreadEl = document.getElementById('statUnread').closest('.stat-item');
            if (data.unread_count > 0) {
                unreadEl.classList.add('has-unread');
            } else {
                unreadEl.classList.remove('has-unread');
            }
        })
        .catch(err => console.error('Failed to load stats:', err));
}

// Force immediate refresh when restored from bfcache
window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
        inboxPoller.stop();
        inboxPoller.start();
    }
});

// Prefetch conversation pages on hover for faster navigation
function initConversationPrefetch() {
    const container = document.getElementById('conversationList');
    if (!container) return;

    const prefetched = new Set();
    container.addEventListener('mouseenter', (e) => {
        const card = e.target.closest('.conversation-card');
        if (!card) return;
        const href = card.getAttribute('href');
        if (!href || prefetched.has(href)) return;
        prefetched.add(href);
        // Create a prefetch link — browser loads the page in background
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = href;
        document.head.appendChild(link);
    }, true);
}

// Start polling when page loads
document.addEventListener('DOMContentLoaded', () => {
    // Instant render from cache if available (makes "back to inbox" feel instant)
    const cached = loadCachedInbox();
    if (cached) {
        updateInboxList(cached);
    }

    refreshRelativeTimestamps();

    let timestampInterval = setInterval(refreshRelativeTimestamps, 60000);
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            clearInterval(timestampInterval);
            timestampInterval = null;
        } else {
            if (!timestampInterval) {
                refreshRelativeTimestamps();
                timestampInterval = setInterval(refreshRelativeTimestamps, 60000);
            }
        }
    });

    filterState.applyFilters();
    filterState.updateUI();

    insertDateGroupHeaders();

    const searchInput = document.getElementById('searchInput');
    if (filterState.state.search && searchInput) {
        searchInput.value = filterState.state.search;
        const clearBtn = document.getElementById('searchClearBtn');
        if (clearBtn) clearBtn.classList.add('visible');
        setTimeout(async () => {
            const results = await fetchSearchResults(filterState.state.search);
            renderSearchResults(results);
        }, 100);
    }

    populateGuestDropdown();
    loadStats();
    inboxPoller.start();
    initConversationPrefetch();

    // Stagger external service sync to avoid blocking page load
    setTimeout(() => initGmailAutoSync(), 3000);
    setTimeout(() => initSmoobuAutoSync(), 6000);
});
