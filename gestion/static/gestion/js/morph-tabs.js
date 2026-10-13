/* ═══════════════════════════════════════════════════════════════════
   Morphing Tabs — port de beui.dev/components/blocks/morphing-tabs
   La pestaña activa se funde con el panel en una sola forma "líquida"
   (un <path> SVG) que se desliza con resorte al cambiar de pestaña.
   Sin cerrar ni reordenar pestañas: solo el despliegue y la visualización.

   Uso:
     MorphTabs(rootEl, { onChange: function (id) { ... } });
   Marcado esperado:
     <section data-morph-tabs>
       <div class="morph-rail" role="tablist">
         <button class="morph-tab" role="tab" data-tab="id">…</button> …
       </div>
       <div class="morph-panel" role="tabpanel">
         <div data-morph-content>…</div>
       </div>
     </section>
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    // Geometría idéntica a beUI
    var MAX_TAB_WIDTH = 176;
    var MIN_TAB_WIDTH = 96;
    var COMPACT_BELOW = 110;
    var TAB_HEIGHT = 56;
    var RAIL_HEIGHT = 80;
    var SURFACE_INSET = 16;
    var LIQUID_JOIN = 24;
    var PANEL_RADIUS = 28;
    var TAB_RADIUS = 24;
    var TAB_GAP = 12;

    // SPRING_GLIDE de beUI
    var STIFFNESS = 700;
    var DAMPING = 50;
    var MASS = 0.5;

    var EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)';
    var SVG_NS = 'http://www.w3.org/2000/svg';

    function liquidTabPath(tabLeft, surfaceWidth, tabWidth) {
        var panelLeft = SURFACE_INSET;
        var panelRight = surfaceWidth - SURFACE_INSET;
        var left = Math.max(panelLeft, Math.min(panelRight - tabWidth, tabLeft));
        var right = left + tabWidth;
        var top = RAIL_HEIGHT - TAB_HEIGHT;
        var bottom = RAIL_HEIGHT;
        var leftJoin = Math.max(panelLeft, left - LIQUID_JOIN);
        var rightJoin = Math.min(panelRight, right + LIQUID_JOIN);
        var leftDepth = Math.min(LIQUID_JOIN, left - leftJoin);
        var rightDepth = Math.min(LIQUID_JOIN, rightJoin - right);
        var leftControl = leftDepth * 0.55;
        var rightControl = rightDepth * 0.55;
        var leftPanelRadius = Math.min(PANEL_RADIUS, leftJoin - panelLeft);
        var rightPanelRadius = Math.min(PANEL_RADIUS, panelRight - rightJoin);

        return [
            'M' + panelLeft + ' ' + (bottom + PANEL_RADIUS),
            'V' + (bottom + leftPanelRadius),
            'Q' + panelLeft + ' ' + bottom + ' ' + (panelLeft + leftPanelRadius) + ' ' + bottom,
            'H' + leftJoin,
            'C' + (leftJoin + leftControl) + ' ' + bottom + ' ' + left + ' ' + (bottom - leftDepth + leftControl) + ' ' + left + ' ' + (bottom - leftDepth),
            'V' + (top + TAB_RADIUS),
            'Q' + left + ' ' + top + ' ' + (left + TAB_RADIUS) + ' ' + top,
            'H' + (right - TAB_RADIUS),
            'Q' + right + ' ' + top + ' ' + right + ' ' + (top + TAB_RADIUS),
            'V' + (bottom - rightDepth),
            'C' + right + ' ' + (bottom - rightDepth + rightControl) + ' ' + (rightJoin - rightControl) + ' ' + bottom + ' ' + rightJoin + ' ' + bottom,
            'H' + (panelRight - rightPanelRadius),
            'Q' + panelRight + ' ' + bottom + ' ' + panelRight + ' ' + (bottom + rightPanelRadius),
            'V' + (bottom + PANEL_RADIUS),
            'Z'
        ].join(' ');
    }

    function MorphTabs(root, options) {
        options = options || {};
        var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var rail = root.querySelector('.morph-rail');
        var tabs = Array.prototype.slice.call(root.querySelectorAll('.morph-tab'));
        var content = root.querySelector('[data-morph-content]');
        if (!rail || !tabs.length) return null;

        // Superficie líquida
        var svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('class', 'morph-surface');
        var path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('fill', 'currentColor');
        svg.appendChild(path);
        root.insertBefore(svg, root.firstChild);

        var width = 0, tabWidth = MAX_TAB_WIDTH, slotGap = TAB_GAP, slots = [];
        var activeIndex = Math.max(0, tabs.findIndex(function (t) { return t.getAttribute('aria-selected') === 'true'; }));
        var spring = { x: SURFACE_INSET, v: 0, target: SURFACE_INSET, raf: 0, last: 0 };

        function draw() {
            if (width > SURFACE_INSET * 2) path.setAttribute('d', liquidTabPath(spring.x, width, tabWidth));
        }

        function step(now) {
            var dt = Math.min(0.064, (now - spring.last) / 1000 || 0.016);
            spring.last = now;
            // Integración en sub-pasos para que el resorte rígido sea estable
            var n = Math.ceil(dt / 0.004);
            var h = dt / n;
            for (var i = 0; i < n; i++) {
                var force = -STIFFNESS * (spring.x - spring.target) - DAMPING * spring.v;
                spring.v += (force / MASS) * h;
                spring.x += spring.v * h;
            }
            if (Math.abs(spring.x - spring.target) < 0.5 && Math.abs(spring.v) < 10) {
                spring.x = spring.target;
                spring.v = 0;
                spring.raf = 0;
                draw();
                return;
            }
            draw();
            spring.raf = requestAnimationFrame(step);
        }

        function glideTo(x, instant) {
            spring.target = x;
            if (instant || reduce) {
                cancelAnimationFrame(spring.raf);
                spring.raf = 0;
                spring.x = x;
                spring.v = 0;
                draw();
                return;
            }
            if (!spring.raf) {
                spring.last = performance.now();
                spring.raf = requestAnimationFrame(step);
            }
        }

        // Reparto del ancho en tres niveles, igual que beUI
        function layout(instant) {
            width = root.clientWidth;
            var count = tabs.length;
            var inner = width - SURFACE_INSET * 2;
            var widthAt = function (gap) { return Math.floor((inner - gap * (count - 1)) / count); };
            if (widthAt(TAB_GAP) >= MIN_TAB_WIDTH) {
                tabWidth = Math.min(MAX_TAB_WIDTH, widthAt(TAB_GAP));
                slotGap = TAB_GAP;
            } else if (count > 1 && widthAt(0) >= MIN_TAB_WIDTH) {
                tabWidth = MIN_TAB_WIDTH;
                slotGap = Math.max(0, Math.floor((inner - MIN_TAB_WIDTH * count) / (count - 1)));
            } else {
                tabWidth = Math.max(0, widthAt(0));
                slotGap = 0;
            }
            slots = tabs.map(function (_, i) { return SURFACE_INSET + i * (tabWidth + slotGap); });
            root.classList.toggle('is-compact', tabWidth < COMPACT_BELOW);
            svg.setAttribute('viewBox', '0 0 ' + width + ' ' + (RAIL_HEIGHT + PANEL_RADIUS));
            tabs.forEach(function (tab, i) {
                tab.style.width = tabWidth + 'px';
                tab.style.transform = 'translate3d(' + slots[i] + 'px, 0, 0)';
            });
            glideTo(slots[activeIndex], instant);
            if (instant) draw();
        }

        // Cambio de contenido: sale (120ms) → onChange → entra con resorte
        var swapToken = 0;
        function swapContent(id) {
            var token = ++swapToken;
            if (!content || !content.animate) {
                if (options.onChange) options.onChange(id);
                return;
            }
            var out = reduce
                ? [{ opacity: 1 }, { opacity: 0 }]
                : [{ opacity: 1, transform: 'none', filter: 'blur(0px)' }, { opacity: 0, transform: 'translateY(-5px)', filter: 'blur(5px)' }];
            var exit = content.animate(out, { duration: reduce ? 80 : 120, easing: EASE_OUT, fill: 'forwards' });
            exit.finished.then(function () {
                if (token !== swapToken) return;
                if (options.onChange) options.onChange(id);
                var into = reduce
                    ? [{ opacity: 0 }, { opacity: 1 }]
                    : [{ opacity: 0, transform: 'translateY(8px)', filter: 'blur(6px)' }, { opacity: 1, transform: 'none', filter: 'blur(0px)' }];
                var enter = content.animate(into, { duration: reduce ? 120 : 320, easing: EASE_OUT, fill: 'forwards' });
                exit.cancel();
                enter.finished.then(function () { if (token === swapToken) enter.cancel(); });
            }).catch(function () {});
        }

        function select(index, focus) {
            if (index < 0 || index >= tabs.length || tabs[index].disabled) return;
            var changed = index !== activeIndex;
            activeIndex = index;
            tabs.forEach(function (tab, i) {
                var on = i === index;
                tab.classList.toggle('is-active', on);
                tab.setAttribute('aria-selected', on ? 'true' : 'false');
                tab.tabIndex = on ? 0 : -1;
            });
            if (focus) tabs[index].focus();
            glideTo(slots[index]);
            if (changed) swapContent(tabs[index].getAttribute('data-tab'));
        }

        tabs.forEach(function (tab, i) {
            tab.addEventListener('click', function () { select(i, false); });
            tab.addEventListener('keydown', function (e) {
                var next = null;
                if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
                else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = tabs.length - 1;
                if (next === null) return;
                e.preventDefault();
                select(next, true);
            });
        });

        tabs.forEach(function (tab, i) {
            var on = i === activeIndex;
            tab.classList.toggle('is-active', on);
            tab.setAttribute('aria-selected', on ? 'true' : 'false');
            tab.tabIndex = on ? 0 : -1;
        });

        layout(true);
        root.classList.add('is-ready');
        if (window.ResizeObserver) {
            new ResizeObserver(function () {
                if (root.clientWidth !== width) layout(false);
            }).observe(root);
        }

        return {
            select: function (id) {
                var i = tabs.findIndex(function (t) { return t.getAttribute('data-tab') === id; });
                select(i, false);
            }
        };
    }

    window.MorphTabs = MorphTabs;
})();
