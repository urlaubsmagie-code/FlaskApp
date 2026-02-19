/**
 * FilterState - Centralized filter state management with URL synchronization
 *
 * Manages platform and status filters for the inbox, persisting state in URL
 * for bookmarking and browser navigation support.
 */

class FilterState {
    constructor() {
        this.state = {
            platform: null,  // null = all, or 'email'|'whatsapp'|'airbnb'|'booking'
            status: null,    // null = all, or 'active'|'pending_owner'|'closed'
            guest: null,     // null = all, or guest ID string
            search: null     // null = no search, or query string
        };

        // Load initial state from URL
        this.loadFromURL();

        // Handle browser back/forward navigation
        window.addEventListener('popstate', () => {
            this.loadFromURL();
            this.applyFilters();
            this.updateUI();
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
        this.state.platform = params.get('platform') || null;
        this.state.status = params.get('status') || null;
        this.state.guest = params.get('guest') || null;
        this.state.search = params.get('q') || null;
    }

    /**
     * Save current filter state to URL using history.replaceState
     * Uses replaceState to avoid cluttering browser history
     */
    saveToURL() {
        const url = new URL(window.location.href);

        // Set or delete platform param
        if (this.state.platform) {
            url.searchParams.set('platform', this.state.platform);
        } else {
            url.searchParams.delete('platform');
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

        // Update URL without creating history entry
        history.replaceState(null, '', url.toString());
    }

    /**
     * Set platform filter
     * @param {string|null} platform - Platform to filter by, or null for all
     */
    setPlatform(platform) {
        this.state.platform = platform || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    /**
     * Set status filter
     * @param {string|null} status - Status to filter by, or null for all
     */
    setStatus(status) {
        this.state.status = status || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
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
     * Set search query
     * @param {string|null} query - Search query, or null to clear
     */
    setSearch(query) {
        this.state.search = query || null;
        this.saveToURL();
        // Don't call applyFilters - search handler does server fetch
    }

    /**
     * Clear search (shorthand)
     */
    clearSearch() {
        this.setSearch(null);
    }

    /**
     * Reset all filters to default (no filtering)
     */
    reset() {
        this.state.platform = null;
        this.state.status = null;
        this.state.guest = null;
        this.state.search = null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    /**
     * Clear platform filter (shorthand)
     */
    clearPlatform() {
        this.setPlatform(null);
    }

    /**
     * Clear status filter (shorthand)
     */
    clearStatus() {
        this.setStatus(null);
    }

    /**
     * Apply current filters to conversation cards
     * Combines platform, status, and search filters
     */
    applyFilters() {
        const cards = document.querySelectorAll('.conversation-card');
        const searchInput = document.getElementById('searchInput');
        const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';

        cards.forEach(card => {
            const matchesPlatform = !this.state.platform || card.dataset.platform === this.state.platform;
            const matchesStatus = !this.state.status || card.dataset.status === this.state.status;
            const matchesGuest = !this.state.guest || card.dataset.guestId === this.state.guest;
            const matchesSearch = !searchTerm || card.textContent.toLowerCase().includes(searchTerm);

            card.style.display = (matchesPlatform && matchesStatus && matchesGuest && matchesSearch) ? 'flex' : 'none';
        });
    }

    /**
     * Update UI elements to reflect current filter state
     * - Toggle active class on filter buttons
     * - Update active filter indicators
     */
    updateUI() {
        // Update platform filter buttons
        document.querySelectorAll('[data-filter-platform]').forEach(btn => {
            const filterValue = btn.dataset.filterPlatform;
            const isActive = (filterValue === '' && !this.state.platform) ||
                            (filterValue === this.state.platform);
            btn.classList.toggle('active', isActive);
        });

        // Update status filter buttons
        document.querySelectorAll('[data-filter-status]').forEach(btn => {
            const filterValue = btn.dataset.filterStatus;
            const isActive = (filterValue === '' && !this.state.status) ||
                            (filterValue === this.state.status);
            btn.classList.toggle('active', isActive);
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

        // Add platform badge if filtered
        if (this.state.platform) {
            container.appendChild(this.createFilterBadge('platform', this.state.platform));
        }

        // Add status badge if filtered
        if (this.state.status) {
            container.appendChild(this.createFilterBadge('status', this.state.status));
        }

        // Add guest badge if filtered
        if (this.state.guest) {
            container.appendChild(this.createFilterBadge('guest', this.state.guest));
        }

        // Add search badge if searching
        if (this.state.search) {
            container.appendChild(this.createFilterBadge('search', this.state.search));
        }

        // Show/hide clear all button
        const hasActiveFilters = this.state.platform || this.state.status || this.state.guest || this.state.search;
        if (clearBtn) {
            clearBtn.style.display = hasActiveFilters ? 'inline-flex' : 'none';
        }
    }

    /**
     * Create a filter badge element
     * @param {string} type - 'platform' or 'status'
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
            if (type === 'platform') {
                this.clearPlatform();
            } else if (type === 'status') {
                this.clearStatus();
            } else if (type === 'guest') {
                this.clearGuest();
            } else if (type === 'search') {
                this.clearSearch();
                const searchInput = document.getElementById('searchInput');
                if (searchInput) searchInput.value = '';
            }
        });

        return badge;
    }

    /**
     * Format filter value for display
     * @param {string} type - 'platform' or 'status'
     * @param {string} value - The raw filter value
     * @returns {string} Formatted display value
     */
    formatFilterValue(type, value) {
        if (type === 'platform') {
            // Capitalize first letter (email -> Email)
            return value.charAt(0).toUpperCase() + value.slice(1);
        } else if (type === 'status') {
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
        return !!(this.state.platform || this.state.status || this.state.guest || this.state.search);
    }
}

// Create singleton and expose globally
const filterState = new FilterState();
// Don't auto-apply on construction - let inbox.html call when ready
