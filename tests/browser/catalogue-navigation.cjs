// Run against the local storefront, with its real category tree and search index.
// PLAYWRIGHT_MODULE and CHROME_PATH may point to existing browser tooling.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.CATALOGUE_ORIGIN || 'http://127.0.0.1:8000';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-catalogue-navigation';
const baseline = process.env.CATALOGUE_BASELINE_HTML && fs.readFileSync(process.env.CATALOGUE_BASELINE_HTML, 'utf8');
fs.mkdirSync(screenshots, {recursive: true});
(async () => {
    const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
    try {
        const results = [];
        for (const width of [1440, 768, 390, 320]) {
            const context = await browser.newContext({viewport: {width, height: 1000}});
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            assert.equal((await page.goto(origin + '/catalogue/')).status(), 200);
            await page.evaluate(() => document.fonts.ready);
            const tree = page.locator('.abdeen-category-navigation');
            const dialog = page.locator('[data-filter-dialog]');
            const trigger = page.locator('[data-filter-open]');
            const close = page.locator('[data-filter-close]');
            const overflow = async () => {
                assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth));
            };
            const open = async () => {
                if (width < 1024) {
                    await trigger.click();
                    assert.equal(await dialog.evaluate(el => el.matches(':modal')), true);
                    assert.equal(await trigger.getAttribute('aria-expanded'), 'true');
                    assert.equal(await close.evaluate(el => el === document.activeElement), true);
                }
            };
            assert.equal(await tree.count(), 1);
            assert.equal(await page.getByText('SHOW RESULTS FOR', {exact:true}).count(), 0);
            assert.equal(await page.locator('.abdeen-catalogue-sidebar').isVisible(), width >= 1024);
            assert.equal(await trigger.isVisible(), width < 1024);
            if (baseline) {
                assert.equal(await page.evaluate(oldHTML => {
                    const before = new DOMParser().parseFromString(oldHTML, 'text/html');
                    const now = document.querySelector('.abdeen-catalogue-grid');
                    return before.querySelector('.abdeen-catalogue-grid').innerHTML === now.innerHTML;
                }, baseline), true, 'Product grid markup must remain unchanged');
                assert.equal(await page.evaluate(oldHTML => {
                    const before = new DOMParser().parseFromString(oldHTML, 'text/html');
                    const oldLinks = [...before.querySelectorAll('.side_categories a')].map(a => a.getAttribute('href'));
                    const currentLinks = [...document.querySelectorAll('[data-category-navigation] a')].map(a => a.getAttribute('href'));
                    return oldLinks.every(url => currentLinks.includes(url));
                }, baseline), true, 'Every original category URL remains available');
            }
            await overflow();
            const total = (await page.locator('.abdeen-result-count strong').textContent()).trim();
            if (width < 1024) {
                const buttonRect = await trigger.boundingBox();
                const sortRect = await page.locator('.abdeen-catalogue-sort').boundingBox();
                assert.equal(buttonRect.y, sortRect.y);
                assert.ok(buttonRect.x + buttonRect.width < sortRect.x);
            }
            await page.screenshot({path: `${screenshots}/catalogue-${width}.png`});
            await open();
            if (width < 1024) {
                await page.keyboard.press('Shift+Tab');
                assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true, 'Backward focus stays inside drawer');
                await page.keyboard.press('Tab');
                assert.equal(await close.evaluate(el => el === document.activeElement), true);
                await page.keyboard.press('Escape');
                assert.equal(await dialog.isVisible(), false);
                assert.equal(await trigger.evaluate(el => el === document.activeElement), true);
                await open();
                await close.click();
                await page.waitForFunction(() => document.querySelector('[data-filter-open]').getAttribute('aria-expanded') === 'false');
                assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
                await open();
                const rect = await dialog.boundingBox();
                const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
                await page.mouse.click((rect.x + rect.width + clientWidth) / 2, 100);
                assert.equal(await dialog.isVisible(), false);
                await open();
            }
            const brandsToggle = page.getByRole('button', {name: 'Toggle Brands categories', exact:true});
            await brandsToggle.click();
            assert.equal(await tree.getByRole('link', {name: 'Casio', exact:true}).isVisible(), false);
            await brandsToggle.focus();
            await page.keyboard.press('Enter');
            const casioToggle = page.getByRole('button', {name: 'Toggle Casio categories', exact:true});
            assert.equal(await casioToggle.getAttribute('aria-expanded'), 'false');
            await casioToggle.click();
            assert.equal(await casioToggle.getAttribute('aria-expanded'), 'true');
            const childNames = ['G-SHOCK', 'CASIO ANALOG', 'CASIO DIGITAL', 'Edifice'];
            for (const name of childNames) {
                const link = tree.getByRole('link', {name, exact:true});
                assert.equal(await link.isVisible(), true);
                if (width === 1440) assert.equal((await context.request.get(origin + await link.getAttribute('href'))).status(), 200);
            }
            if (width < 1024) await dialog.evaluate(el => { el.scrollTop = 0; });
            await page.screenshot({path: `${screenshots}/navigation-${width}.png`});
            await overflow();
            // Follow a real child category; its ancestor groups must reopen on arrival.
            const gshock = tree.getByRole('link', {name:'G-SHOCK', exact:true});
            const gshockURL = await gshock.getAttribute('href');
            await gshock.click();
            await page.waitForURL(origin + gshockURL);
            await open();
            assert.equal(await tree.locator('[aria-current="page"]').textContent(), 'G-SHOCK');
            assert.equal(await page.getByRole('button', {name:'Toggle Casio categories', exact:true}).getAttribute('aria-expanded'), 'true');
            await overflow();
            await page.screenshot({path: `${screenshots}/active-category-${width}.png`});
            for (const name of ['Men', 'Women', 'Casio']) {
                const link = tree.getByRole('link', {name, exact:true});
                const url = await link.getAttribute('href');
                await link.click();
                await page.waitForURL(origin + url);
                await open();
                assert.equal(await tree.locator('[aria-current="page"]').textContent(), name);
            }
            // Sorting and pagination remain Oscar GET requests with real result counts.
            await page.goto(origin + '/catalogue/');
            await page.locator('#id_sort_by').selectOption('price-asc');
            await page.waitForURL(url => url.searchParams.get('sort_by') === 'price-asc');
            assert.equal((await page.locator('.abdeen-result-count strong').textContent()).trim(), total);
            const prices = await page.locator('.abdeen-product-price').allTextContents();
            const numericPrices = prices.map(text => Number(text.replace(/[^\d.]/g, '')));
            assert.ok(numericPrices.length > 1);
            assert.deepEqual(numericPrices, [...numericPrices].sort((a,b) => a-b));
            await page.locator('.abdeen-pagination [rel="next"]').click();
            await page.waitForURL(url => url.searchParams.get('page') === '2' && url.searchParams.get('sort_by') === 'price-asc');
            assert.match(await page.locator('.abdeen-pagination [aria-current]').textContent(), /Page 2 of/);
            assert.equal(await page.locator('#id_sort_by').inputValue(), 'price-asc');
            await page.locator('.abdeen-pagination [rel="prev"]').click();
            await page.waitForURL(url => url.searchParams.get('page') === '1' && url.searchParams.get('sort_by') === 'price-asc');
            await overflow();
            if (width === 768) {
                await open();
                await page.setViewportSize({width:1440,height:1000});
                assert.equal(await dialog.isVisible(), false);
                assert.equal(await page.locator('.abdeen-catalogue-sidebar').isVisible(), true);
                assert.equal(await page.evaluate(() => document.documentElement.classList.contains('abdeen-filter-open')), false);
                assert.equal(await tree.count(), 1);
            }
            assert.deepEqual(errors, []);
            results.push({width, navigation:true, drawer:width<1024, activeAncestors:true, sorting:true, pagination:true, noOverflow:true});
            await context.close();
        }
        // Native disclosure and server-side sort submission remain usable without JS.
        const fallback = await browser.newContext({javaScriptEnabled:false, viewport:{width:320,height:1000}});
        const page = await fallback.newPage();
        await page.goto(origin + '/catalogue/');
        assert.equal(await page.locator('.abdeen-browse-navigation').getAttribute('open'), null);
        await page.locator('.abdeen-browse-navigation > summary').click();
        assert.equal(await page.getByRole('link', {name:'G-SHOCK',exact:true}).isVisible(),true);
        await page.locator('#id_sort_by').selectOption('title-asc');
        await page.getByRole('button',{name:'Apply',exact:true}).click();
        await page.waitForURL(url=>url.searchParams.get('sort_by')==='title-asc');
        await fallback.close();
        console.log(JSON.stringify({status:'PASS',results,noJavaScriptFallback:true},null,2));
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
