/* ═══════════════════════════════════════════════════════════════════
   ACRYLITEC — Movimiento de la interfaz
   - Entradas escalonadas de los bloques de cada página
   - Contadores en los KPI
   - Avisos (toasts) para mensajes de Django y del POS
   - Menú lateral en móvil
   Todo se desactiva con prefers-reduced-motion.
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ── Entradas escalonadas ───────────────────────────────────────
    function revealPage() {
        var page = document.querySelector('.page');
        if (!page || reduce) return;

        var blocks = '.page-header, .section-header, .dashboard-kpis > *, .kpi-grid > *, .stat-strip, ' +
            '.dashboard-toolbar, .card, .table-responsive, .action-card, .product-card, .empty-state, ' +
            '.page > .alert, .section > .alert, .ticket, .morph-tabs, [data-reveal]';
        var i = 0;
        page.querySelectorAll(blocks).forEach(function (el) {
            if (el.closest('.modal')) return;
            var parent = el.parentElement;
            // Solo el bloque exterior: los anidados entran con su contenedor
            if (parent && parent.closest('.card, .table-responsive, .product-card, .ticket, .action-card, .morph-tabs')) return;
            el.classList.add('rv');
            el.style.setProperty('--i', Math.min(i++, 14));
        });

        page.querySelectorAll('.table tbody').forEach(function (tbody) {
            var rows = tbody.querySelectorAll(':scope > tr');
            rows.forEach(function (tr, k) {
                if (k > 24) return;
                tr.classList.add('rv-row');
                tr.style.setProperty('--i', k);
            });
        });
    }

    // ── Contadores ─────────────────────────────────────────────────
    function countUp(el) {
        var raw = (el.textContent || '').trim();
        var m = raw.match(/^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/);
        if (!m) return;
        var prefix = m[1], numStr = m[2], suffix = m[3];
        var target = parseFloat(numStr.replace(/,/g, ''));
        if (!isFinite(target) || target === 0) return;
        var decimals = (numStr.split('.')[1] || '').length;
        var fmt = function (v) {
            return prefix + v.toLocaleString('es-MX', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix;
        };
        if (reduce) { el.textContent = fmt(target); return; }

        var duration = 1100;
        var start = null;
        var delay = 120;
        el.textContent = fmt(0);
        function tick(t) {
            if (start === null) start = t + delay;
            var p = Math.max(0, Math.min(1, (t - start) / duration));
            var e = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
            el.textContent = fmt(target * e);
            if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    function runCounters() {
        document.querySelectorAll('.kpi-value, [data-countup]').forEach(countUp);
    }

    // ── Toasts ─────────────────────────────────────────────────────
    var ICONS = { success: 'bi-check-lg', error: 'bi-x-lg', danger: 'bi-x-lg', warning: 'bi-exclamation-lg', info: 'bi-info-lg' };

    function stack() {
        var s = document.getElementById('toastStack');
        if (!s) {
            s = document.createElement('div');
            s.id = 'toastStack';
            s.className = 'toast-stack';
            s.setAttribute('aria-live', 'polite');
            document.body.appendChild(s);
        }
        return s;
    }

    function dismiss(toast) {
        if (!toast || toast.classList.contains('is-leaving')) return;
        toast.classList.add('is-leaving');
        setTimeout(function () { toast.remove(); }, reduce ? 0 : 200);
    }

    function arm(toast) {
        var close = toast.querySelector('.toast-close');
        if (close) close.addEventListener('click', function () { dismiss(toast); });
        var ms = parseInt(toast.getAttribute('data-timeout') || '4200', 10);
        setTimeout(function () { dismiss(toast); }, ms);
    }

    window.acryToast = function (message, type) {
        type = type || 'success';
        var toast = document.createElement('div');
        toast.className = 'toast-item toast-' + type;
        toast.setAttribute('role', 'status');
        var icon = document.createElement('span');
        icon.className = 'toast-icon';
        icon.innerHTML = '<i class="bi ' + (ICONS[type] || ICONS.info) + '"></i>';
        var text = document.createElement('span');
        text.textContent = message;
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'toast-close';
        close.setAttribute('aria-label', 'Cerrar aviso');
        close.innerHTML = '<i class="bi bi-x"></i>';
        toast.appendChild(icon);
        toast.appendChild(text);
        toast.appendChild(close);
        stack().appendChild(toast);
        arm(toast);
        return toast;
    };

    // ── Dock: hoja "Más" (móvil) ───────────────────────────────────
    function sheetEls() {
        return {
            sheet: document.getElementById('dockSheet'),
            more: document.getElementById('dockMore'),
            backdrop: document.getElementById('dockBackdrop')
        };
    }

    window.toggleSheet = function (force) {
        var el = sheetEls();
        if (!el.sheet) return;
        var open = typeof force === 'boolean' ? force : !document.body.classList.contains('sheet-open');
        el.sheet.style.transform = '';
        document.body.classList.toggle('sheet-open', open);
        if (el.more) el.more.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
            setTimeout(function () { el.sheet.focus({ preventScroll: true }); }, 60);
        } else if (el.more && el.sheet.contains(document.activeElement)) {
            el.more.focus({ preventScroll: true });
        }
    };

    function wireSheet() {
        var el = sheetEls();
        if (!el.sheet) return;
        if (el.more) el.more.addEventListener('click', function () { window.toggleSheet(); });
        if (el.backdrop) el.backdrop.addEventListener('click', function () { window.toggleSheet(false); });
        el.sheet.querySelectorAll('a').forEach(function (a) {
            a.addEventListener('click', function () { window.toggleSheet(false); });
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && document.body.classList.contains('sheet-open')) window.toggleSheet(false);
        });

        // Arrastrar hacia abajo para cerrar
        var startY = 0, lastY = 0, lastT = 0, vel = 0, dragging = false;
        el.sheet.addEventListener('touchstart', function (e) {
            if (!document.body.classList.contains('sheet-open')) return;
            dragging = true;
            startY = lastY = e.touches[0].clientY;
            lastT = Date.now();
            vel = 0;
            el.sheet.classList.add('is-dragging');
        }, { passive: true });
        el.sheet.addEventListener('touchmove', function (e) {
            if (!dragging) return;
            var y = e.touches[0].clientY;
            var dy = Math.max(0, y - startY);
            el.sheet.style.transform = 'translateY(' + dy + 'px)';
            var now = Date.now();
            if (now > lastT) vel = (y - lastY) / (now - lastT);
            lastT = now;
            lastY = y;
        }, { passive: true });
        function endDrag(e) {
            if (!dragging) return;
            dragging = false;
            el.sheet.classList.remove('is-dragging');
            var endY = (e.changedTouches && e.changedTouches[0]) ? e.changedTouches[0].clientY : lastY;
            var dy = endY - startY;
            var fast = vel > 0.5;
            if (dy > 80 || (dy > 24 && fast)) {
                window.toggleSheet(false);
            } else {
                el.sheet.style.transform = '';
            }
        }
        el.sheet.addEventListener('touchend', endDrag);
        el.sheet.addEventListener('touchcancel', endDrag);
    }

    function init() {
        revealPage();
        runCounters();
        wireSheet();
        document.querySelectorAll('.toast-stack .toast-item').forEach(arm);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
