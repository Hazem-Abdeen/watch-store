"use strict";

// Disclosure controls only: Oscar continues to handle every category URL.
document.querySelectorAll(".abdeen-category-toggle").forEach((button) => {
    const children = document.getElementById(button.getAttribute("aria-controls"));
    if (!children) return;
    const branch = button.closest("li");
    const active = Boolean(branch.querySelector('[aria-current="page"]'));
    const setExpanded = (expanded) => {
        button.setAttribute("aria-expanded", String(expanded));
        children.hidden = !expanded;
    };
    setExpanded(branch.classList.contains("abdeen-category-root") || active);
    button.hidden = false;
    if (active) branch.classList.add("abdeen-active-branch");
    button.addEventListener("click", () => setExpanded(children.hidden));
});

// Move one navigation tree between the sidebar and a native modal dialog.
// showModal provides focus containment, background inertness and Escape support.
const catalogue = document.querySelector(".abdeen-catalogue");
const browseNavigation = catalogue?.querySelector(".abdeen-browse-navigation");
const navigationContent = catalogue?.querySelector("[data-category-navigation]");
const filterDialog = catalogue?.querySelector("[data-filter-dialog]");
const filterTrigger = catalogue?.querySelector("[data-filter-open]");
if (browseNavigation && navigationContent && filterTrigger && typeof filterDialog?.showModal === "function") {
    const desktopNavigation = window.matchMedia("(min-width: 1024px)");
    const closeButton = navigationContent.querySelector("[data-filter-close]");
    const closeDrawer = () => filterDialog.close();
    const syncNavigation = () => {
        if (filterDialog.open) closeDrawer();
        browseNavigation.open = true;
        filterTrigger.hidden = desktopNavigation.matches;
        (desktopNavigation.matches ? browseNavigation : filterDialog).append(navigationContent);
        catalogue.dataset.filtersReady = "true";
    };
    filterTrigger.addEventListener("click", () => {
        filterDialog.showModal();
        filterTrigger.setAttribute("aria-expanded", "true");
        document.documentElement.classList.add("abdeen-filter-open");
        closeButton.focus();
    });
    closeButton.addEventListener("click", closeDrawer);
    filterDialog.addEventListener("close", () => {
        filterTrigger.setAttribute("aria-expanded", "false");
        document.documentElement.classList.remove("abdeen-filter-open");
        if (!desktopNavigation.matches) filterTrigger.focus();
    });
    filterDialog.addEventListener("click", (event) => {
        const rect = filterDialog.getBoundingClientRect();
        if (event.target === filterDialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) closeDrawer();
    });
    // Also restore scrolling when the browser returns to this page from its cache.
    window.addEventListener("pageshow", () => { if (!filterDialog.open) document.documentElement.classList.remove("abdeen-filter-open"); });
    desktopNavigation.addEventListener("change", syncNavigation);
    syncNavigation();
}
