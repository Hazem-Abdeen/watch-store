// Run against checkout_preview.py with CONSOLE_ORDER_EMAILS=1 and stdout logged.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = 'http://127.0.0.1:8023';
const log = process.env.CONSOLE_EMAIL_LOG;
assert.ok(log, 'Set CONSOLE_EMAIL_LOG to the preview server stdout log');
const merchants = ['ops@example.test', 'owner@example.test', 'sales@example.test'];
const recipients = () => (fs.readFileSync(log, 'utf8').replace(/\r?\n[ \t]+/g, ' ')
  .match(/^To: .*$/gm) || []).map(line => line.slice(4).split(',').map(address => address.trim()));
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
  try {
    const context = await browser.newContext();
    await context.route('https://ajax.googleapis.com/**', route => route.abort());
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const fixture = await (await context.request.get(base + '/__cod_fixture__/')).json();
    const before = recipients().length;
    await page.goto(base + fixture.product);
    await page.locator('form[data-cart-add] button[type="submit"]').click();
    await page.locator('[data-cart-close]').click();
    await page.goto(base + '/basket/');
    await page.locator('.abdeen-basket-checkout').click();
    for (const [name, value] of Object.entries({email: 'console-checkout@example.test', phone_number: '0791234567', first_name: 'Console', last_name: 'Customer', line1: '12 Example Street', line4: 'Amman'})) {
      await page.locator(`[name="${name}"]`).fill(value);
    }
    const form = await page.locator('#cod-checkout').evaluate(form => Object.fromEntries(new FormData(form)));
    form.action = 'place_order';
    await page.getByRole('button', {name: 'PLACE ORDER', exact: true}).click();
    await page.waitForURL('**/checkout/thank-you/');
    await page.getByRole('heading', {name: 'Thank you for your order', exact: true}).waitFor();
    const order = await (await context.request.get(base + '/__cod_result__/')).json();
    assert.equal(order.basket_orders, 1);
    assert.equal(order.source, 'Cash on Delivery (COD)');
    assert.equal(Number(order.debited), 0);
    assert.deepEqual(order.notifications, [{kind: 'customer', status: 'sent'}, {kind: 'merchant', status: 'sent'}]);
    assert.deepEqual(recipients().slice(before), [['console-checkout@example.test'], merchants]);
    await page.reload();
    await page.reload();
    await context.request.post(base + '/checkout/', {form});
    assert.equal(recipients().length, before + 2, 'Refresh/replay must not print more messages');
    assert.equal((await (await context.request.get(base + '/__cod_result__/')).json()).basket_orders, 1);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: 'PASS', order: order.number, customerTo: 'console-checkout@example.test', merchantTo: merchants, consoleMessages: 2, refreshAndReplayResends: 0, notifications: order.notifications}, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
