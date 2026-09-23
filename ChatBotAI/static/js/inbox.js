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
    // last_message_at drives the shown time AND the date-group header, matching the
    // server's sort order (Conversation.last_message_at.desc). updated_at bumps on any
    // row touch (sync, read, AI summary), so grouping by it interleaved the headers.
    card.dataset.lastMessageAt = conv.last_message_at || '';
    card.dataset.platform = conv.platform;
    card.dataset.channel = conv.channel || '';
    card.dataset.account = conv.smoobu_account_id || '';
    card.dataset.status = conv.status;
    card.dataset.guestId = conv.guest_id || '';
    card.dataset.isRead = conv.is_read ? 'true' : 'false';
    card.dataset.escalated = conv.escalated ? 'true' : 'false';
    card.dataset.autoRespond = conv.auto_respond ? 'true' : 'false';
    card.dataset.hasPendingApproval = conv.has_pending_approval ? 'true' : 'false';
    card.dataset.aiEnabled = conv.ai_enabled ? 'true' : 'false';
    card.dataset.lastSender = (conv.last_message && conv.last_message.sender_type) || '';
    if (conv.escalated) card.classList.add('escalated');

    const guestName = (conv.guest && (conv.guest.name || conv.guest.email)) || i18n.t('ux.unknownGuest');

    let preview = i18n.t('ux.noMessages');
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
                <span class="conversation-time" data-timestamp="${conv.last_message_at || ''}" title="${formatAbsoluteTime(conv.last_message_at)}">${formatRelativeTime(conv.last_message_at)}</span>
            </div>
            <div class="conversation-subject">${escapeHtml(conv.property_name || conv.subject || i18n.t('ux.noSubject'))}${conv.check_in && conv.check_out ? ` <span class="stay-dates">${formatStayDates(conv.check_in, conv.check_out)}</span>` : ''}</div>
            <div class="conversation-preview">${escapeHtml(preview)}</div>
        </div>
        <div class="conversation-meta">
            <span class="platform-badge ${(conv.display_platform || conv.platform).toLowerCase().replace('booking.com', 'booking').replace(/\s/g, '')}">${escapeHtml(conv.display_platform || conv.platform)}</span>
            ${aiBadge}
            ${escalationLabel}
            ${approvalLabel}
            ${cancellationLabel}
            <span class="status-badge ${conv.status}">${formatStatus(conv.status)}</span>
            <button class="card-menu-btn" onclick="openCardMenu(event, ${conv.id})" title="${i18n.t('inbox.menu.title') || 'Optionen'}" aria-label="Optionen"><i class="fas fa-ellipsis-v"></i></button>
        </div>
    `;

    return card;
}

function updateConversationCard(card, conv) {
    card.dataset.updatedAt = conv.updated_at || '';
    card.dataset.lastMessageAt = conv.last_message_at || '';
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
        timeEl.dataset.timestamp = conv.last_message_at || '';
        timeEl.title = formatAbsoluteTime(conv.last_message_at);
        timeEl.textContent = formatRelativeTime(conv.last_message_at);
    }

    const previewEl = card.querySelector('.conversation-preview');
    if (previewEl) {
        let preview = i18n.t('ux.noMessages');
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
        const lastMessageAt = card.dataset.lastMessageAt;
        const group = getDateGroup(lastMessageAt);
        if (group !== lastGroup) {
            container.insertBefore(createDateGroupHeader(group), card);
            lastGroup = group;
        }
    });
}

// =========================================================================
// Filter and Search (using FilterState module)
// =========================================================================

const filterDropdown = document.getElementById('filterDropdown');

document.querySelectorAll('[data-filter-channel]').forEach(btn => {
    btn.addEventListener('click', function() {
        filterState.setChannel(this.dataset.filterChannel || null);
        filterDropdown.open = false;
    });
});

document.querySelectorAll('[data-filter-account]').forEach(btn => {
    btn.addEventListener('click', function() {
        filterState.setAccount(this.dataset.filterAccount || null);
        filterDropdown.open = false;
    });
});

// <details> doesn't close on outside tap by itself.
document.addEventListener('click', (e) => {
    if (filterDropdown.open && !filterDropdown.contains(e.target)) filterDropdown.open = false;
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
    // Stale response: the user cleared or changed the query while it was in flight.
    const currentQuery = (document.getElementById('searchInput').value || '').trim();
    if (data.query !== currentQuery) return;

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
        const guestName = escapeHtml(result.guest_name || i18n.t('ux.unknownGuest'));
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
    // Kill any in-flight debounce, otherwise it fires after the clear and
    // re-renders the results the user just dismissed.
    if (searchTimeout) { clearTimeout(searchTimeout); searchTimeout = null; }
    const input = document.getElementById('searchInput');
    if (input) input.value = '';
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
                const displayName = guest.name || guest.email || i18n.t('ux.unknownGuest');
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

    fetch(`/chatbot/api/conversations?page=${loadMorePage}&per_page=50${serverFilterParams()}`)
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
    const st = filterState.getState();
    // Unread and Eskaliert are server-side filters that must return the WHOLE set,
    // not just page 1 — otherwise the old ones (escalations run months back) stay
    // hidden behind "Mehr laden", which is exactly the pile nobody was seeing.
    // ponytail: 500 covers any realistic backlog; raise it if a filter ever
    // legitimately exceeds 500 conversations at once.
    const fullSet = st.unread || st.status === 'escalated' || st.status === 'pending_approval';
    const perPage = fullSet ? 500 : 50;
    let url = `/chatbot/api/conversations?per_page=${perPage}${serverFilterParams()}`;
    if (st.status === 'escalated') url += '&escalated=true';
    if (st.status === 'pending_approval') url += '&status=pending_approval';
    if (st.unread) url += '&unread=true';
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    // The fetch returns the complete set in full-set mode, so "Mehr laden" would
    // page over a list that is already whole. One place decides it, for every
    // path that can enter or leave these filters.
    const loadMoreEl = document.getElementById('loadMoreContainer');
    if (loadMoreEl) loadMoreEl.style.display = fullSet ? 'none' : '';
    updateInboxList(data.conversations);
    loadStats();
}

// The "Ungelesen" filter is server-backed (see fullInboxFetch): toggling it must
// re-fetch so ALL unread conversations load, not just the ones already on screen.
// "Load More" is hidden while the filter is on because the fetch returns the full set.
// Side effects of the unread filter live on the state hook so EVERY path that flips it
// — the toggle button, the badge ✕, and "Filter löschen" — refetches the correct list.
// Channel and account are server-side filters (the inbox is paginated), so any change
// must replace the list rather than hide cards. Same reasoning as the unread filter.
function serverFilterParams() {
    const st = filterState.getState();
    return (st.channel ? `&channel=${encodeURIComponent(st.channel)}` : '')
         + (st.account ? `&account=${encodeURIComponent(st.account)}` : '');
}

filterState.onServerFilterChange = () => {
    loadMorePage = 1;  // the refetch replaces the list; keep Load More paging honest
    fullInboxFetch().catch(err => console.error('Filter refresh failed:', err));
};

filterState.onUnreadChange = (unread) => {
    loadMorePage = 1;  // full refetch replaces the list; keep Load More paging consistent
    fullInboxFetch().catch(err => console.error('Unread filter refresh failed:', err));
};

function toggleUnreadFilter() {
    filterState.toggleUnread();
}

// The Eskaliert / UMI-Freigabe tiles are the status filter: tapping one a second
// time clears it instead of stranding the team in it.
function toggleStatusFilter(status) {
    filterState.setStatus(filterState.state.status === status ? null : status);
}

const inboxPoller = new PollingManager({
    fetchFn: async (signal) => {
        const checkResp = await fetch('/chatbot/api/conversations/last-updated', { signal });
        if (!checkResp.ok) throw new Error(`HTTP ${checkResp.status}`);
        const { ts, unread } = await checkResp.json();

        if (lastKnownTimestamp === null || ts !== lastKnownTimestamp || unread !== lastKnownUnread) {
            await fullInboxFetch(signal);
            lastKnownTimestamp = ts;
            lastKnownUnread = unread;
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
                            const body = await response.json().catch(() => ({}));
                            throw new Error(body.session_expired ? 'SESSION_EXPIRED' : 'GMAIL_DISCONNECTED');
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

// No frontend Smoobu poller: the server daemon syncs, and the button's
// visibility is rendered server-side (inbox.html).
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
            setInboxBadge(data.unread_count || 0);  // badge and tile: one number
            document.getElementById('statMessagesToday').textContent = data.messages_today || 0;

            // Open escalations get their own stat tile. Without one nobody
            // noticed them: 19 were open, the oldest three months old. Always
            // shown — a standing "0" is the team's "nothing pending" signal —
            // and only red when there is actually something to handle.
            const escItem = document.getElementById('statEscalatedItem');
            if (escItem) {
                const n = data.escalated_count || 0;
                document.getElementById('statEscalated').textContent = n;
                escItem.classList.toggle('has-escalations', n > 0);
            }
            const approvals = data.pending_approval_count || 0;
            document.getElementById('statApproval').textContent = approvals;
            document.getElementById('statApprovalItem').classList.toggle('has-approvals', approvals > 0);

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

    // If the inbox loaded with a full-set filter active (persisted/bookmarked
    // URL), fetch the whole set from the server instead of filtering page 1.
    // fullInboxFetch hides "Mehr laden" itself.
    if (filterState.state.unread || filterState.state.status === 'escalated'
        || filterState.state.status === 'pending_approval') {
        fullInboxFetch().catch(err => console.error('Filter initial load failed:', err));
    }

    populateGuestDropdown();
    loadStats();
    inboxPoller.start();
    initConversationPrefetch();
    initCardMenu();

    // Stagger external service sync to avoid blocking page load
    setTimeout(() => initGmailAutoSync(), 3000);
});

// ============================================================================
// Inbox card ⋮ quick-actions menu
// ============================================================================
let cardMenuEl = null;        // single reused popover
let cardMenuConvId = null;

function ensureCardMenuEl() {
    if (cardMenuEl) return cardMenuEl;
    cardMenuEl = document.createElement('div');
    cardMenuEl.className = 'card-menu';
    document.body.appendChild(cardMenuEl);
    // Delegated clicks for the standing menu items (data-action). Preview
    // buttons wire their own handlers.
    cardMenuEl.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        handleCardMenuAction(btn.dataset.action);
    });
    return cardMenuEl;
}

function closeCardMenu() {
    if (cardMenuEl) {
        cardMenuEl.classList.remove('open');
        cardMenuEl.innerHTML = '';
    }
    cardMenuConvId = null;
}

function openCardMenu(event, convId) {
    event.preventDefault();
    event.stopPropagation();
    const card = document.querySelector(`.conversation-card[data-conversation-id="${convId}"]`);
    if (!card) return;
    // Second tap on the same button closes it.
    if (cardMenuConvId === convId && cardMenuEl && cardMenuEl.classList.contains('open')) {
        closeCardMenu();
        return;
    }
    const menu = ensureCardMenuEl();
    cardMenuConvId = convId;
    menu.innerHTML = buildCardMenuHtml(card);
    menu.classList.add('open');
    positionCardMenu(menu, event.currentTarget || card.querySelector('.card-menu-btn') || card);
}

function positionCardMenu(menu, anchor) {
    const rect = anchor.getBoundingClientRect();
    const mW = menu.offsetWidth;
    const mH = menu.offsetHeight;
    let left = rect.right - mW;                 // right-align to the button
    if (left < 8) left = 8;
    if (left + mW > window.innerWidth - 8) left = window.innerWidth - mW - 8;
    let top = rect.bottom + 6;
    if (top + mH > window.innerHeight - 8) top = rect.top - mH - 6;   // flip up
    if (top < 8) top = 8;
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';
}

function cardMenuItem(action, icon, label, extraClass) {
    return `<button class="card-menu-item ${extraClass || ''}" data-action="${action}">
        <i class="fas ${icon}"></i><span>${escapeHtml(label)}</span></button>`;
}

function buildCardMenuHtml(card) {
    const t = (k, d) => i18n.t(k) || d;
    const isRead = card.dataset.isRead === 'true';
    const status = card.dataset.status;
    const autoRespond = card.dataset.autoRespond === 'true';
    const aiEnabled = card.dataset.aiEnabled === 'true';
    const escalated = card.dataset.escalated === 'true';
    const lastSender = card.dataset.lastSender;
    let html = '';

    html += cardMenuItem('read', isRead ? 'fa-envelope' : 'fa-envelope-open',
        isRead ? t('inbox.menu.markUnread', 'Als ungelesen markieren')
               : t('inbox.menu.markRead', 'Als gelesen markieren'));

    if (aiEnabled) {
        html += cardMenuItem('auto', 'fa-bolt',
            autoRespond ? t('inbox.menu.autoOff', 'Auto-Antwort AUS')
                        : t('inbox.menu.autoOn', 'Auto-Antwort AN'));
    }

    // UMI-Antwort — only when UMI is on, chat is not escalated, and the guest
    // sent the last message (avoids double-replying).
    if (aiEnabled && !escalated && lastSender === 'guest') {
        const instant = window.inboxConfig && window.inboxConfig.instantSend;
        html += cardMenuItem('umi', 'fa-robot',
            instant ? t('inbox.menu.umiReplySend', 'UMI-Antwort senden')
                    : t('inbox.menu.umiReply', 'UMI-Antwort'));
    }

    // Manual escalation — independent of UMI, the team marks chats important too.
    html += cardMenuItem('escalate', escalated ? 'fa-check-circle' : 'fa-exclamation-triangle',
        escalated ? t('inbox.menu.resolve', 'Eskalation lösen')
                  : t('inbox.menu.escalate', 'Als wichtig markieren'));

    if (status !== 'closed') {
        html += '<div class="card-menu-sep"></div>';
        html += cardMenuItem('close', 'fa-times-circle',
            t('inbox.menu.close', 'Chat schließen'), 'card-menu-danger');
    }
    return html;
}

function handleCardMenuAction(action) {
    const convId = cardMenuConvId;
    const card = document.querySelector(`.conversation-card[data-conversation-id="${convId}"]`);
    if (!card) { closeCardMenu(); return; }
    if (action === 'read') return cardToggleRead(convId, card);
    if (action === 'auto') return cardToggleAuto(convId, card);
    if (action === 'umi') return cardUmiReply(convId, card);
    if (action === 'escalate') return cardToggleEscalation(convId, card);
    if (action === 'close') { closeCardMenu(); closeConversation(_noopEvent(), convId); }
}

function _noopEvent() {
    return { preventDefault() {}, stopPropagation() {} };
}

function cardToggleRead(convId, card) {
    const isRead = card.dataset.isRead === 'true';
    const opts = isRead
        ? { method: 'POST' }
        : { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) };
    const url = isRead ? `/chatbot/api/conversations/${convId}/unread`
                       : `/chatbot/api/conversations/${convId}/read`;
    fetch(url, opts)
        .then(r => r.json())
        .then(d => {
            const nowRead = !!d.is_read;
            card.dataset.isRead = nowRead ? 'true' : 'false';
            card.classList.toggle('unread', !nowRead);
            const sr = card.querySelector('.sr-only');
            if (nowRead && sr) sr.remove();
            if (!nowRead && !sr) {
                const s = document.createElement('span');
                s.className = 'sr-only';
                s.textContent = 'Unread';
                card.insertBefore(s, card.firstChild);
            }
            if (typeof loadStats === 'function') loadStats();
        })
        .catch(() => showNotification(i18n.t('common.error') || 'Fehler', 'error'))
        .finally(closeCardMenu);
}

function cardToggleEscalation(convId, card) {
    const wasEscalated = card.dataset.escalated === 'true';
    const url = `/chatbot/api/conversations/${convId}/${wasEscalated ? 'resolve' : 'escalate'}`;
    fetch(url, { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (!d.success) { showNotification(d.error || (i18n.t('common.error') || 'Fehler'), 'error'); return; }
            const nowEscalated = !!d.escalated;
            card.dataset.escalated = nowEscalated ? 'true' : 'false';
            card.classList.toggle('escalated', nowEscalated);
            const existing = card.querySelector('.escalation-badge');
            const metaEl = card.querySelector('.conversation-meta');
            if (nowEscalated && !existing && metaEl) {
                const badge = document.createElement('span');
                badge.className = 'escalation-badge';
                badge.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${i18n.t('inbox.needsAttention') || 'Braucht Aufmerksamkeit'}`;
                metaEl.insertBefore(badge, card.querySelector('.status-badge'));
            } else if (!nowEscalated && existing) {
                existing.remove();
            }
            filterState.applyFilters();
            showNotification(
                nowEscalated ? (i18n.t('inbox.menu.escalateDone') || 'Als wichtig markiert')
                             : (i18n.t('conversation.escalation.resolved') || 'Eskalation gelöst'),
                'success');
        })
        .catch(() => showNotification(i18n.t('common.error') || 'Fehler', 'error'))
        .finally(closeCardMenu);
}

function cardToggleAuto(convId, card) {
    fetch(`/chatbot/api/conversations/${convId}/toggle-auto-respond`, { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) { showNotification(d.error, 'error'); return; }
            card.dataset.autoRespond = d.auto_respond ? 'true' : 'false';
            const badge = card.querySelector('.ai-badge');
            if (badge) {
                badge.classList.toggle('auto-respond-on', d.auto_respond);
                badge.classList.toggle('auto-respond-off', !d.auto_respond);
            }
            showNotification(
                d.auto_respond ? (i18n.t('inbox.menu.autoOnDone') || 'Auto-Antwort an')
                               : (i18n.t('inbox.menu.autoOffDone') || 'Auto-Antwort aus'),
                'success');
        })
        .catch(() => showNotification(i18n.t('common.error') || 'Fehler', 'error'))
        .finally(closeCardMenu);
}

function cardUmiReply(convId, card) {
    const menu = cardMenuEl;
    menu.innerHTML = `<div class="card-menu-spinner"><i class="fas fa-spinner fa-spin"></i> ${escapeHtml(i18n.t('inbox.menu.generating') || 'UMI denkt nach…')}</div>`;
    const anchor = card.querySelector('.card-menu-btn');
    if (anchor) positionCardMenu(menu, anchor);
    fetch(`/chatbot/api/conversations/${convId}/ai-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_only: true })
    })
        .then(async r => ({ ok: r.ok, data: await r.json().catch(() => ({})) }))
        .then(({ ok, data }) => {
            if (cardMenuConvId !== convId) return;   // menu changed/closed meanwhile
            if (data.skipped) {
                showNotification(i18n.t('inbox.menu.noReplyNeeded') || 'Keine Antwort nötig', 'info');
                closeCardMenu();
                return;
            }
            if (!ok || data.error || !data.message) {
                menu.innerHTML = `<div class="card-menu-spinner">${escapeHtml(data.error || (i18n.t('common.error') || 'Fehler'))}</div>`;
                if (anchor) positionCardMenu(menu, anchor);
                return;
            }
            if (window.inboxConfig && window.inboxConfig.instantSend) {
                cardApproveDraft(data.message.id);
            } else {
                renderDraftPreview(convId, data.message, card);
            }
        })
        .catch(() => {
            menu.innerHTML = `<div class="card-menu-spinner">${escapeHtml(i18n.t('common.error') || 'Fehler')}</div>`;
        });
}

function renderDraftPreview(convId, msg, card) {
    const menu = cardMenuEl;
    menu.innerHTML = `
        <div class="card-menu-preview">
            <div class="cm-draft">${escapeHtml(msg.content || '')}</div>
            <div class="cm-actions">
                <button class="btn btn-secondary btn-sm" data-cm="cancel">${escapeHtml(i18n.t('inbox.menu.cancel') || 'Abbrechen')}</button>
                <button class="btn btn-primary btn-sm" data-cm="send">${escapeHtml(i18n.t('inbox.menu.send') || 'Senden')}</button>
            </div>
        </div>`;
    menu.querySelector('[data-cm="cancel"]').addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation(); cardRejectDraft(msg.id);
    });
    menu.querySelector('[data-cm="send"]').addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation(); cardApproveDraft(msg.id);
    });
    const anchor = card.querySelector('.card-menu-btn');
    if (anchor) positionCardMenu(menu, anchor);
}

function cardApproveDraft(messageId) {
    fetch(`/chatbot/api/messages/${messageId}/approve`, { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) { showNotification(d.error, 'error'); return; }
            showNotification(i18n.t('inbox.menu.sent') || 'Gesendet', 'success');
            if (typeof refreshConversations === 'function') refreshConversations();
        })
        .catch(() => showNotification(i18n.t('inbox.menu.sendError') || 'Senden fehlgeschlagen', 'error'))
        .finally(closeCardMenu);
}

function cardRejectDraft(messageId) {
    fetch(`/chatbot/api/messages/${messageId}/reject`, { method: 'POST' })
        .catch(() => {})
        .finally(closeCardMenu);
}

function initCardMenu() {
    ensureCardMenuEl();
    document.addEventListener('click', (e) => {
        if (cardMenuEl && cardMenuEl.classList.contains('open') &&
            !cardMenuEl.contains(e.target) && !e.target.closest('.card-menu-btn')) {
            closeCardMenu();
        }
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeCardMenu(); });
    const list = document.getElementById('conversationList');
    if (list) list.addEventListener('scroll', closeCardMenu, { passive: true });
    window.addEventListener('scroll', closeCardMenu, { passive: true });
}

// ============================================================================
// Guided Tour — inbox page steps (engine lives in guided-tour.js)
// ============================================================================
GuidedTour.buildSteps = function () {
    const steps = [];
    steps.push({
        selector: '#statsCard',
        titleKey: 'tour.inbox.stats',
        textKey: 'tour.inbox.stats.desc'
    });
    // A real conversation row — only if the list isn't empty.
    if (document.querySelector('.conversation-card')) {
        steps.push({
            selector: '.conversation-card',
            titleKey: 'tour.inbox.card',
            textKey: 'tour.inbox.card.desc'
        });
    }
    // The ⋮ quick-actions menu — only if a card (and its button) is present.
    if (document.querySelector('.card-menu-btn')) {
        steps.push({
            selector: '.card-menu-btn',
            titleKey: 'tour.inbox.menu',
            textKey: 'tour.inbox.menu.desc'
        });
    }
    steps.push({
        selector: '#filterDropdown',
        titleKey: 'tour.inbox.platform',
        textKey: 'tour.inbox.platform.desc'
    });
    steps.push({
        selector: '.search-box',
        titleKey: 'tour.inbox.search',
        textKey: 'tour.inbox.search.desc'
    });
    steps.push({
        selector: '#markAllReadBtn',
        titleKey: 'tour.inbox.markRead',
        textKey: 'tour.inbox.markRead.desc'
    });
    return steps;
};


// Inbox-wide sweep: pull Booking guest messages straight out of Gmail into the
// chats they provably belong to. Separate from the review queue on purpose — it
// inserts only exact reservation/date matches and queues nothing.
// The server runs it in the background (a full sweep exceeds Cloudflare's 100s
// limit), so we poll for the result instead of waiting on the request.
function sweepBookingEmails() {
    const btn = document.getElementById('emailSweepBtn');
    const originalHtml = btn ? btn.innerHTML : '';
    const busy = (on) => {
        if (!btn) return;
        btn.disabled = on;
        btn.innerHTML = on
            ? '<i class="fas fa-spinner fa-spin"></i> Suche…'
            : originalHtml;
    };

    busy(true);
    fetch('/chatbot/api/email/sweep', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: 30 }),
    })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                busy(false);
                showNotification(data.error || 'E-Mail-Suche fehlgeschlagen', 'error', 4000);
                return;
            }
            showNotification('Suche läuft — Nachrichten erscheinen nach und nach.', 'info', 4000);
            pollSweep();
        })
        .catch(() => {
            busy(false);
            showNotification('E-Mail-Suche fehlgeschlagen', 'error', 4000);
        });

    let tries = 0;
    function pollSweep() {
        // ~5 minutes at 5s. A sweep that outlives that keeps running server-side;
        // the messages still land, the button just stops reporting on it.
        if (++tries > 60) { busy(false); return; }
        setTimeout(() => {
            fetch('/chatbot/api/email/sweep')
                .then(r => r.json())
                .then(s => {
                    if (s.running) { pollSweep(); return; }
                    busy(false);
                    const n = (s.last && s.last.auto_inserted) || 0;
                    if (n > 0) {
                        showNotification(
                            `${n} Nachricht${n === 1 ? '' : 'en'} aus E-Mails übernommen`,
                            'success', 5000);
                        inboxPoller.stop();
                        inboxPoller.start();
                    } else {
                        showNotification('Keine fehlenden Nachrichten gefunden', 'info', 4000);
                    }
                })
                .catch(() => busy(false));
        }, 5000);
    }
}
