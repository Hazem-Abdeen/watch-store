"use strict";

// Presentation after Oscar replaces its basket partial; no cart state or totals.
(() => {
    const page = document.querySelector('.abdeen-basket');
    const content = page?.querySelector('#content_inner');
    if (!content || !window.oscar?.basket) return;
    page.classList.add('is-enhanced');

    const refreshPresentation = (announce = false) => {
        const selection = content.querySelector('[data-basket-count]');
        const bag = document.querySelector('.abdeen-bag-link');
        if (selection && bag) {
            bag.querySelector('.abdeen-bag-count').textContent = selection.dataset.basketCount;
            bag.setAttribute('aria-label', selection.dataset.basketLabel);
            if (announce) page.querySelector('[data-basket-status]').textContent = selection.dataset.basketLabel;
        }
        content.querySelectorAll('[data-basket-image-fallback]').forEach((image) => {
            const fallback = image.dataset.basketImageFallback;
            const useFallback = () => {
                if (image.getAttribute('src') !== fallback) image.src = fallback;
            };
            image.addEventListener('error', useFallback, {once: true});
            if (image.complete && !image.naturalWidth) useFallback();
        });
    };
    refreshPresentation();
    new MutationObserver(() => refreshPresentation(true)).observe(content, {childList: true});
})();
