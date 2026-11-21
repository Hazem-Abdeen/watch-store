// Run carousels_preview.py first: all test data lives in a disposable DB copy.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.STOREFRONT_ORIGIN || 'http://127.0.0.1:8026';
const original = process.env.ORIGINAL_STOREFRONT_ORIGIN || 'http://127.0.0.1:8027';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-carousel-dots';
fs.mkdirSync(screenshots, {recursive: true});
const widths = [320, 375, 390, 768, 1024, 1440];
const perPage = width => width >= 1024 ? 4 : width >= 768 ? 3 : 2;

async function assertWidth(page, width) {
    const metrics = await page.evaluate(() => ({
        client: document.documentElement.clientWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
        inner: innerWidth,
        visual: visualViewport.width,
        scale: visualViewport.scale,
    }));
    assert.equal(metrics.client, width);
    assert.equal(metrics.document, width, 'document must not expand from off-screen sale labels');
    assert.equal(metrics.body, width);
    assert.equal(metrics.inner, width, 'mobile layout viewport must not expand/zoom out');
    assert.ok(Math.abs(metrics.visual - width) < 1);
    assert.ok(Math.abs(metrics.scale - 1) < .01);
    return metrics;
}

async function atPage(track, index, total, size) {
    const first = Math.max(0, Math.min(index * size, total - size));
    await track.page().waitForFunction(({id, first, index}) => {
        const el = document.getElementById(id);
        const step = el.firstElementChild.getBoundingClientRect().width + parseFloat(getComputedStyle(el).columnGap);
        const active = el.parentElement.querySelector('.abdeen-carousel-dots [aria-current="true"]');
        return Math.abs(el.scrollLeft - first * step) < 2 && (!active || Number(active.dataset.page) === index);
    }, {id: await track.getAttribute('id'), first, index});
}

async function loadedImages(section) {
    await section.locator('img').evaluateAll(images => images.forEach(image => { image.loading = 'eager'; }));
    await section.page().waitForFunction(selector => [...document.querySelectorAll(selector + ' img')]
        .every(image => image.complete && image.naturalWidth > 0), '#' + await section.getAttribute('id'));
    await section.page().evaluate(() => document.fonts.ready);
}

async function touchSwipe(context, track, vertical = false) {
    await track.scrollIntoViewIfNeeded();
    const box = await track.boundingBox();
    const cdp = await context.newCDPSession(track.page());
    const x = box.x + box.width * .85;
    const y = box.y + Math.min(180, box.height / 2);
    await cdp.send('Input.dispatchTouchEvent', {type: 'touchStart', touchPoints: [{x, y}]});
    for (let i = 1; i <= 10; i++) {
        await cdp.send('Input.dispatchTouchEvent', {type: 'touchMove', touchPoints: [{
            x: vertical ? x : x - box.width * .07 * i,
            y: vertical ? y - 12 * i : y,
        }]});
    }
    await cdp.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
    await cdp.detach();
}

(async () => {
    const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
    const results = [];
    try {
        for (const width of widths) {
            // isMobile is essential: viewport-only desktop emulation missed the shrink bug.
            const context = await browser.newContext({viewport: {width, height: 1000},
                isMobile: width < 768, hasTouch: true, reducedMotion: 'reduce'});
            await context.route('https://ajax.googleapis.com/**', route => route.abort());
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            await page.goto(original);
            assert.ok(await page.locator('.abdeen-carousel .sr-only').count(), 'actual sale-price regression fixture');
            const actualMetrics = await assertWidth(page, width);
            for (const id of ['best-sellers', 'new-arrivals']) {
                await loadedImages(page.locator('#' + id));
                await page.locator('#' + id).screenshot({path: `${screenshots}/actual-${id}-${width}.png`});
            }
            await page.screenshot({path: `${screenshots}/actual-home-${width}.png`, fullPage: true});

            await page.goto(origin);
            const size = perPage(width);
            for (const id of ['best-sellers', 'new-arrivals']) {
                const carousel = page.locator(`[data-carousel="${id}"]`);
                const track = carousel.locator('.abdeen-carousel-track');
                const cards = track.locator('article');
                const dots = carousel.locator('.abdeen-carousel-dots button');
                const pages = Math.ceil(19 / size);
                assert.equal(await cards.count(), 8);
                assert.equal(await dots.count(), pages, 'dots include unloaded products');
                assert.equal(await dots.first().getAttribute('aria-current'), 'true');
                assert.equal(await dots.first().getAttribute('aria-label'), `Go to products 1–${size}`);
                assert.equal(await carousel.locator('[data-carousel-next], [data-carousel-prev]').count(), 0);
                assert.equal(await track.evaluate(el => getComputedStyle(el).scrollbarWidth), 'none');
                assert.equal(await track.evaluate(el => getComputedStyle(el).scrollBehavior), 'auto');
                await track.scrollIntoViewIfNeeded();
                await loadedImages(page.locator('#' + id));
                const initialHeight = (await track.boundingBox()).height;
                const layout = await cards.evaluateAll(els => els.map(el => ({
                    top: el.offsetTop, height: el.offsetHeight, width: el.getBoundingClientRect().width,
                })));
                assert.ok(layout.every(card => card.top === layout[0].top && card.height === layout[0].height));
                const trackWidth = await track.evaluate(el => el.clientWidth);
                const gap = await track.evaluate(el => parseFloat(getComputedStyle(el).columnGap));
                assert.ok(Math.abs(layout[0].width * size + gap * (size - 1) - trackWidth) < 1, 'complete cards fit the viewport');
                assert.ok(await carousel.locator('.abdeen-product-image img').first().evaluate(el =>
                    Math.abs(el.clientWidth - el.clientHeight) < 1 && getComputedStyle(el).objectFit === 'contain'));
                await carousel.screenshot({path: `${screenshots}/fixture-${id}-${width}.png`});

                if (width < 768) {
                    const url = page.url();
                    await touchSwipe(context, track);
                    await atPage(track, 1, 19, size);
                    assert.equal(page.url(), url, 'swiping never opens a product');
                } else {
                    const box = await track.boundingBox();
                    await page.mouse.move(box.x + box.width / 2, box.y + 80);
                    await page.mouse.wheel(trackWidth, 0);
                    await atPage(track, 1, 19, size);
                }
                assert.equal(await dots.nth(1).getAttribute('aria-current'), 'true');
                await dots.last().click();
                await atPage(track, pages - 1, 19, size);
                assert.equal(await cards.count(), 19, 'all products beyond eight can be selected directly');
                assert.equal(await dots.last().getAttribute('aria-current'), 'true');
                assert.equal(await dots.last().getAttribute('aria-label'), `Go to products ${20 - size}–19`);
                assert.ok(Math.abs((await track.boundingBox()).height - initialHeight) < 1, 'later long titles do not grow the track');
                assert.ok(await cards.last().evaluate(el => el.getBoundingClientRect().right <= el.parentElement.getBoundingClientRect().right + 2));
                await assertWidth(page, width);
                if (id === 'best-sellers') {
                    assert.equal(await page.locator('#new-arrivals-grid').evaluate(el => el.scrollLeft), 0);
                    assert.equal(await page.locator('#new-arrivals-grid article').count(), 8);
                }
                await track.focus();
                await page.keyboard.press('Home');
                await atPage(track, 0, 19, size);
                await page.keyboard.press('ArrowRight');
                await atPage(track, 1, 19, size);
                await dots.nth(1).focus();
                await page.keyboard.press('End');
                await atPage(track, pages - 1, 19, size);
                await page.keyboard.press('Home');
                await atPage(track, 0, 19, size);
                if (width < 768) {
                    const before = await page.evaluate(() => scrollY);
                    await touchSwipe(context, track, true);
                    await page.waitForFunction(before => Math.abs(scrollY - before) > 20, before);
                    await atPage(track, 0, 19, size);
                }
            }
            await page.setViewportSize({width: 1440, height: 1000});
            await page.waitForFunction(() => document.querySelector('.abdeen-carousel-dots').children.length === 5);
            await assertWidth(page, 1440);
            await page.setViewportSize({width, height: 1000});
            await page.waitForFunction(size => document.querySelector('.abdeen-carousel-dots').children.length === Math.ceil(19 / size), size);
            await assertWidth(page, width);
            assert.deepEqual(errors, []);
            const link = page.locator('#best-sellers .abdeen-product-link').first();
            const href = await link.getAttribute('href');
            await link.click();
            await page.waitForURL(origin + href);
            results.push({width, cardsPerPage: size, actualMetrics, result: 'passed'});
            console.log(`${width}px: actual viewport, both carousels, dots, swipes/trackpad, active state, pagination, height, keyboard, resize and links passed`);
            await context.close();
        }

        const page = await browser.newPage({viewport: {width: 390, height: 1000}, isMobile: true, hasTouch: true, reducedMotion: 'reduce'});
        await page.route('https://ajax.googleapis.com/**', route => route.abort());
        let fail = true;
        await page.route('**/?carousel=**', route => fail ? route.abort() : route.continue());
        await page.goto(origin);
        const carousel = page.locator('[data-carousel="best-sellers"]');
        await carousel.locator('.abdeen-carousel-dots button').last().click();
        await page.waitForFunction(() => !document.querySelector('.abdeen-carousel-retry').hidden);
        fail = false;
        await carousel.locator('.abdeen-carousel-retry').click();
        await atPage(carousel.locator('.abdeen-carousel-track'), 9, 19, 2);
        assert.equal(await carousel.locator('article').count(), 19);
        assert.ok(await carousel.locator('.abdeen-carousel-retry').isHidden());

        for (const width of [320, 1440]) {
            await page.setViewportSize({width, height: 1000});
            for (const count of [1, 2, 3, 4, 8]) {
                await page.route(origin + '/', async route => {
                    const response = await route.fetch();
                    let body = (await response.text()).replace(/data-next-page="2"/g, 'data-next-page=""')
                        .replace(/data-total="19"/g, `data-total="${count}"`);
                    body = body.replace(/(<div class="abdeen-carousel-track"[^>]*>)([\s\S]*?)(\n {4}<\/div>)/g,
                        (match, start, content, end) => {
                            let index = 0;
                            return start + content.replace(/<article class="abdeen-product-card"[\s\S]*?<\/article>/g,
                                article => index++ < count ? article : '') + end;
                        });
                    await route.fulfill({response, body});
                });
                await page.goto(origin);
                for (const id of ['best-sellers', 'new-arrivals']) {
                    const c = page.locator(`[data-carousel="${id}"]`);
                    assert.equal(await c.locator('article').count(), count);
                    const pages = Math.ceil(count / perPage(width));
                    assert.equal(await c.locator('.abdeen-carousel-dots').isHidden(), pages === 1);
                    assert.equal(await c.locator('.abdeen-carousel-dots button').count(), pages === 1 ? 0 : pages);
                }
                await assertWidth(page, width);
                await page.unroute(origin + '/');
            }
        }
        await page.emulateMedia({reducedMotion: 'no-preference'});
        await page.goto(origin);
        assert.equal(await carousel.locator('.abdeen-carousel-track').evaluate(el => getComputedStyle(el).scrollBehavior), 'smooth');
        await carousel.locator('.abdeen-carousel-dots button').nth(1).click();
        await atPage(carousel.locator('.abdeen-carousel-track'), 1, 19, 4);
        console.log('Retry, one/two/three/four/eight products, unnecessary controls and smooth/reduced-motion behavior passed');
        fs.writeFileSync(`${screenshots}/results.json`, JSON.stringify(results, null, 2));
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exit(1);});
