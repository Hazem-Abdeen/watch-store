"use strict";

// Also cover storage URLs that fail after the HTML was rendered.
document.querySelectorAll("[data-image-fallback]").forEach((image) => {
    const useFallback = () => {
        const fallback = image.dataset.imageFallback;
        if (!fallback) return;
        delete image.dataset.imageFallback;
        image.src = fallback;
        image.alt = "Image coming soon";
    };
    image.addEventListener("error", useFallback, {once: true});
    if (image.complete && image.naturalWidth === 0) useFallback();
});

// Keep the editorial composition and real link when campaign files are absent.
document.querySelectorAll('[data-category-image]').forEach((image) => {
    const showFallback = () => { image.hidden = true; };
    image.addEventListener('error', showFallback, {once: true});
    if (image.complete && image.naturalWidth === 0) showFallback();
});

// Native details keep navigation/search usable without JavaScript.
// Enhancement: one panel at a time, Escape/outside-click dismissal, focus return.
const header = document.querySelector('[data-home-header]');
if (header) {
    header.querySelectorAll('details').forEach((details) => {
        const summary = details.querySelector(':scope > summary');
        const sync = () => summary.setAttribute('aria-expanded', String(details.open));
        sync();
        details.addEventListener('toggle', sync);
    });
    header.querySelectorAll('[data-brands-menu]').forEach((menu) => {
        document.addEventListener('click', (event) => {
            if (!menu.contains(event.target)) menu.open = false;
        });
        menu.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            const target = event.target.closest('details[open]');
            if (!target || !menu.contains(target)) return;
            target.open = false;
            target.querySelector(':scope > summary').focus();
            event.stopPropagation();
        });
        menu.addEventListener('focusout', () => {
            requestAnimationFrame(() => {
                if (!menu.contains(document.activeElement)) menu.open = false;
            });
        });
    });
    const panels = [...header.querySelectorAll('[data-header-panel]')];
    const closePanels = (restoreFocus = false) => {
        panels.forEach((panel) => {
            if (!panel.open) return;
            panel.open = false;
            if (restoreFocus) panel.querySelector('summary').focus();
        });
    };
    panels.forEach((panel) => {
        panel.addEventListener('toggle', () => {
            if (!panel.open) return;
            panels.forEach((other) => { if (other !== panel) other.open = false; });
            if (panel.classList.contains('abdeen-search')) panel.querySelector('input').focus();
        });
        panel.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => closePanels(true));
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closePanels(true);
    });
    document.addEventListener('click', (event) => {
        if (!header.contains(event.target)) closePanels();
    });
    header.addEventListener('focusout', () => {
        requestAnimationFrame(() => {
            if (!header.contains(document.activeElement)) closePanels();
        });
    });
    window.matchMedia('(min-width: 1024px)').addEventListener('change', () => closePanels());
}

// A deleted media file or failed storage request should still leave a useful card.
document.querySelectorAll('[data-brand-logo-image]').forEach((image) => {
    const fallback = image.closest('[data-brand-logo]').querySelector('[data-brand-logo-fallback]');
    const showName = () => { image.hidden = true; fallback.hidden = false; };
    image.addEventListener('error', showName, {once: true});
    if (image.complete && image.naturalWidth === 0) showName();
});
