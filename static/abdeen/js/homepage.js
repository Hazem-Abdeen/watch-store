"use strict";

// Filters only the server-rendered range products; no cart or wishlist state.
document.querySelectorAll("[data-home-filter-section]").forEach((section) => {
    const controls = section.querySelector("[data-home-filters]");
    if (!controls) return; // Missing/empty ranges have no controls.
    const buttons = [...controls.querySelectorAll("[data-home-filter]")];
    const cards = [...section.querySelectorAll("[data-home-product]")];
    const status = section.querySelector("[data-home-filter-status]");
    controls.hidden = false;

    buttons.forEach((button) => {
        button.setAttribute("aria-controls", "best-sellers-grid");
        button.addEventListener("click", () => {
            const filter = button.dataset.homeFilter;
            buttons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
            let visible = 0;
            cards.forEach((card) => {
                card.hidden = !(filter === "all" || card.dataset.filters.split(" ").includes(filter));
                if (!card.hidden) visible += 1;
            });
            status.textContent = visible + (visible === 1 ? " watch shown." : " watches shown.");
        });
    });
});

// Also cover storage URLs that fail after the HTML was rendered.
document.querySelectorAll("[data-image-fallback]").forEach((image) => {
    const useFallback = () => {
        const fallback = image.dataset.imageFallback;
        if (!fallback) return;
        delete image.dataset.imageFallback;
        image.src = fallback;
        image.alt = "Image coming soon";
        const category = image.closest(".abdeen-category-card");
        if (category) category.querySelector(".abdeen-category-tag").textContent = "Image coming soon";
    };
    image.addEventListener("error", useFallback, {once: true});
    if (image.complete && image.naturalWidth === 0) useFallback();
});
