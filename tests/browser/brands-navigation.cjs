// Local storefront verification. No catalogue writes. Optional manifest contains
// independently queried product IDs keyed by brand category + gender URL.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.CATALOGUE_ORIGIN || 'http://127.0.0.1:8000';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-brands';
const expected = process.env.BRAND_GENDER_MANIFEST && JSON.parse(fs.readFileSync(process.env.BRAND_GENDER_MANIFEST, 'utf8'));
fs.mkdirSync(screenshots, {recursive:true});
const openState = async (page, locator, open) => {
    await page.waitForFunction(({el, open}) => el.open === open && el.querySelector(':scope > summary').getAttribute('aria-expanded') === String(open),
        {el:await locator.elementHandle(), open});
};
const geometry = page => page.evaluate(() => {
    const rect = (selector, documentPosition = false) => {
        const r = document.querySelector(selector).getBoundingClientRect();
        return {x:r.x, y:r.y + (documentPosition ? scrollY : 0), width:r.width, height:r.height};
    };
    return {header:rect('[data-home-header]'), hero:rect('.campaign-hero', true), logo:rect('header .abdeen-logo'), actions:rect('.abdeen-header-actions')};
});
(async () => {
    const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome', headless:true});
    try {
        let genderLinks;
        for (const width of [320, 375, 390, 768, 1440]) {
            const context = await browser.newContext({viewport:{width,height:900}, hasTouch:width < 1024});
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', e => errors.push(e.message));
            assert.equal((await page.goto(origin + '/')).status(), 200);
            await page.evaluate(() => document.fonts.ready);
            if (await page.locator('[data-hero-controls]').count()) {
                await page.locator('[data-hero-controls]').waitFor({state:'visible'});
                // Stop the independent carousel timer before comparing layout.
                await page.locator('[data-hero-dot]').first().evaluate(el => el.focus({preventScroll:true}));
            }
            const mobile = width < 1024;
            const nav = page.locator(mobile ? '.abdeen-menu-panel' : '.abdeen-desktop-nav');
            const main = page.locator('.abdeen-mobile-menu > summary');
            const menu = nav.locator('[data-brands-menu]');
            const trigger = menu.locator(':scope > summary');
            const panel = menu.locator('.abdeen-brands-panel');
            const before = await geometry(page);
            assert.ok(before.header.height < 90, 'Original header height');
            assert.equal(await panel.isVisible(), false);
            await page.screenshot({path:`${screenshots}/${width}-closed.png`});
            if (mobile) await main.tap();
            assert.equal(await nav.getByRole('link', {name:'Shop',exact:true}).getAttribute('href'), '/catalogue/');
            assert.equal(await nav.getByRole('link', {name:'Home',exact:true}).getAttribute('href'), '/');
            await trigger.focus();
            await page.keyboard.press('Enter');
            await openState(page, menu, true);
            assert.deepEqual(await geometry(page), before, 'Opening Brands cannot move the header, hero, logo or actions');
            assert.equal(await menu.locator('ul').evaluateAll(els => els.every(el => getComputedStyle(el).listStyleType === 'none')), true);
            assert.equal(await trigger.evaluate(el => getComputedStyle(el).outlineWidth), '2px');
            const names = await menu.locator('.abdeen-brand-link').allTextContents();
            assert.ok(names.length > 0);
            assert.deepEqual(names, [...names].sort((a,b) => a.toLowerCase().localeCompare(b.toLowerCase())));
            if (!mobile) {
                assert.equal(await panel.evaluate(el => getComputedStyle(el).position), 'absolute');
                const box = await panel.boundingBox();
                const button = await trigger.boundingBox();
                assert.ok(box.y >= button.y + button.height - 1 && box.y < before.hero.y + before.hero.height);
                assert.ok(box.x >= 0 && box.x + box.width <= width);
                assert.equal(await panel.evaluate(el => el.contains(document.elementFromPoint(el.getBoundingClientRect().x + 20, el.getBoundingClientRect().y + 30))), true, 'Dropdown is above hero');
            }
            const child = menu.locator('[data-brand-children]').first();
            const toggle = child.locator(':scope > summary');
            if (mobile) await toggle.tap(); else await toggle.click();
            await openState(page, child, true);
            assert.ok(await child.locator('a').first().isVisible());
            assert.ok((await toggle.boundingBox()).height >= 44);
            const second = menu.locator('[data-brand-children]').nth(1);
            if (mobile) await second.locator(':scope > summary').tap(); else await second.locator(':scope > summary').click();
            await openState(page, second, true);
            assert.equal(await child.evaluate(el => el.open), true, 'Multiple brands can stay expanded');
            assert.deepEqual(await geometry(page), before);
            await menu.evaluate(el => Promise.all(el.getAnimations({subtree:true}).map(animation => animation.finished)));
            await page.evaluate(() => window.scrollTo(0, 0));
            await page.screenshot({path:`${screenshots}/${width}-expanded.png`});
            genderLinks = await menu.locator('[data-brand-children] a').evaluateAll(links => links.map(a => a.getAttribute('href')));
            if (expected) assert.deepEqual([...genderLinks].sort(), Object.keys(expected).filter(url => expected[url].length).sort());
            await toggle.click();
            await openState(page, child, false);
            await toggle.focus();
            await page.keyboard.press('Space');
            await openState(page, child, true);
            await page.keyboard.press('Tab');
            assert.ok(await child.locator('a').first().evaluate(el => el === document.activeElement));
            await page.keyboard.press('Escape');
            await openState(page, child, false);
            assert.equal(await toggle.evaluate(el => el === document.activeElement), true);
            await page.keyboard.press('Escape');
            await openState(page, menu, false);
            assert.equal(await panel.isVisible(), false);
            assert.equal(await trigger.evaluate(el => el === document.activeElement), true);
            if (mobile) await trigger.tap(); else await trigger.click();
            await menu.locator('.abdeen-brand-link').last().scrollIntoViewIfNeeded();
            const scroller = mobile ? nav : panel;
            assert.ok(await scroller.evaluate(el => el.scrollHeight > el.clientHeight && el.scrollTop > 0));
            assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth));
            await page.mouse.click(width - 2, 899);
            await openState(page, menu, false);
            if (mobile) await main.tap();
            await trigger.click();
            await page.setViewportSize({width:mobile ? 1440 : 390,height:900});
            await page.waitForFunction(el => !el.open, await (mobile ? page.locator('.abdeen-mobile-menu') : menu).elementHandle());
            assert.deepEqual(errors, []);
            await context.close();
            console.log(`PASS ${width}px: stable header/hero, overlay, multiple genders, keyboard, touch, dismissal, scrolling, resizing, no overflow`);
        }
        // Follow every gender route, including every results page, and compare
        // with real database IDs when the independent manifest was supplied.
        const context = await browser.newContext();
        const page = await context.newPage();
        for (const url of genderLinks) {
            const ids = [];
            let next = url;
            let pages = 0;
            while (next) {
                assert.ok(++pages < 100);
                assert.equal((await page.goto(new URL(next, origin).href)).status(), 200);
                ids.push(...await page.locator('.abdeen-catalogue-grid .abdeen-product-link').evaluateAll(links => links.map(a => Number(a.pathname.match(/_(\d+)\/$/)[1]))));
                const nextLink = page.locator('.abdeen-pagination [rel="next"]');
                next = await nextLink.count() ? new URL(await nextLink.getAttribute('href'), page.url()).href : null;
            }
            assert.ok(ids.length > 0, `No empty gender option: ${url}`);
            if (expected) assert.deepEqual(ids.sort((a,b) => a-b), expected[url], `Brand AND gender: ${url}`);
        }
        console.log(`PASS ${genderLinks.length} gender routes and all result pages${expected ? ' against database product IDs' : ''}`);
        await context.close();
        for (const width of [375, 1440]) {
            const fallback = await browser.newContext({javaScriptEnabled:false, viewport:{width,height:900}});
            const p = await fallback.newPage();
            await p.goto(origin + '/');
            if (width < 1024) await p.locator('.abdeen-mobile-menu > summary').click();
            const nav = p.locator(width < 1024 ? '.abdeen-menu-panel' : '.abdeen-desktop-nav');
            await nav.locator('[data-brands-menu] > summary').click();
            const child = nav.locator('[data-brand-children]').first();
            await child.locator(':scope > summary').click();
            const link = child.locator('a').first();
            const href = await link.getAttribute('href');
            const box = await link.boundingBox();
            const point = {x:box.x + 20, y:box.y + 20};
            assert.ok(await link.evaluate((el, point) => el.contains(document.elementFromPoint(point.x, point.y)), point));
            // Use a native pointer click; no injected animation-stability loop.
            await p.mouse.click(point.x, point.y);
            await p.waitForURL(origin + href);
            assert.ok(p.url().endsWith(href));
            assert.ok(await p.locator('.abdeen-catalogue-grid .abdeen-product-card').count());
            await fallback.close();
        }
        console.log('PASS desktop and mobile JavaScript-disabled gender navigation');
    } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode=1;});
