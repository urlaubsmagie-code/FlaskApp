/**
 * PollingManager - Reusable polling infrastructure with visibility detection
 *
 * Handles polling lifecycle, automatic pause on tab hidden, resume on tab visible,
 * and request cancellation via AbortController.
 */

class PollingManager {
    /**
     * Create a new PollingManager instance
     * @param {Object} options - Configuration options
     * @param {Function} options.fetchFn - Async function that receives AbortController signal, returns data
     * @param {Function} options.onUpdate - Callback invoked with data when fetch succeeds
     * @param {number} [options.interval=15000] - Polling interval in milliseconds
     * @param {Function} [options.onError] - Optional error callback (default logs to console)
     */
    constructor({ fetchFn, onUpdate, interval = 15000, onError = null }) {
        if (typeof fetchFn !== 'function') {
            throw new Error('PollingManager: fetchFn is required and must be a function');
        }
        if (typeof onUpdate !== 'function') {
            throw new Error('PollingManager: onUpdate is required and must be a function');
        }

        this.fetchFn = fetchFn;
        this.onUpdate = onUpdate;
        this.interval = interval;
        this.onError = onError || ((err) => console.error('PollingManager error:', err));

        // Instance state
        this.timeoutId = null;
        this.abortController = null;
        this.isPolling = false;

        // Bind visibility handler to preserve `this` context
        this._onVisibilityChange = this._onVisibilityChange.bind(this);
    }

    /**
     * Start polling
     * Idempotent - no-op if already polling
     */
    start() {
        if (this.isPolling) {
            return;
        }

        this.isPolling = true;

        // Add visibility change listener
        document.addEventListener('visibilitychange', this._onVisibilityChange);

        // Poll immediately (no initial delay)
        this._poll();
    }

    /**
     * Stop polling completely
     */
    stop() {
        this.isPolling = false;

        // Remove visibility listener
        document.removeEventListener('visibilitychange', this._onVisibilityChange);

        // Cancel pending timeout and in-flight request
        this._cancelPending();
    }

    /**
     * Internal: Execute one poll cycle
     * @private
     */
    async _poll() {
        // Guard: Don't poll if stopped or tab is hidden
        if (!this.isPolling || document.visibilityState === 'hidden') {
            return;
        }

        // Abort any existing request (they can only abort once)
        if (this.abortController) {
            this.abortController.abort();
        }

        // Create new AbortController for this request
        this.abortController = new AbortController();
        const signal = this.abortController.signal;

        try {
            const data = await this.fetchFn(signal);

            // Guard: Check if still polling after async operation
            if (this.isPolling) {
                this.onUpdate(data);
                this._scheduleNext();
            }
        } catch (error) {
            // Ignore AbortError - expected when cancelling
            if (error.name === 'AbortError') {
                return;
            }

            // Call error handler if still polling
            if (this.isPolling) {
                this.onError(error);
                this._scheduleNext();
            }
        }
    }

    /**
     * Internal: Schedule next poll
     * @private
     */
    _scheduleNext() {
        // Clear any existing timeout first
        this._cancelPending();

        // Schedule next poll using recursive setTimeout (NOT setInterval)
        // This prevents call stacking if fetches take longer than interval
        this.timeoutId = setTimeout(() => this._poll(), this.interval);
    }

    /**
     * Internal: Cancel pending timeout and in-flight request
     * @private
     */
    _cancelPending() {
        // Clear scheduled timeout
        if (this.timeoutId !== null) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }

        // Abort in-flight request
        if (this.abortController !== null) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    /**
     * Internal: Handle visibility change events
     * @private
     */
    _onVisibilityChange() {
        if (document.visibilityState === 'visible') {
            // Tab became visible - poll immediately
            this._poll();
        } else {
            // Tab became hidden - cancel pending operations
            this._cancelPending();
        }
    }
}
