// Prevent accidental repeated clicks; server-side basket claiming is authoritative.
(() => {
    const form = document.getElementById('cod-checkout');
    if (!form) return;
    let submitting = false;
    form.addEventListener('submit', event => {
        if (submitting) { event.preventDefault(); return; }
        submitting = true;
        const button = event.submitter;
        if (button) {
            button.setAttribute('aria-disabled', 'true');
            button.textContent = button.value === 'place_order' ? 'PLACING ORDER…' : 'UPDATING…';
        }
    });
    window.addEventListener('pageshow', () => {
        submitting = false;
        const button = document.getElementById('place-order');
        if (button) { button.removeAttribute('aria-disabled'); button.textContent = 'PLACE ORDER'; }
    });
})();
