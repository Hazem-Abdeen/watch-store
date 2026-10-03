// Use product_detail_preview.py: every purchase and fixture uses a disposable DB.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.STOREFRONT_ORIGIN || 'http://127.0.0.1:8021';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-detail-qa';
fs.mkdirSync(screenshots, {recursive: true});
(async () => {
 const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
 const results = [];
 try {
  for (const width of [1440, 768, 390, 320]) {
   const context = await browser.newContext({viewport: {width, height: 1000}});
   await context.route('https://ajax.googleapis.com/**', route => route.abort());
   const page = await context.newPage();
   page.setDefaultTimeout(15000);
   const errors = [];
   page.on('pageerror', error => errors.push(error.message));
   const urls = await (await context.request.get(origin + '/__detail_fixture__/')).json();
   const check = async () => {
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `overflow ${width}`);
    const text = await page.locator('body').innerText();
    assert.doesNotMatch(text, /\d+ available|\d+ items? left|Low stock|Tax included|a maximum of \d+ can be bought|Add to wish list|Customer Reviews|Write a review|Price & availability details/);
    assert.equal(await page.locator('.star-rating, .btn-wishlist, a[href*="wishlists"]').count(), 0);
   };
   for (const name of ['out_of_stock', 'no_description', 'mixed', 'unavailable', 'in_stock']) {
    await page.goto(origin + urls[name]);
    await page.evaluate(() => document.fonts.ready);
    await check();
    assert.equal(await page.getByRole('heading', {name: 'Product Details', exact: true}).count(), 0);
    const disclosure = page.locator('[data-specifications]');
    if (await disclosure.count()) {
     const toggle = disclosure.locator('summary');
     const specifications = page.locator('#product-specifications');
     assert.equal(await disclosure.getAttribute('open'), null);
     assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
     assert.equal(await toggle.getAttribute('aria-controls'), 'product-specifications');
     assert.equal(await specifications.getAttribute('aria-labelledby'), await toggle.getAttribute('id'));
     assert.equal(await specifications.isVisible(), false);
     await toggle.click();
     await page.waitForFunction(() => document.querySelector('[data-specifications] summary').getAttribute('aria-expanded') === 'true');
     assert.equal(await specifications.isVisible(), true);
     assert.equal(await specifications.locator('.abdeen-detail-specs').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), width >= 1024 ? 2 : 1);
     await check();
     await page.screenshot({path: `${screenshots}/${name}-specifications-${width}.png`, fullPage: true});
     await toggle.click();
     await page.waitForFunction(() => document.querySelector('[data-specifications] summary').getAttribute('aria-expanded') === 'false');
     await toggle.focus();
     await page.keyboard.press('Enter');
     await page.waitForFunction(() => document.querySelector('[data-specifications] summary').getAttribute('aria-expanded') === 'true');
     await page.keyboard.press('Space');
     await page.waitForFunction(() => document.querySelector('[data-specifications] summary').getAttribute('aria-expanded') === 'false');
    }
    const image = page.locator('[data-gallery-image]');
    await image.evaluate(img => img.complete ? Promise.resolve() : new Promise(resolve => img.onload = resolve));
    assert.ok(await image.evaluate(img => img.naturalWidth > 0));
    assert.equal(await page.locator('.abdeen-detail-edit').count(), 0);
    if (name === 'out_of_stock' || name === 'unavailable') {
     assert.equal(await page.locator('#add_to_basket_form').count(), 0);
     assert.match(await page.locator('.abdeen-detail-pricing').innerText(), name === 'out_of_stock' ? /Out of stock/ : /Unavailable/);
    } else {
     assert.equal(await page.locator('#add_to_basket_form').count(), 1);
     assert.match(await page.locator('.price_color').first().innerText(), /^\d+(\.\d+)? JOD$/);
    }
    if (name === 'no_description') {
     assert.equal(await page.locator('#product_description').count(), 0);
     assert.equal(await page.locator('.abdeen-detail-sku').count(), 0);
    }
    if (name === 'mixed') {
     assert.match(await page.locator('.abdeen-detail-description').innerText(), /A considered design/);
     await disclosure.locator('summary').click();
     assert.match(await page.locator('.abdeen-detail-specs').innerText(), /Two Years \(International\)/);
     await disclosure.locator('summary').click();
     const thumbs = page.locator('[data-gallery-thumbnail]');
     await thumbs.first().focus();
     await page.keyboard.press('ArrowRight');
     assert.equal(await thumbs.nth(1).getAttribute('aria-current'), 'true');
     assert.equal(await page.locator('[data-gallery-link]').evaluate(el => el.href), await thumbs.nth(1).evaluate(el => el.href));
     await page.keyboard.press('Home');
    }
    if (name === 'in_stock') {
     assert.equal(await page.locator('#product_description').count(), 0);
     assert.ok(await page.locator('.abdeen-detail-sku').count());
     assert.match(await page.locator('.availability').first().innerText(), /^In stock, ready to ship$/);
     assert.equal(await page.locator('.abdeen-detail-shipping a').count(), 0);
    }
    if (name === 'unavailable') assert.match(await image.getAttribute('src'), /watch-placeholder.svg$/);
    await page.locator('.abdeen-footer').scrollIntoViewIfNeeded();
    await page.waitForFunction(() => [...document.querySelectorAll('img')].every(img => img.complete));
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({path: `${screenshots}/${name}-${width}.png`, fullPage: true});
   }
   const recently = page.locator('.abdeen-recently-viewed');
   const recommended = page.locator('.abdeen-recommendations');
   const recommendationLinks = await recommended.locator('.abdeen-product-link').evaluateAll(links => links.map(link => link.getAttribute('href')));
   assert.ok(recommendationLinks.length > 0 && recommendationLinks.length <= 4);
   assert.equal(new Set(recommendationLinks).size, recommendationLinks.length);
   assert.ok(!recommendationLinks.includes(urls.in_stock));
   assert.equal(await recommended.locator('button, .product_pod, .star-rating').count(), 0);
   assert.equal(await recommended.locator('.abdeen-product-card').first().evaluate(el => getComputedStyle(el).borderTopWidth), '0px');
   assert.ok(await recommended.evaluate(el => Boolean(el.compareDocumentPosition(document.querySelector('.abdeen-recently-viewed')) & Node.DOCUMENT_POSITION_FOLLOWING)));
   assert.equal(await recently.locator('.abdeen-product-card').count(), 4);
   assert.equal(await recently.locator('button, .product_pod, .star-rating').count(), 0);
   assert.equal(await recently.locator('.abdeen-product-card').first().evaluate(el => getComputedStyle(el).borderTopWidth), '0px');
   assert.equal(await recently.locator('.abdeen-section-heading').evaluate(el => getComputedStyle(el).textAlign), 'center');
   const gridColumns = await recently.locator('.abdeen-product-grid').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length);
   assert.equal(gridColumns, width >= 1024 ? 4 : width >= 640 ? 3 : 2);
   const recentLink = recently.locator('.abdeen-product-link').first();
   const recentURL = await recentLink.getAttribute('href');
   await recentLink.hover();
   await page.waitForFunction(() => getComputedStyle(document.querySelector('.abdeen-recently-viewed img')).transform !== 'none');
   await recentLink.focus();
   await page.keyboard.press('Enter');
   await page.waitForURL(origin + recentURL);
   await page.goto(origin + urls.in_stock);
   assert.equal(await page.locator('#id_quantity').inputValue(), '1');
   assert.equal(await page.locator('[data-quantity-step="-1"]').isDisabled(), true);
   assert.equal(await page.locator('#id_quantity').getAttribute('max'), null);
   await page.getByRole('button', {name: 'Increase quantity'}).focus();
   await page.keyboard.press('Enter');
   assert.equal(await page.locator('#id_quantity').inputValue(), '2');
   await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
   await page.waitForLoadState('networkidle');
   assert.match(await page.locator('.abdeen-detail-purchase').innerText(), /requested quantity is not available/);
   assert.equal(await page.locator('#id_quantity').inputValue(), '2');
   await check();
   await page.getByRole('button', {name: 'Decrease quantity'}).click();
   assert.equal(await page.locator('#id_quantity').inputValue(), '1');
   await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
   await page.waitForLoadState('networkidle');
   await page.goto(origin + '/basket/');
   await check();
   assert.equal(await page.locator('.abdeen-basket-line').count(), 1);
   assert.equal(await page.locator('input[name="form-0-quantity"]').getAttribute('max'), null);
   await page.locator('input[name="form-0-quantity"]').fill('999');
   await Promise.all([
    page.waitForResponse(response => response.url().includes('/basket/') && response.request().method() === 'POST'),
    page.locator('.abdeen-basket-update').click(),
   ]);
   await page.waitForFunction(() => document.querySelector('.abdeen-basket-controls .error-block'));
   assert.match(await page.locator('.abdeen-basket-controls .error-block').innerText(), /requested quantity is not available/);
   await check();
   await page.goto(origin + urls.mixed);
   await page.getByRole('button', {name: 'Increase quantity'}).click();
   assert.equal(await page.locator('#id_quantity').inputValue(), '2');
   await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
   await page.waitForLoadState('networkidle');
   await page.goto(origin + '/basket/');
   assert.equal(await page.locator('.abdeen-basket-line').count(), 2);
   assert.ok((await page.locator('input[name$="-quantity"]').evaluateAll(inputs => inputs.map(input => input.value))).includes('2'));
   for (const role of ['customer', 'staff', 'superuser']) {
    await context.request.get(origin + '/__detail_fixture__/?role=' + role);
    await page.goto(origin + urls.in_stock);
    await check();
    assert.equal(await page.locator('.abdeen-detail-edit').count(), role === 'customer' ? 0 : 1);
   }
   assert.deepEqual(errors, []);
   results.push({width, states: 5, specifications: true, recommendations: true, recentlyViewed: true, addToCart: true, quantity: true, gallery: true, permissions: true, overflow: false});
   await context.close();
  }
  const noJS = await browser.newContext({javaScriptEnabled: false});
  const urls = await (await noJS.request.get(origin + '/__detail_fixture__/')).json();
  const page = await noJS.newPage();
  await page.goto(origin + urls.in_stock);
  const nativeDisclosure = page.locator('[data-specifications]');
  assert.equal(await nativeDisclosure.getAttribute('open'), null);
  await nativeDisclosure.locator('summary').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#product-specifications').isVisible(), true);
  await page.keyboard.press('Space');
  assert.equal(await page.locator('#product-specifications').isVisible(), false);
  assert.equal(await page.locator('#id_quantity').isVisible(), true);
  assert.equal(await page.getByRole('button', {name: 'Increase quantity'}).count(), 0);
  await page.locator('#id_quantity').fill('1');
  await page.getByRole('button', {name: 'Add to Cart', exact: true}).click();
  await page.goto(origin + '/basket/');
  assert.equal(await page.locator('.abdeen-basket-line').count(), 1);
  await noJS.close();
  console.log(JSON.stringify({status: 'PASS', results}, null, 2));
 } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});
