// Run against product_detail_preview.py: all basket writes use a disposable DB.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.STOREFRONT_ORIGIN || 'http://127.0.0.1:8021';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-cart-qa';
fs.mkdirSync(screenshots, {recursive: true});

(async () => {
    const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
    try {
        for (const width of [1440, 768, 390, 320]) {
            const context = await browser.newContext({viewport: {width, height: 1000}});
            await context.route('https://ajax.googleapis.com/**', route => route.abort());
            const page = await context.newPage();
            page.setDefaultTimeout(15000);
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            const urls = await (await context.request.get(origin + '/__detail_fixture__/')).json();
            const drawer = page.locator('[data-cart-drawer]');
            const ready = () => page.waitForFunction(() => {
                const cart = document.querySelector('[data-cart-drawer]');
                return cart.open && cart.getAttribute('aria-busy') === 'false' && cart.querySelector('[data-cart-content]');
            });
            const count = async value => {
                await ready();
                await page.waitForFunction(value => document.querySelector('[data-cart-content]').dataset.count === String(value), value);
                assert.equal(await page.locator('.abdeen-bag-count').innerText(), String(value));
            };
            await page.goto(origin + urls.mixed);
            const add = page.getByRole('button', {name: 'Add to Cart', exact: true});
            await add.click();
            await count(1);
            assert.equal(page.url(), origin + urls.mixed);
            assert.equal(await drawer.getAttribute('aria-labelledby'), 'cart-drawer-title');
            assert.equal(await page.evaluate(() => document.activeElement.matches('[data-cart-close]')), true);
            await page.keyboard.press('Shift+Tab');
            assert.equal(await page.evaluate(() => document.querySelector('[data-cart-drawer]').contains(document.activeElement)), true);
            const plus = drawer.locator('[data-cart-step="1"]').first();
            await plus.click();
            await count(2);
            await plus.click();
            await count(3);
            await plus.click();
            await ready();
            await page.waitForFunction(() => !document.querySelector('[data-cart-error]').hidden);
            assert.match(await drawer.locator('[data-cart-error]').innerText(), /requested quantity is not available/);
            assert.equal(await drawer.locator('[data-cart-quantity]').inputValue(), '3');
            assert.equal(await drawer.locator('[data-cart-quantity]').getAttribute('max'), null);
            await drawer.locator('[data-cart-step="-1"]').click();
            await count(2);
            await page.keyboard.press('Escape');
            assert.equal(await drawer.evaluate(el => el.open), false);
            await page.waitForFunction(() => document.activeElement.matches('[data-cart-add] button[type="submit"]'));
            assert.equal(await add.evaluate(el => el === document.activeElement), true);
            await page.goto(origin + urls.in_stock);
            await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
            await count(3);
            assert.equal(await drawer.locator('[data-cart-line]').count(), 2);
            assert.doesNotMatch(await drawer.innerText(), /Your cart total is now/);
            await page.evaluate(() => document.fonts.ready);
            await drawer.screenshot({path: `${screenshots}/drawer-${width}.png`});
            await page.screenshot({path: `${screenshots}/page-${width}.png`});
            assert.equal(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth), true);
            const box = await drawer.boundingBox();
            assert.ok(Math.abs(box.x + box.width - width) < 2);
            assert.equal(await drawer.locator('.abdeen-cart-checkout').isVisible(), true);
            if (width > 500) await page.mouse.click(20, 300);
            else await drawer.locator('[data-cart-close]').click();
            assert.equal(await drawer.evaluate(el => el.open), false);
            // Adding the same one-stock product is rejected without a second write.
            await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
            await page.waitForSelector('[data-cart-add-error]');
            assert.match(await page.locator('[data-cart-add-error]').innerText(), /requested quantity is not available/);
            assert.equal(await drawer.evaluate(el => el.open), false);
            await page.locator('[data-cart-open]').click();
            await count(3);
            await drawer.locator('.abdeen-cart-checkout').click();
            await page.waitForURL(/\/(checkout|accounts)\//);
            assert.ok(await page.locator('main').isVisible());
            await page.goto(origin + '/basket/');
            await page.locator('[data-cart-open]').click();
            await count(3);
            // Direct entry uses the same validated update and keeps the full bag in sync.
            await drawer.locator('[data-cart-quantity]').first().fill('1');
            await drawer.locator('[data-cart-quantity]').first().press('Tab');
            await count(2);
            await page.waitForFunction(() => document.querySelector('.abdeen-basket [data-basket-count]').dataset.basketCount === '2');
            // Quantity changes and removals survive a page reload.
            await drawer.locator('[data-cart-remove]').first().click();
            await count(1);
            await page.reload();
            await page.locator('[data-cart-open]').click();
            await count(1);
            await drawer.locator('[data-cart-remove]').click();
            await count(0);
            assert.match(await drawer.innerText(), /Your cart is empty/);
            assert.equal(await drawer.locator('.abdeen-cart-checkout').count(), 0);
            assert.deepEqual(errors, []);
            console.log(JSON.stringify({width, add: true, update: true, stockValidation: true, remove: true, keyboard: true, overflow: false}));
            await context.close();
        }
        // Failed requests offer recovery without automatically repeating a POST.
        const context = await browser.newContext();
        const page = await context.newPage();
        const urls = await (await context.request.get(origin + '/__detail_fixture__/')).json();
        await page.goto(origin + urls.mixed);
        let posts = 0;
        await page.route('**/basket/add/**', route => { posts++; return route.abort(); });
        await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
        await page.waitForSelector('[data-cart-recovery]:visible');
        assert.equal(posts, 1);
        assert.match(await page.locator('[data-cart-error]').innerText(), /check before trying again/);
        await context.close();
        const plain = await browser.newContext({javaScriptEnabled: false});
        const plainPage = await plain.newPage();
        await plainPage.goto(origin + urls.mixed);
        await plainPage.getByRole('button', {name: 'Add to Cart', exact: true}).click();
        await plainPage.waitForLoadState('networkidle');
        await plainPage.goto(origin + '/basket/');
        assert.equal(await plainPage.locator('.abdeen-basket-line').count(), 1);
        await plain.close();
        console.log('Network recovery and no-JavaScript purchase passed.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
