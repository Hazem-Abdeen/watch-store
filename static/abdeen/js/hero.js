"use strict";

document.querySelectorAll('[data-hero-carousel]').forEach(async (carousel) => {
    const slides = [...carousel.querySelectorAll('[data-hero-slide]')];
    if (slides.length < 2) return;
    const dots = [...carousel.querySelectorAll('[data-hero-dot]')];
    const rotation = carousel.querySelector('[data-hero-rotation]');
    const status = carousel.querySelector('[data-hero-status]');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const surface = carousel.querySelector('[data-hero-slides]');
    // Load responsive artwork before enabling navigation. All slides share grid
    // tracks, so changing to a different aspect ratio/copy length cannot reflow
    // the page. A failed image must not prevent the controls from becoming usable.
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
    let suppressClick = false;
    let rotationIntent = null;

    const schedule = () => {
        clearTimeout(timer);
        rotation.setAttribute('aria-label', paused ? 'Start rotation' : 'Pause rotation');
        rotation.dataset.paused = String(paused);
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
    // Remember the intended mouse/touch action before focusin pauses rotation.
    rotation.addEventListener('pointerdown', () => { rotationIntent = !paused; });
    rotation.addEventListener('pointercancel', () => { rotationIntent = null; });
    rotation.addEventListener('blur', () => { rotationIntent = null; });
    rotation.addEventListener('click', () => {
        paused = rotationIntent === null ? !paused : rotationIntent;
        rotationIntent = null;
        schedule();
    });
    // Keyboard focus stops rotation until explicitly restarted, so a focused
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
        suppressClick = false;
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
            suppressClick = true;
            show(index + (dx < 0 ? 1 : -1), true);
            setTimeout(() => { suppressClick = false; }, 0);
        } else schedule();
    });
    window.addEventListener('pointercancel', () => { gesture = null; touching = false; schedule(); });
    surface.addEventListener('click', (event) => {
        if (suppressClick) { event.preventDefault(); event.stopPropagation(); }
    }, true);
    document.addEventListener('visibilitychange', schedule);
    reducedMotion.addEventListener('change', () => {
        paused = true;
        rotation.hidden = reducedMotion.matches;
        schedule();
    });
    rotation.hidden = reducedMotion.matches;
    schedule();
});
