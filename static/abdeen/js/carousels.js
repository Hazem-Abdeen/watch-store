"use strict";

document.querySelectorAll('[data-carousel]').forEach((carousel) => {
    const track = carousel.querySelector('.abdeen-carousel-track');
    const dots = carousel.querySelector('.abdeen-carousel-dots');
    const status = carousel.querySelector('.abdeen-carousel-status');
    const retry = carousel.querySelector('.abdeen-carousel-retry');
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let total = Number(carousel.dataset.total);
    let nextBatch = Number(carousel.dataset.nextPage) || null;
    let perPage = 0;
    let activePage = 0;
    let requestedPage = 0;
    let pending = null;
    let failed = false;
    let navigation = 0;
    let navigating = false;
    let lastWidth = 0;
    let frame = 0;

    const pageCount = () => Math.ceil(total / perPage);
    const step = () => track.firstElementChild.getBoundingClientRect().width
        + parseFloat(getComputedStyle(track).columnGap);
    // The last page aligns to the final product, without empty trailing slots.
    const firstProduct = page => Math.max(0, Math.min(page * perPage, total - perPage));
    const offset = page => firstProduct(page) * step();
    const behavior = () => motion.matches ? 'instant' : 'smooth';

    const updateActive = () => {
        let nearest = 0;
        let distance = Infinity;
        for (let page = 0; page < pageCount(); page++) {
            const delta = Math.abs(track.scrollLeft - offset(page));
            if (delta < distance) { nearest = page; distance = delta; }
        }
        const changed = activePage !== nearest;
        activePage = nearest;
        [...dots.children].forEach((button, page) => {
            button.setAttribute('aria-current', String(page === activePage));
            button.tabIndex = page === activePage ? 0 : -1;
        });
        // Long ranges keep one row of dots; reveal the active dot horizontally.
        const current = dots.children[activePage];
        if (changed && current) {
            const rect = current.getBoundingClientRect();
            const bounds = dots.getBoundingClientRect();
            if (rect.left < bounds.left || rect.right > bounds.right) {
                dots.scrollBy({left: rect.left - bounds.left - (dots.clientWidth - rect.width) / 2,
                    behavior: behavior()});
            }
        }
    };

    const renderDots = () => {
        const count = pageCount();
        dots.hidden = count <= 1;
        const wanted = count > 1 ? count : 0;
        // Reuse focused buttons when a batch arrives or a breakpoint changes.
        while (dots.children.length > wanted) dots.lastElementChild.remove();
        for (let page = 0; page < wanted; page++) {
            let button = dots.children[page];
            if (!button) {
                button = document.createElement('button');
                button.type = 'button';
                button.dataset.page = String(page);
                button.setAttribute('aria-controls', track.id);
                const mark = document.createElement('span');
                mark.setAttribute('aria-hidden', 'true');
                button.append(mark);
                dots.append(button);
            }
            const start = firstProduct(page) + 1;
            button.setAttribute('aria-label', `Go to products ${start}–${Math.min(start + perPage - 1, total)}`);
        }
        [...track.children].forEach((card, index) => {
            card.toggleAttribute('data-page-start', index % perPage === 0);
        });
        updateActive();
    };

    const prepareImages = (root) => {
        root.querySelectorAll('[data-image-fallback]').forEach(image => {
            const fallback = () => {
                const src = image.dataset.imageFallback;
                if (!src) return;
                delete image.dataset.imageFallback;
                image.src = src;
                image.alt = 'Image coming soon';
            };
            image.addEventListener('error', fallback, {once: true});
            if (image.complete && !image.naturalWidth) fallback();
        });
    };

    const load = () => {
        if (pending) return pending;
        if (!nextBatch) return Promise.resolve(true);
        status.textContent = 'Loading more watches…';
        track.setAttribute('aria-busy', 'true');
        const url = new URL(window.location.href);
        url.search = new URLSearchParams({carousel: carousel.dataset.carousel, page: nextBatch}).toString();
        pending = fetch(url, {headers: {'Accept': 'application/json'}})
            .then(response => {
                if (!response.ok) throw new Error('Unable to load watches');
                return response.json();
            })
            .then(data => {
                const fragment = document.createElement('template');
                fragment.innerHTML = data.html;
                prepareImages(fragment.content);
                track.append(fragment.content);
                total = data.total;
                nextBatch = data.next_page;
                failed = false;
                retry.hidden = true;
                status.textContent = '';
                renderDots();
                return true;
            })
            .catch(() => {
                failed = true;
                retry.hidden = false;
                status.textContent = 'More watches could not be loaded. Please try again.';
                return false;
            })
            .finally(() => {
                pending = null;
                track.removeAttribute('aria-busy');
            });
        return pending;
    };

    const goToPage = async page => {
        const target = Math.max(0, Math.min(page, pageCount() - 1));
        requestedPage = target;
        const ticket = ++navigation;
        navigating = true;
        // Dots cover the complete range, including batches not fetched yet.
        try {
            while (track.children.length < Math.min(total, (target + 1) * perPage) && nextBatch) {
                if (!await load() || ticket !== navigation) return;
            }
            // A wheel gesture's native snap can otherwise overwrite scrollTo
            // when it finishes. Wait for that motion (or a cancelled request).
            await new Promise(resolve => {
                let previous = track.scrollLeft;
                let stillFrames = 0;
                const settled = () => {
                    const current = track.scrollLeft;
                    stillFrames = Math.abs(current - previous) < .5 ? stillFrames + 1 : 0;
                    previous = current;
                    if (stillFrames >= 3 || ticket !== navigation) resolve();
                    else requestAnimationFrame(settled);
                };
                requestAnimationFrame(settled);
            });
            if (ticket !== navigation) return;
            requestedPage = Math.max(0, Math.min(target, pageCount() - 1));
            track.scrollTo({left: offset(requestedPage), behavior: behavior()});
        } finally {
            if (ticket === navigation) navigating = false;
        }
    };

    dots.addEventListener('click', event => {
        const button = event.target.closest('button[data-page]');
        if (button) goToPage(Number(button.dataset.page));
    });
    retry.addEventListener('click', async () => {
        if (await load()) goToPage(requestedPage);
    });
    const keyboard = event => {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        if (event.currentTarget === track && event.target !== track) return;
        // A second key can arrive before the scroll event's animation frame.
        updateActive();
        let page;
        if (event.key === 'ArrowLeft') page = activePage - 1;
        else if (event.key === 'ArrowRight') page = activePage + 1;
        else if (event.key === 'Home') page = 0;
        else if (event.key === 'End') page = pageCount() - 1;
        else return;
        event.preventDefault();
        page = Math.max(0, Math.min(page, pageCount() - 1));
        if (event.currentTarget === dots) dots.children[page]?.focus({preventScroll: true});
        goToPage(page);
    };
    dots.addEventListener('keydown', keyboard);
    track.addEventListener('keydown', keyboard);
    track.addEventListener('scroll', () => {
        if (frame) return;
        frame = requestAnimationFrame(() => {
            frame = 0;
            updateActive();
            if (!failed && !pending && !navigating && nextBatch && track.scrollWidth - track.clientWidth - track.scrollLeft < track.clientWidth) {
                // Native touch/trackpad scrolling can also reach the next batch.
                requestedPage = activePage;
                load();
            }
        });
    }, {passive: true});

    // Keep native panning/vertical scrolling. Only suppress the click generated
    // by a drag, never a deliberate tap or keyboard activation of a product.
    let origin = null;
    let dragged = false;
    let suppressUntil = 0;
    track.addEventListener('pointerdown', event => {
        navigation++;
        navigating = false;
        origin = {x: event.clientX, y: event.clientY};
        dragged = false;
        suppressUntil = 0;
    }, {passive: true});
    track.addEventListener('pointermove', event => {
        if (origin && Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 10) dragged = true;
    }, {passive: true});
    const endGesture = event => {
        if (origin && (dragged || event.type === 'pointercancel')) suppressUntil = performance.now() + 400;
        origin = null;
    };
    track.addEventListener('pointerup', endGesture, {passive: true});
    track.addEventListener('pointercancel', endGesture, {passive: true});
    track.addEventListener('click', event => {
        if (event.detail && performance.now() < suppressUntil) {
            event.preventDefault();
            event.stopPropagation();
        }
    }, true);
    track.addEventListener('dragstart', event => event.preventDefault());

    const resize = () => {
        const nextSize = Number(getComputedStyle(carousel).getPropertyValue('--cards-per-page'));
        if (perPage === nextSize && Math.abs(lastWidth - track.clientWidth) < 1) return;
        const first = perPage ? firstProduct(activePage) : 0;
        perPage = nextSize;
        lastWidth = track.clientWidth;
        activePage = Math.min(Math.floor(first / perPage), pageCount() - 1);
        track.scrollTo({left: offset(activePage), behavior: 'instant'});
        renderDots();
    };
    carousel.classList.add('is-enhanced');
    resize();
    new ResizeObserver(resize).observe(track);
});
