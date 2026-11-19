"use strict";

document.querySelectorAll('[data-hero-carousel]').forEach(async (carousel) => {
    const slides = [...carousel.querySelectorAll('[data-hero-slide]')];
    const surface = carousel.querySelector('[data-hero-slides]');
    // Also guard single-slide banners. Keep suppression until the next pointer
    // gesture so delayed touch clicks cannot follow a swipe or scroll.
    let drag;
    let blockClick = false;
    surface.addEventListener('pointerdown', event => {
        if (!event.isPrimary) return;
        blockClick = false;
        drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
    });
    const trackDrag = event => {
        if (drag && drag.id === event.pointerId &&
            Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 10) blockClick = true;
    };
    window.addEventListener('pointermove', trackDrag);
    window.addEventListener('pointerup', event => { trackDrag(event); drag = null; });
    window.addEventListener('pointercancel', () => { if (drag) blockClick = true; drag = null; });
    surface.addEventListener('click', event => {
        if (blockClick && event.detail !== 0) {
            event.preventDefault();
            event.stopPropagation();
        }
    }, true);
    if (slides.length < 2) return;
    const dots = [...carousel.querySelectorAll('[data-hero-dot]')];
    const status = carousel.querySelector('[data-hero-status]');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    // Load responsive artwork before enabling navigation. The visible slide
    // determines the track heights. A failed image must not block the controls.
    carousel.classList.add('is-enhanced');
    slides.forEach((slide, number) => {
        slide.inert = number !== 0;
        slide.setAttribute('aria-hidden', String(number !== 0));
    });
    await Promise.allSettled(slides.map((slide) => {
        const image = slide.querySelector('img');
        image.loading = 'eager';
        return image.decode();
    }));
    let index = 0;
    let timer;
    let paused = reducedMotion.matches || carousel.contains(document.activeElement);
    let hovering = window.matchMedia('(hover: hover)').matches && carousel.matches(':hover');
    let touching = false;
    let gesture;

    const schedule = () => {
        clearTimeout(timer);
        if (!paused && !hovering && !touching && !document.hidden && !reducedMotion.matches) {
            timer = setTimeout(() => show(index + 1), 6000);
        }
    };
    const show = (next, manual = false) => {
        index = (next + slides.length) % slides.length;
        if (manual && surface.contains(document.activeElement)) dots[index].focus();
        slides.forEach((slide, number) => {
            slide.hidden = number !== index;
            slide.inert = number !== index;
            slide.setAttribute('aria-hidden', String(number !== index));
        });
        dots.forEach((dot, number) => dot.setAttribute('aria-current', String(number === index)));
        if (manual) {
            paused = true;
            status.textContent = `Campaign ${index + 1} of ${slides.length}`;
        }
        schedule();
    };
    carousel.querySelector('[data-hero-controls]').hidden = false;
    carousel.querySelector('[data-hero-previous]').addEventListener('click', () => show(index - 1, true));
    carousel.querySelector('[data-hero-next]').addEventListener('click', () => show(index + 1, true));
    dots.forEach((dot, number) => dot.addEventListener('click', () => show(number, true)));
    // Keyboard focus stops rotation for this visit, so a focused
    // link is never hidden by a timer while someone is reading the campaign.
    carousel.addEventListener('focusin', () => { paused = true; schedule(); });
    carousel.addEventListener('keydown', (event) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? slides.length - 1 : index + (event.key === 'ArrowLeft' ? -1 : 1);
        show(next, true);
    });
    carousel.addEventListener('pointerenter', (event) => {
        if (event.pointerType !== 'mouse') return;
        hovering = true;
        schedule();
    });
    carousel.addEventListener('pointerleave', (event) => {
        if (event.pointerType !== 'mouse') return;
        hovering = false;
        schedule();
    });
    surface.addEventListener('pointerdown', (event) => {
        if (!event.isPrimary || event.pointerType === 'mouse') return;
        gesture = {id: event.pointerId, x: event.clientX, y: event.clientY};
        touching = true;
        paused = true;
        schedule();
    });
    window.addEventListener('pointerup', (event) => {
        if (!gesture || gesture.id !== event.pointerId) return;
        const dx = event.clientX - gesture.x;
        const dy = event.clientY - gesture.y;
        gesture = null;
        touching = false;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
            show(index + (dx < 0 ? 1 : -1), true);
        } else schedule();
    });
    window.addEventListener('pointercancel', () => { gesture = null; touching = false; schedule(); });
    document.addEventListener('visibilitychange', schedule);
    reducedMotion.addEventListener('change', () => {
        paused = true;
        schedule();
    });
    schedule();
});
