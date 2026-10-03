"use strict";

// Native details/summary remains keyboard-operable even without JavaScript.
document.querySelectorAll('[data-specifications]').forEach((disclosure) => {
    const summary = disclosure.querySelector('summary');
    const sync = () => summary.setAttribute('aria-expanded', String(disclosure.open));
    disclosure.addEventListener('toggle', sync);
    sync();
});

// Enhance Oscar's number input only. Its form owns quantity, options, CSRF,
// basket totals and stock validation; inventory counts are never sent to JS.
document.querySelectorAll('[data-detail-quantity]').forEach((control) => {
    const input = control.querySelector('input[type="number"]');
    if (!input) return;
    const buttons = [...control.querySelectorAll('[data-quantity-step]')];
    const sync = () => {
        const value = input.valueAsNumber;
        buttons.forEach((button) => {
            const decreasing = Number(button.dataset.quantityStep) < 0;
            button.disabled = input.disabled || input.readOnly || (Number.isFinite(value) &&
                (decreasing ? input.min !== '' && value <= Number(input.min)
                    : input.max !== '' && value >= Number(input.max)));
        });
    };
    buttons.forEach((button) => {
        button.hidden = false;
        button.addEventListener('click', () => {
            if (Number(button.dataset.quantityStep) < 0) input.stepDown();
            else input.stepUp();
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        });
    });
    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
    control.dataset.enhanced = '';
    sync();
});

document.querySelectorAll("[data-detail-gallery]").forEach((gallery) => {
    const image = gallery.querySelector("[data-gallery-image]");
    const fullSize = gallery.querySelector("[data-gallery-link]");
    const thumbnails = [...gallery.querySelectorAll("[data-gallery-thumbnail]")];
    const status = gallery.querySelector("[data-gallery-status]");
    const fallback = image.dataset.detailFallback;
    const useFallback = () => {
        if (image.getAttribute("src") === fallback) return;
        image.src = fallback;
        fullSize.href = fallback;
    };
    image.addEventListener("error", useFallback);
    if (image.complete && !image.naturalWidth) useFallback();

    const select = (thumbnail) => {
        image.src = thumbnail.href;
        image.alt = thumbnail.dataset.galleryAlt;
        fullSize.href = thumbnail.href;
        thumbnails.forEach((item) => {
            if (item === thumbnail) item.setAttribute("aria-current", "true");
            else item.removeAttribute("aria-current");
        });
        status.textContent = thumbnail.dataset.galleryStatusText;
    };
    thumbnails.forEach((thumbnail, index) => {
        thumbnail.addEventListener("click", (event) => {
            // Keep modified clicks and the no-JS links to the original image.
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            select(thumbnail);
        });
        thumbnail.addEventListener("keydown", (event) => {
            const targets = {ArrowRight: (index + 1) % thumbnails.length,
                ArrowLeft: (index - 1 + thumbnails.length) % thumbnails.length,
                Home: 0, End: thumbnails.length - 1};
            if (!(event.key in targets)) return;
            event.preventDefault();
            const next = thumbnails[targets[event.key]];
            select(next);
            next.focus();
        });
    });
});
