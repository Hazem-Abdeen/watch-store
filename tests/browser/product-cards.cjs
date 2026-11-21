// Run against messages_preview.py, which uses a disposable copy of the database.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.STOREFRONT_ORIGIN || 'http://127.0.0.1:8020';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-product-cards';
fs.mkdirSync(screenshots, {recursive: true});
(async () => {
 const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
 try {
  const results = [];
  for (const width of [1440, 768, 390, 320]) {
   const context = await browser.newContext({viewport: {width, height: 1000}});
   // Exercise the bundled fallback without depending on the public jQuery CDN.
   await context.route('https://ajax.googleapis.com/**', route => route.abort());
   const page = await context.newPage();
   const errors = [];
   page.on('pageerror', error => errors.push(error.message));
   assert.equal((await page.goto(origin)).status(), 200);
   const categoryLinks = await page.locator('.abdeen-category-card').evaluateAll(els => els.map(el => el.getAttribute('href')));
   assert.ok(categoryLinks.length);
   async function checkGrid(selector, columns, label) {
    const grid = page.locator(selector);
    await grid.scrollIntoViewIfNeeded();
    const cards = grid.locator('.abdeen-product-card');
    assert.ok(await cards.count(), `${label} has real products`);
    if (selector !== '.abdeen-catalogue-grid' && width >= 640) columns = Math.min(columns, await cards.count());
    const isCarousel = await grid.evaluate(el => el.classList.contains('abdeen-carousel-track'));
    const gridColumns = await grid.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length);
    if (isCarousel) {
     assert.equal(await grid.evaluate(el => getComputedStyle(el).gridAutoFlow), 'column');
     const rows = await cards.evaluateAll(els => new Set(els.map(el => el.offsetTop)).size);
     assert.equal(rows, 1, label);
    } else assert.equal(gridColumns, columns, label);
    const styles = await cards.evaluateAll(els => els.map(el => ({
     border: getComputedStyle(el).borderTopWidth, background: getComputedStyle(el).backgroundColor,
     links: el.querySelectorAll('a').length, buttons: el.querySelectorAll('button, form').length,
     href: el.querySelector('a').getAttribute('href'), price: el.querySelector('.abdeen-product-price').textContent,
    })));
    for (const item of styles) {
     assert.equal(item.border, '0px'); assert.equal(item.background, 'rgba(0, 0, 0, 0)');
     assert.equal(item.links, 1); assert.equal(item.buttons, 0); assert.ok(item.href.startsWith('/catalogue/'));
     assert.match(item.price, /\d+(?:\.\d+)? JOD|Price unavailable/);
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width, `${label} no overflow`);
    assert.equal(await page.evaluate(() => document.body.scrollWidth), width, `${label} body no overflow`);
    const link = cards.first().locator('a');
    await page.keyboard.press('Tab');
    await link.focus();
    assert.notEqual(await link.evaluate(el => getComputedStyle(el).outlineStyle), 'none');
    await link.blur();
    // Load off-screen lazy images before capturing the entire grid.
    await grid.locator('img').evaluateAll(images => images.forEach(img => { img.loading = 'eager'; }));
    await page.waitForFunction(selector => [...document.querySelectorAll(`${selector} img`)].every(img => img.complete && img.naturalWidth > 0), selector);
    await grid.screenshot({path: `${screenshots}/${label}-${width}.png`, style: '.abdeen-header { visibility: hidden !important; }'});
   }
   await checkGrid('#best-sellers-grid', width >= 1024 ? 4 : width >= 640 ? 3 : 2, 'best-sellers');
   assert.equal(await page.locator('[data-home-filter], [data-home-filters]').count(), 0);
   await checkGrid('#new-arrivals .abdeen-carousel-track', width >= 1024 ? 4 : width >= 640 ? 3 : 2, 'new-arrivals');
   const productLink = page.locator('#best-sellers .abdeen-product-link').first();
   const productURL = await productLink.getAttribute('href');
   await productLink.focus(); await page.keyboard.press('Enter'); await page.waitForURL(origin + productURL);
   assert.ok(await page.locator('.abdeen-detail').count());
   await page.goto(origin + '/catalogue/');
   await checkGrid('.abdeen-catalogue-grid', width >= 1200 ? 4 : width >= 1024 ? 3 : 2, 'catalogue');
   const firstPage = await page.locator('.abdeen-product-link').first().getAttribute('href');
   await page.locator('#id_sort_by').selectOption('price-asc');
   await page.waitForURL(/sort_by=price-asc/);
   const prices = await page.locator('.abdeen-product-price').allTextContents();
   const numbers = prices.map(text => Number(text.trim().split(' ')[0]));
   assert.deepEqual(numbers, [...numbers].sort((a,b) => a-b));
   if (await page.locator('.abdeen-pagination a[rel="next"]').count()) {
    await page.locator('.abdeen-pagination a[rel="next"]').click();
    await page.waitForURL(/page=2/); assert.ok(page.url().includes('sort_by=price-asc'));
    assert.notEqual(await page.locator('.abdeen-product-link').first().getAttribute('href'), firstPage);
   }
   for (let i = 0; i < categoryLinks.length; i++) {
    await page.goto(origin + categoryLinks[i]);
    await checkGrid('.abdeen-catalogue-grid', width >= 1200 ? 4 : width >= 1024 ? 3 : 2, `category-${i + 1}`);
   }
   await page.locator('summary[aria-label="Search watches"]').click();
   await page.locator('#home-search').fill('Casio');
   await page.locator('#home-search').press('Enter');
   await page.waitForURL(/\/search\/\?q=Casio/);
   assert.ok(await page.locator('.product_pod').count());
   await page.goto(origin);
   await page.emulateMedia({reducedMotion: 'reduce'});
   const img = page.locator('.abdeen-product-image img').first();
   assert.equal(await img.evaluate(el => getComputedStyle(el).transitionDuration), '0s');
   assert.deepEqual(errors, []);
   results.push({width, homepageRanges: true, catalogue: true, categories: categoryLinks.length, sorting: true, pagination: true, search: true, overflow: false});
   await context.close();
  }
  console.log(JSON.stringify({status: 'PASS', results}, null, 2));
 } finally {await browser.close();}
})().catch(error => {console.error(error); process.exit(1);});
