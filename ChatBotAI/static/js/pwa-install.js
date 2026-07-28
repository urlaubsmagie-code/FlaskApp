// UMI-Chat install prompt. Android/Chromium: use the native beforeinstallprompt.
// iOS Safari: no such event, so show a one-line "Add to Home Screen" hint. Hidden
// entirely when already running installed (standalone).
(function () {
    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches
            || window.navigator.standalone === true;
    }
    function isIOS() {
        return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    }
    if (isStandalone()) return;  // already installed — nothing to show

    var DISMISS_KEY = 'umi_install_hint_dismissed';

    function banner(innerHtml) {
        var el = document.createElement('div');
        el.id = 'umiInstallBanner';
        el.style.cssText =
            'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;'
            + 'background:#7B2332;color:#fff;padding:12px 14px;border-radius:10px;'
            + 'box-shadow:0 4px 16px rgba(0,0,0,.3);display:flex;align-items:center;'
            + 'gap:10px;font-size:0.95rem;max-width:520px;margin:0 auto;';
        el.innerHTML = innerHtml;
        document.body.appendChild(el);
        return el;
    }
    function closeBtn(el) {
        var b = document.createElement('button');
        b.innerHTML = '&times;';
        b.setAttribute('aria-label', 'Schließen');
        b.style.cssText = 'margin-left:auto;background:transparent;border:0;color:#fff;'
            + 'font-size:1.4rem;line-height:1;cursor:pointer;padding:0 4px;';
        b.onclick = function () {
            try { localStorage.setItem(DISMISS_KEY, '1'); } catch (e) {}
            el.remove();
        };
        el.appendChild(b);
    }

    // Android / Chromium: capture the native prompt and offer a button.
    var deferred = null;
    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferred = e;
        var el = banner('<i class="fas fa-download"></i>'
            + '<span>UMI-Chat als App installieren</span>'
            + '<button id="umiInstallBtn" style="background:#fff;color:#7B2332;'
            + 'border:0;border-radius:6px;padding:6px 12px;font-weight:600;cursor:pointer;">'
            + 'Installieren</button>');
        closeBtn(el);
        document.getElementById('umiInstallBtn').onclick = function () {
            el.remove();
            if (deferred) { deferred.prompt(); deferred = null; }
        };
    });

    // iOS Safari: no beforeinstallprompt — show a hint once (dismissible).
    document.addEventListener('DOMContentLoaded', function () {
        if (!isIOS()) return;
        try { if (localStorage.getItem(DISMISS_KEY)) return; } catch (e) {}
        var el = banner('<i class="fas fa-arrow-up-from-bracket"></i>'
            + '<span>UMI-Chat installieren: Teilen-Symbol antippen, '
            + 'dann „Zum Home-Bildschirm".</span>');
        closeBtn(el);
    });
})();
