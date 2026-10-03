"use strict";

// Oscar owns every mutation, price and validation decision. This is presentation.
(() => {
    const drawer = document.querySelector('[data-cart-drawer]');
    if (!drawer || typeof drawer.showModal !== 'function' || !window.fetch) return;
    const body = drawer.querySelector('[data-cart-body]');
    const status = drawer.querySelector('[data-cart-status]');
    const error = drawer.querySelector('[data-cart-error]');
    const recovery = drawer.querySelector('[data-cart-recovery]');
    let busy = false;
    let opener = null;
    const parse = (html) => new DOMParser().parseFromString(html, 'text/html');
    const plainText = (html) => parse(html).body.textContent.trim();

    function open(trigger) {
        if (drawer.open) return;
        opener = trigger || document.activeElement;
        drawer.showModal();
        document.documentElement.classList.add('abdeen-cart-open');
    }

    function setBusy(value) {
        busy = value;
        drawer.setAttribute('aria-busy', String(value));
        body.inert = value;
        status.textContent = value ? drawer.dataset.updating : '';
    }

    function showError(message, uncertain = false) {
        error.textContent = message;
        error.hidden = !message;
        recovery.hidden = !uncertain;
    }

    async function request(url, options = {}) {
        const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options});
        if (!response.ok) throw new Error('Cart request failed');
        return response;
    }

    function render(html) {
        const content = parse(html).querySelector('[data-cart-content]');
        if (!content) throw new Error('Cart content missing');
        body.replaceChildren(document.importNode(content, true));
        drawer.querySelector('[data-cart-title]').textContent = content.dataset.title;
        document.querySelectorAll('.abdeen-bag-link').forEach((link) => {
            link.setAttribute('aria-label', content.dataset.label);
            const count = link.querySelector('.abdeen-bag-count');
            if (count) count.textContent = content.dataset.count;
        });
        body.querySelectorAll('[data-cart-image-fallback]').forEach((image) => {
            const fallback = () => {
                if (image.getAttribute('src') !== image.dataset.cartImageFallback) image.src = image.dataset.cartImageFallback;
            };
            image.addEventListener('error', fallback, {once: true});
            if (image.complete && !image.naturalWidth) fallback();
        });
    }

    async function refresh() {
        render(await (await request(drawer.dataset.url)).text());
    }

    async function load(trigger) {
        open(trigger);
        if (busy) return;
        setBusy(true);
        showError('');
        try { await refresh(); }
        catch { showError(drawer.dataset.error, true); }
        finally { setBusy(false); }
    }

    async function add(form, trigger) {
        if (busy) return;
        const data = new FormData(form);
        // Successful additions return the server-rendered drawer. Invalid adds
        // retain Oscar's redirect and bound-form errors on the originating page.
        data.set('next', drawer.dataset.url);
        const button = trigger || form.querySelector('[type="submit"]');
        const label = button?.innerHTML;
        setBusy(true);
        showError('');
        form.querySelector('[data-cart-add-error]')?.remove();
        if (button) button.disabled = true;
        try {
            const response = await request(form.action, {method: 'POST', body: data});
            const html = await response.text();
            const documentResponse = parse(html);
            if (!documentResponse.querySelector('[data-cart-content]')) {
                const messages = [...documentResponse.querySelectorAll('#messages .alert-danger, #add_to_basket_form .error-block, #add_to_basket_form .alert-danger')];
                if (!messages.length) throw new Error('Unexpected add response');
                const alert = document.createElement('p');
                alert.className = 'error-block';
                alert.dataset.cartAddError = '';
                alert.setAttribute('role', 'alert');
                alert.textContent = [...new Set(messages.map((message) => {
                    message.querySelectorAll('.close').forEach((close) => close.remove());
                    return message.textContent.trim();
                }))].join(' ');
                form.prepend(alert);
                return;
            }
            render(html);
            open(button);
        } catch {
            open(button);
            showError(drawer.dataset.updateError, true);
        } finally {
            setBusy(false);
            if (button) {
                button.disabled = false;
                button.classList.remove('disabled');
                button.innerHTML = label;
            }
        }
    }

    async function update(form, trigger, removeName) {
        if (busy) return;
        if (!removeName && !form.reportValidity()) return;
        const data = new FormData(form);
        if (removeName) data.set(removeName, 'on');
        const lineId = trigger.closest('[data-cart-line]')?.dataset.cartLine;
        const selector = trigger.matches('[data-cart-quantity]') ? '[data-cart-quantity]'
            : trigger.matches('[data-cart-step]') ? `[data-cart-step="${trigger.dataset.cartStep}"]` : '[data-cart-remove]';
        setBusy(true);
        showError('');
        try {
            const response = await request(form.action, {
                method: 'POST', body: data, headers: {'X-Requested-With': 'XMLHttpRequest'},
            });
            const result = await response.json();
            const basket = parse(result.content_html);
            const errors = [...basket.querySelectorAll('.error-block, .errorlist')].map((element) => element.textContent.trim());
            for (const level of ['error', 'warning']) {
                for (const message of result.messages?.[level] || []) errors.push(plainText(message));
            }
            // Keep an underlying full basket page in sync when opened there.
            const basketPage = document.querySelector('.abdeen-basket #content_inner');
            if (basketPage) basketPage.innerHTML = result.content_html;
            await refresh();
            showError([...new Set(errors)].join(' '));
        } catch { showError(drawer.dataset.updateError, true); }
        finally {
            setBusy(false);
            if (drawer.open) {
                const next = body.querySelector(`[data-cart-line="${lineId}"] ${selector}`);
                (next && !next.disabled ? next : drawer.querySelector('[data-cart-close]')).focus();
            }
        }
    }

    document.querySelectorAll('[data-cart-open]').forEach((link) => {
        link.setAttribute('aria-haspopup', 'dialog');
        link.setAttribute('aria-controls', drawer.id);
    });
    document.addEventListener('click', (event) => {
        const link = event.target.closest('[data-cart-open]');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        event.preventDefault();
        load(link);
    });
    document.addEventListener('submit', (event) => {
        if (event.target.matches('[data-cart-add]')) {
            event.preventDefault();
            add(event.target, event.submitter);
        } else if (event.target.matches('[data-cart-form]')) {
            event.preventDefault();
            update(event.target, document.activeElement);
        }
    });
    drawer.addEventListener('click', (event) => {
        if (event.target.closest('[data-cart-close]')) { drawer.close(); return; }
        const bounds = drawer.getBoundingClientRect();
        if (event.target === drawer && (event.clientX < bounds.left || event.clientX > bounds.right)) {
            drawer.close(); return;
        }
        if (busy) return;
        const step = event.target.closest('[data-cart-step]');
        const remove = event.target.closest('[data-cart-remove]');
        if (step) {
            const input = step.closest('[data-cart-line]').querySelector('[data-cart-quantity]');
            if (Number(step.dataset.cartStep) > 0) input.stepUp(); else input.stepDown();
            update(step.closest('form'), step);
        } else if (remove) update(remove.closest('form'), remove, remove.dataset.cartRemove);
    });
    drawer.addEventListener('change', (event) => {
        if (event.target.matches('[data-cart-quantity]')) update(event.target.form, event.target);
    });
    drawer.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const focusable = [...drawer.querySelectorAll('a[href], button:not(:disabled), input:not([type="hidden"]):not(:disabled)')]
            .filter(element => element.tabIndex >= 0 && !element.closest('[inert]') && element.getClientRects().length);
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
    drawer.addEventListener('close', () => {
        document.documentElement.classList.remove('abdeen-cart-open');
        if (opener?.isConnected) opener.focus();
    });
})();
