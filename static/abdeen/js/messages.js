"use strict";

// Presentation only: Oscar still creates, clears and dismisses messages.
(() => {
    const root = document.getElementById('main-content');
    if (!root) return;
    let nextErrorId = 0;
    let pendingFocus;
    const dismissLabel = root.querySelector('#messages')?.dataset.dismissLabel || 'Dismiss message';

    const enhanceAlert = (alert) => {
        if (alert.dataset.abdeenMessage) return;
        alert.dataset.abdeenMessage = 'true';
        alert.classList.add('abdeen-message');
        const error = alert.matches('.alert-danger, .alert-error');
        if (!alert.hasAttribute('role')) alert.setAttribute('role', error ? 'alert' : 'status');
        alert.setAttribute('aria-atomic', 'true');
        const close = alert.querySelector('[data-dismiss="alert"]');
        if (close) {
            let button = close;
            if (close.tagName !== 'BUTTON') {
                button = document.createElement('button');
                for (const attribute of close.attributes) {
                    if (!['href', 'role'].includes(attribute.name)) button.setAttribute(attribute.name, attribute.value);
                }
                button.innerHTML = close.innerHTML;
                close.replaceWith(button);
            }
            button.type = 'button';
            if (!button.hasAttribute('aria-label')) button.setAttribute('aria-label', dismissLabel);
            alert.classList.add('alert-dismissible');
        }
        // Legacy/AJAX alerts share the same content wrapper without changing HTML.
        if (!alert.querySelector('.abdeen-message-content')) {
            const content = document.createElement('div');
            content.className = 'abdeen-message-content';
            [...alert.childNodes].forEach(node => {
                if (!(node.nodeType === 1 && node.matches('[data-dismiss="alert"]'))) content.append(node);
            });
            alert.append(content);
        }
    };
    const connectErrors = () => {
        root.querySelectorAll('.error-block, .errorlist').forEach(error => {
            if (!error.textContent.trim() || error.matches('.nonfield, .nonform')) return;
            const group = error.closest('.form-group, .abdeen-basket-controls, .form-inline, td');
            if (!group) return;
            const controls = group.querySelectorAll('input:not([type="hidden"]), select, textarea');
            if (!controls.length) return;
            if (!error.id) {
                const expectedId = [...controls].flatMap(control =>
                    (control.getAttribute('aria-describedby') || '').split(/\s+/)
                ).find(id => id.endsWith('_error') && !document.getElementById(id));
                if (expectedId) error.id = expectedId;
                else {
                    do { error.id = `abdeen-field-error-${++nextErrorId}`; }
                    while (document.querySelectorAll(`#${error.id}`).length > 1);
                }
            }
            controls.forEach(control => {
                const ids = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
                ids.add(error.id);
                control.setAttribute('aria-describedby', [...ids].join(' '));
                control.setAttribute('aria-invalid', 'true');
            });
        });
    };
    const enhance = () => {
        root.querySelectorAll('.alert').forEach(enhanceAlert);
        connectErrors();
        if (pendingFocus && !pendingFocus.alert.isConnected) {
            if (document.activeElement === document.body) {
                const target = pendingFocus.next?.isConnected ? pendingFocus.next : root;
                target.focus({preventScroll: true});
            }
            pendingFocus = null;
        }
    };
    root.addEventListener('click', event => {
        const close = event.target.closest('[data-dismiss="alert"]');
        const alert = close?.closest('.alert');
        if (!alert || !alert.contains(document.activeElement)) return;
        const alerts = [...root.querySelectorAll('.alert')];
        const next = alerts[alerts.indexOf(alert) + 1] || alerts[alerts.indexOf(alert) - 1];
        pendingFocus = {alert, next: next?.querySelector('[data-dismiss="alert"], a, button')};
    }, true);
    enhance();
    new MutationObserver(enhance).observe(root, {childList: true, subtree: true});
})();
