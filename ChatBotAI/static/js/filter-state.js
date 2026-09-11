/**
 * FilterState - Centralized filter state management with URL synchronization
 *
 * Manages channel, account and status filters for the inbox, persisting state in URL
 * for bookmarking and browser navigation support.
 */

class FilterState {
    constructor() {
        this.state = {
            channel: null,   // null = all, or 'booking'|'airbnb'|'direct'|'whatsapp'
            account: null,   // null = all, or a Smoobu account id
            status: null,    // null = all, or 'active'|'pending_owner'|'closed'
            guest: null,     // null = all, or guest ID string
            search: null,    // null = no search, or query string
            unread: false    // true = show only unread conversations
        };

        // Fired whenever the unread filter flips (any path). inbox.js sets this to
        // re-fetch the server-backed unread set / restore the normal list.
        this.onUnreadChange = null;

        // Same idea for channel/account: both are server-side filters (the inbox is
        // paginated), so every path that changes them — button, badge X, "Filter
        // löschen", browser back — must refetch. Hook it here, not per call site.
        this.onServerFilterChange = null;

        // Load initial state from URL
        this.loadFromURL();

        // Handle browser back/forward navigation
        window.addEventListener('popstate', () => {
            this.loadFromURL();
            this.applyFilters();
            this.updateUI();
            if (this.onServerFilterChange) this.onServerFilterChange();
            // Sync search input with URL state
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {
                searchInput.value = this.state.search || '';
            }
        });
    }

    /**
     * Load filter state from URL query parameters
     */
    loadFromURL() {
        const params = new URLSearchParams(window.location.search);
        this.state.channel = params.get('channel') || null;
        this.state.account = params.get('account') || null;
        this.state.status = params.get('status') || null;
        this.state.guest = params.get('guest') || null;
        this.state.search = params.get('q') || null;
        this.state.unread = params.get('unread') === 'true';
    }

    /**
     * Save current filter state to URL using history.replaceState
     * Uses replaceState to avoid cluttering browser history
     */
    saveToURL() {
        const url = new URL(window.location.href);

        // Set or delete channel param
        if (this.state.channel) {
            url.searchParams.set('channel', this.state.channel);
        } else {
            url.searchParams.delete('channel');
        }

        // Set or delete account param
        if (this.state.account) {
            url.searchParams.set('account', this.state.account);
        } else {
            url.searchParams.delete('account');
        }

        // Set or delete status param
        if (this.state.status) {
            url.searchParams.set('status', this.state.status);
        } else {
            url.searchParams.delete('status');
        }

        // Set or delete guest param
        if (this.state.guest) {
            url.searchParams.set('guest', this.state.guest);
        } else {
            url.searchParams.delete('guest');
        }

        // Set or delete search param
        if (this.state.search) {
            url.searchParams.set('q', this.state.search);
        } else {
            url.searchParams.delete('q');
        }

        // Set or delete unread param
        if (this.state.unread) {
            url.searchParams.set('unread', 'true');
        } else {
            url.searchParams.delete('unread');
        }

        // Update URL without creating history entry
        history.replaceState(null, '', url.toString());
    }

    /**
     * Set booking-channel filter (server-side)
     * @param {string|null} channel - 'booking'|'airbnb'|'direct'|'whatsapp', or null for all
     */
    setChannel(channel) {
        this.state.channel = channel || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
        if (this.onServerFilterChange) this.onServerFilterChange();
    }

    /**
     * Set Smoobu account filter (server-side)
     * @param {string|null} account - Smoobu account id, or null for all
     */
    setAccount(account) {
        this.state.account = account || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
        if (this.onServerFilterChange) this.onServerFilterChange();
    }

    /**
     * Set status filter
     * @param {string|null} status - Status to filter by, or null for all
     */
    setStatus(status) {
        const serverBacked = s => s === 'escalated' || s === 'pending_approval';
        const wasServerBacked = serverBacked(this.state.status);
        this.state.status = status || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
        // 'escalated' and 'pending_approval' are server-backed: the inbox is
        // paginated, and escalations run months back, so DOM-filtering page 1
        // showed one of nineteen. Entering AND leaving must refetch — leaving
        // has to restore the normal paginated list.
        if ((serverBacked(this.state.status) || wasServerBacked)
            && this.onServerFilterChange) {
            this.onServerFilterChange();
        }
    }

    /**
     * Set guest filter
     * @param {string|null} guestId - Guest ID to filter by, or null for all
     */
    setGuest(guestId) {
        this.state.guest = guestId || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    /**
     * Clear guest filter (shorthand)
     */
    clearGuest() {
        this.setGuest(null);
    }

    /**
     * Toggle unread filter
     */
    toggleUnread() {
        this.state.unread = !this.state.unread;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
        if (this.onUnreadChange) this.onUnreadChange(this.state.unread);
    }

    /**
     * Set search query
     * @param {string|null} query - Search query, or null to clear
     */
    setSearch(query) {
        this.state.search = query || null;
        this.saveToURL();
        // Don't call applyFilters - search handler does server fetch.
        // updateUI IS needed: it repaints the badge row, so the search chip
        // appears while typing and — the actual bug — disappears when its own
        // X clears the search instead of lingering until a page reload.
        this.updateUI();
    }

    /**
     * Clear search (shorthand)
     */
    clearSearch() {
        // inbox.js owns the search-mode DOM (injected cards, snippets, empty
        // state). Delegate so every X does the same full cleanup.
        if (typeof window.clearSearch === 'function') {
            window.clearSearch();
            return;
        }
        this.setSearch(null);
    }

    /**
     * Reset all filters to default (no filtering)
     */
    reset() {
        const wasUnread = this.state.unread;
        const hadServerFilter = !!(this.state.channel || this.state.account
                                   || this.state.status === 'escalated'
                                   || this.state.status === 'pending_approval');
        this.state.channel = null;
        this.state.account = null;
        this.state.status = null;
        this.state.guest = null;
        this.state.search = null;
        this.state.unread = false;
        // Also tear down search mode, otherwise injected result cards survive
        // "Filter löschen" and the inbox keeps showing the search results.
        if (typeof window.clearSearch === 'function') window.clearSearch();
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
        if (wasUnread && this.onUnreadChange) this.onUnreadChange(false);
        // onUnreadChange already refetches; only refetch here when it didn't run.
        else if (hadServerFilter && this.onServerFilterChange) this.onServerFilterChange();
    }

    /**
     * Clear status filter (shorthand)
     */
    clearStatus() {
        this.setStatus(null);
    }

    /**
     * Apply current filters to conversation cards
     * Combines channel, account, status, and search filters
     */
    applyFilters() {
        const cards = document.querySelectorAll('.conversation-card');
        const searchInput = document.getElementById('searchInput');
        const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';

        cards.forEach(card => {
            const matchesChannel = !this.state.channel || card.dataset.channel === this.state.channel;
            const matchesAccount = !this.state.account || card.dataset.account === this.state.account;
            const matchesStatus = !this.state.status
                || (this.state.status === 'escalated' ? card.dataset.escalated === 'true'
                    : this.state.status === 'pending_approval' ? card.dataset.hasPendingApproval === 'true'
                    : card.dataset.status === this.state.status);
            const matchesGuest = !this.state.guest || card.dataset.guestId === this.state.guest;
            const matchesSearch = !searchTerm || card.textContent.toLowerCase().includes(searchTerm);
            const matchesUnread = !this.state.unread || card.dataset.isRead === 'false';

            card.style.display = (matchesChannel && matchesAccount && matchesStatus && matchesGuest && matchesSearch && matchesUnread) ? 'flex' : 'none';
        });

        // Hide date group headers that have no visible cards after them
        document.querySelectorAll('.date-group-header').forEach(header => {
            let hasVisibleCard = false;
            let sibling = header.nextElementSibling;
            while (sibling && !sibling.classList.contains('date-group-header')) {
                if (sibling.classList.contains('conversation-card') && sibling.style.display !== 'none') {
                    hasVisibleCard = true;
                    break;
                }
                sibling = sibling.nextElementSibling;
            }
            header.style.display = hasVisibleCard ? 'flex' : 'none';
        });
    }

    /**
     * Update UI elements to reflect current filter state
     * - Toggle active class on filter buttons
     * - Update active filter indicators
     */
    updateUI() {
        // Update channel filter buttons
        document.querySelectorAll('[data-filter-channel]').forEach(btn => {
            const filterValue = btn.dataset.filterChannel;
            const isActive = (filterValue === '' && !this.state.channel) ||
                            (filterValue === this.state.channel);
            btn.classList.toggle('active', isActive);
        });

        // Update account filter buttons
        document.querySelectorAll('[data-filter-account]').forEach(btn => {
            const filterValue = btn.dataset.filterAccount;
            const isActive = (filterValue === '' && !this.state.account) ||
                            (filterValue === this.state.account);
            btn.classList.toggle('active', isActive);
        });

        // Stat tiles double as the unread / status filter buttons
        document.querySelectorAll('[data-stat-filter]').forEach(tile => {
            const f = tile.dataset.statFilter;
            tile.classList.toggle('active', f === 'unread' ? this.state.unread : this.state.status === f);
        });

        // Sync guest dropdown selection
        const guestDropdown = document.getElementById('guestFilter');
        if (guestDropdown) {
            guestDropdown.value = this.state.guest || '';
        }

        // Update active filter indicators
        this.updateFilterIndicators();
    }

    /**
     * Render active filter badges to the #activeFilters container
     */
    updateFilterIndicators() {
        const container = document.getElementById('activeFilters');
        const clearBtn = document.getElementById('clearFiltersBtn');

        if (!container) return;

        // Clear existing badges
        container.innerHTML = '';

        // Add channel badge if filtered
        if (this.state.channel) {
            container.appendChild(this.createFilterBadge('channel', this.state.channel));
        }

        // Add account badge if filtered
        if (this.state.account) {
            container.appendChild(this.createFilterBadge('account', this.state.account));
        }

        // Add status badge if filtered
        if (this.state.status) {
            container.appendChild(this.createFilterBadge('status', this.state.status));
        }

        // Add guest badge if filtered
        if (this.state.guest) {
            container.appendChild(this.createFilterBadge('guest', this.state.guest));
        }

        // Add unread badge if filtered
        if (this.state.unread) {
            container.appendChild(this.createFilterBadge('unread', 'unread'));
        }

        // Add search badge if searching
        if (this.state.search) {
            container.appendChild(this.createFilterBadge('search', this.state.search));
        }

        // Show/hide clear all button
        const hasActiveFilters = this.state.channel || this.state.account || this.state.status || this.state.guest || this.state.search || this.state.unread;
        if (clearBtn) {
            clearBtn.style.display = hasActiveFilters ? 'inline-flex' : 'none';
        }
    }

    /**
     * Create a filter badge element
     * @param {string} type - 'channel', 'account', 'status', ...
     * @param {string} value - The filter value
     * @returns {HTMLElement} The badge element
     */
    createFilterBadge(type, value) {
        const badge = document.createElement('span');
        // Guest badges use just 'guest' class (value is ID), others use type-value
        const badgeClass = type === 'guest' ? type : `${type}-${value}`;
        badge.className = `active-filter-badge ${badgeClass}`;

        const displayValue = this.formatFilterValue(type, value);
        const escapedValue = typeof escapeHtml === 'function' ? escapeHtml(displayValue) : displayValue;

        badge.innerHTML = `
            ${escapedValue}
            <button type="button" aria-label="Remove ${type} filter">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Add click handler to close button
        const closeBtn = badge.querySelector('button');
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (type === 'channel') {
                this.setChannel(null);
            } else if (type === 'account') {
                this.setAccount(null);
            } else if (type === 'status') {
                this.clearStatus();
            } else if (type === 'guest') {
                this.clearGuest();
            } else if (type === 'unread') {
                this.toggleUnread();
            } else if (type === 'search') {
                this.clearSearch();
            }
        });

        return badge;
    }

    /**
     * Format filter value for display
     * @param {string} type - 'channel', 'account', 'status', ...
     * @param {string} value - The raw filter value
     * @returns {string} Formatted display value
     */
    formatFilterValue(type, value) {
        if (type === 'channel') {
            return { booking: 'Booking.com', airbnb: 'Airbnb', direct: 'Direkt' }[value]
                || value.charAt(0).toUpperCase() + value.slice(1);
        } else if (type === 'account') {
            // Label comes from the button the server rendered for this account id
            const btn = document.querySelector(`[data-filter-account="${value}"]`);
            return btn ? btn.textContent.trim() : value;
        } else if (type === 'status') {
            if (value === 'escalated') return 'Eskaliert';
            if (value === 'pending_approval') return 'UMI-Freigabe';
            // Replace underscores with spaces, title case (pending_owner -> Pending Owner)
            return value
                .split('_')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                .join(' ');
        } else if (type === 'guest') {
            // Look up guest name from dropdown option text, strip count suffix
            const dropdown = document.getElementById('guestFilter');
            if (dropdown) {
                const option = dropdown.querySelector(`option[value="${value}"]`);
                if (option) {
                    // Remove count suffix like " (3)" from "John Smith (3)"
                    return option.textContent.replace(/\s*\(\d+\)$/, '');
                }
            }
            return `Guest ${value}`;
        } else if (type === 'unread') {
            return 'Ungelesen';
        } else if (type === 'search') {
            // Show truncated search query
            return value.length > 20 ? value.substring(0, 20) + '...' : value;
        }
        return value;
    }

    /**
     * Get current filter state (for external access)
     * @returns {Object} Current state object
     */
    getState() {
        return { ...this.state };
    }

    /**
     * Check if any filters are active
     * @returns {boolean} True if any filter is set
     */
    hasActiveFilters() {
        return !!(this.state.channel || this.state.account || this.state.status || this.state.guest || this.state.search || this.state.unread);
    }
}

// Create singleton and expose globally
const filterState = new FilterState();
// Don't auto-apply on construction - let inbox.html call when ready
