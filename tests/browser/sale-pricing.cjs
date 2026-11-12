// Run against sale_pricing_preview.py (disposable database/index).
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.STOREFRONT_ORIGIN || 'http://127.0.0.1:8025';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-sale-pricing';
fs.mkdirSync(screenshots, {recursive: true});

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true});
  try {
    const results = [];
    for (const width of [1440, 768, 390, 320]) {
      const context = await browser.newContext({viewport: {width, height: 1000}});
      await context.route('https://ajax.googleapis.com/**', route => route.abort());
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const fixture = await (await page.request.get(`${origin}/__sale_fixture__/`)).json();
      const checkOverflow = async () => {
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
        assert.equal(await page.evaluate(() => document.body.scrollWidth), width);
      };
      const checkPrice = async (container, sale) => {
        assert.match(await container.textContent(), /95 JOD/);
        assert.equal(await container.locator('.abdeen-price-regular').count(), sale ? 1 : 0);
        assert.equal(await container.locator('.abdeen-price-discount').count(), sale ? 1 : 0);
        if (sale) {
          assert.equal(await container.locator('.abdeen-price-regular').textContent(), '120 JOD');
          assert.match(await container.locator('.abdeen-price-discount').textContent(), /21% OFF/);
          assert.equal(await container.locator('.abdeen-price-regular').evaluate(el => getComputedStyle(el).textDecorationLine), 'line-through');
          const bounds = await container.boundingBox();
          for (const selector of ['.abdeen-price-regular', '.abdeen-price-current', '.abdeen-price-discount']) {
            const box = await container.locator(selector).boundingBox();
            assert.ok(box.x >= bounds.x - 1 && box.x + box.width <= bounds.x + bounds.width + 1, `${width}: ${selector} contained`);
            assert.ok(await container.locator(selector).evaluate(el => el.scrollWidth <= el.clientWidth + 1 || getComputedStyle(el).display === 'inline'));
          }
        }
      };
      assert.equal((await page.goto(origin + fixture.category)).status(), 200);
      await page.locator('.abdeen-product-card').first().waitFor();
      assert.equal(await page.locator('.abdeen-product-card').count(), 4);
      for (const product of fixture.products) {
        const card = page.locator('.abdeen-product-card').filter({hasText: `${product.label} preview watch`});
        await checkPrice(card.locator('.abdeen-product-price'), product.label === 'Markdown');
      }
      await checkOverflow();
      await page.screenshot({path: `${screenshots}/cards-${width}.png`, fullPage: true});
      for (const product of fixture.products) {
        assert.equal((await page.goto(origin + product.url)).status(), 200);
        await checkPrice(page.locator('.product_main .abdeen-detail-price'), product.label === 'Markdown');
        await checkOverflow();
        if (product.label === 'Markdown') {
          await page.screenshot({path: `${screenshots}/detail-${width}.png`, fullPage: true});
        }
      }
      assert.deepEqual(errors, []);
      results.push({width, cardAndDetail: 'PASS', variants: 4, overflow: false});
      await context.close();
    }
    console.log(JSON.stringify({status: 'PASS', results}, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
