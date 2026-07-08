// ============================================================================
// Guided Tour — shared engine
// ============================================================================
// Generic step-by-step overlay tour. Each page provides its own steps by
// assigning GuidedTour.buildSteps = function () { ... } after this file loads.
// A step is { selector, titleKey, textKey, prepare?, spotlightParent? }.
// ============================================================================
const GuidedTour = {
    currentStep: -1,
    steps: [],
    overlay: null,
    tooltip: null,
    previousElement: null,

    /** Default: no steps. Pages override this (chat / inbox). */
    buildSteps() {
        return [];
    },

    start() {
        this.steps = this.buildSteps();
        if (!this.steps.length) return;

        // Close mobile menu first if open
        this._closeMobileMenu();

        // Create overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'tour-overlay';
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) this.end();
        });
        document.body.appendChild(this.overlay);

        // Create tooltip
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'tour-tooltip arrow-top';
        document.body.appendChild(this.tooltip);

        // Handle escape key
        this._escHandler = (e) => { if (e.key === 'Escape') this.end(); };
        document.addEventListener('keydown', this._escHandler);

        // Handle resize
        this._resizeHandler = () => {
            if (this.currentStep >= 0) this._positionTooltip();
        };
        window.addEventListener('resize', this._resizeHandler);

        this.currentStep = -1;
        this.next();
    },

    next() {
        this.currentStep++;
        if (this.currentStep >= this.steps.length) {
            this.end();
            return;
        }
        this._showStep();
    },

    prev() {
        if (this.currentStep <= 0) return;
        this.currentStep--;
        this._showStep();
    },

    end() {
        // Remove spotlight from current element
        if (this.previousElement) {
            this.previousElement.classList.remove('tour-spotlight');
            this.previousElement.style.position = '';
        }
        if (this.overlay) this.overlay.remove();
        if (this.tooltip) this.tooltip.remove();
        this.overlay = null;
        this.tooltip = null;
        this.previousElement = null;
        this.currentStep = -1;
        this._closeMobileMenu();
        document.removeEventListener('keydown', this._escHandler);
        window.removeEventListener('resize', this._resizeHandler);
    },

    _showStep() {
        const step = this.steps[this.currentStep];
        if (!step) return;

        // Run prepare function (e.g. open mobile menu)
        if (step.prepare) step.prepare();

        // Small delay to allow menu to open/DOM to settle
        setTimeout(() => {
            // Remove spotlight from previous element
            if (this.previousElement) {
                this.previousElement.classList.remove('tour-spotlight');
                this.previousElement.style.position = '';
            }

            let el = document.querySelector(step.selector);
            if (!el) {
                // Skip this step if element not found
                this.next();
                return;
            }

            // Optionally spotlight the parent container instead
            const spotlightEl = step.spotlightParent && el.closest('.overflow-menu-item') ? el.closest('.overflow-menu-item') : el;

            // Add spotlight to current element
            const computedPos = window.getComputedStyle(spotlightEl).position;
            if (computedPos === 'static') spotlightEl.style.position = 'relative';
            spotlightEl.classList.add('tour-spotlight');
            this.previousElement = spotlightEl;

            // Scroll element into view if needed
            el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            // Render tooltip content
            const t = (key) => typeof i18n !== 'undefined' ? i18n.t(key) : key;
            const total = this.steps.length;
            const cur = this.currentStep + 1;
            const isLast = this.currentStep === total - 1;
            const isFirst = this.currentStep === 0;

            this.tooltip.innerHTML = `
                <div class="tour-tooltip-title">
                    <i class="fas fa-info-circle"></i>
                    ${t(step.titleKey)}
                </div>
                <div class="tour-tooltip-text">${t(step.textKey)}</div>
                <div class="tour-tooltip-footer">
                    <span class="tour-step-counter">${cur} / ${total}</span>
                    <div class="tour-tooltip-actions">
                        <button class="tour-btn tour-btn-skip" onclick="GuidedTour.end()">${t('tour.skip')}</button>
                        ${!isFirst ? `<button class="tour-btn tour-btn-prev" onclick="GuidedTour.prev()"><i class="fas fa-chevron-left"></i></button>` : ''}
                        <button class="tour-btn tour-btn-next" onclick="${isLast ? 'GuidedTour.end()' : 'GuidedTour.next()'}">
                            ${isLast ? t('tour.done') : t('tour.next')}
                        </button>
                    </div>
                </div>
            `;

            this._positionTooltip();
        }, 80);
    },

    _positionTooltip() {
        const step = this.steps[this.currentStep];
        if (!step) return;
        const el = document.querySelector(step.selector);
        if (!el || !this.tooltip) return;

        const rect = el.getBoundingClientRect();
        const tipW = this.tooltip.offsetWidth;
        const tipH = this.tooltip.offsetHeight;
        const margin = 12;

        // Decide: show below or above the element
        const spaceBelow = window.innerHeight - rect.bottom;
        const showBelow = spaceBelow > tipH + margin + 10;

        let top, left;
        if (showBelow) {
            top = rect.bottom + margin;
            this.tooltip.className = 'tour-tooltip arrow-top';
        } else {
            top = rect.top - tipH - margin;
            this.tooltip.className = 'tour-tooltip arrow-bottom';
        }

        // Horizontal: align with element's left edge, but clamp to viewport
        left = rect.left;
        left = Math.max(12, Math.min(left, window.innerWidth - tipW - 12));

        // If there's not enough space vertically, center the tooltip
        if (top < 8) {
            top = 8;
            this.tooltip.className = 'tour-tooltip arrow-none';
        }
        if (top + tipH > window.innerHeight - 8) {
            top = window.innerHeight - tipH - 8;
            this.tooltip.className = 'tour-tooltip arrow-none';
        }

        // Position arrow relative to element center
        const arrowLeft = Math.max(16, Math.min(rect.left + rect.width / 2 - left, tipW - 16));

        this.tooltip.style.position = 'fixed';
        this.tooltip.style.zIndex = '10000';
        this.tooltip.style.top = top + 'px';
        this.tooltip.style.left = left + 'px';
        this.tooltip.style.setProperty('--tour-arrow-left', arrowLeft + 'px');
    },

    // Chat page only — no-op elsewhere (guarded on element existence).
    _openMobileMenu() {
        const menu = document.getElementById('mobileOverflowMenu');
        if (menu && !menu.classList.contains('open')) {
            menu.classList.add('open');
        }
        // Elevate menu above tour overlay so spotlighted items are visible
        if (menu) menu.style.zIndex = '9999';
    },

    _closeMobileMenu() {
        const menu = document.getElementById('mobileOverflowMenu');
        if (menu) {
            menu.classList.remove('open');
            menu.style.zIndex = '';
        }
    }
};

function startGuidedTour() {
    // Close the chat mobile overflow menu if present (the tour button lives
    // inside it on mobile). No-op on pages without that menu.
    const menu = document.getElementById('mobileOverflowMenu');
    if (menu) menu.classList.remove('open');

    // Small delay to let any menu close before measuring positions
    setTimeout(() => GuidedTour.start(), 100);
}
