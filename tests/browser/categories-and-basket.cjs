// Run against messages_preview.py: a temporary DB copy with real Oscar routes.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = 'http://127.0.0.1:8020';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-editorial-screenshots';
fs.mkdirSync(screenshots, {recursive:true});
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome',headless:true});
 try {
  const results = [];
  for (const width of [1440,768,390,320]) {
   const context = await browser.newContext({viewport:{width,height:1000}});
   const page = await context.newPage();
   const errors = [];
   page.on('pageerror', error=>errors.push(error.message));
   await page.goto(origin);
   const cards = page.locator('.abdeen-category-card');
   assert.equal(await cards.count(),2);
   await page.locator('#categories').scrollIntoViewIfNeeded();
   await page.waitForFunction(()=>[...document.querySelectorAll('[data-category-image]')].every(img=>img.complete && img.naturalWidth>0));
   const links = await cards.evaluateAll(els=>els.map(el=>el.getAttribute('href')));
   const products = await page.locator('.abdeen-product-link').evaluateAll(els=>els.map(el=>el.getAttribute('href')));
   assert.deepEqual(await cards.locator('h3').allTextContents(),['Men','Women']);
   assert.equal(await page.locator('.abdeen-category-empty').isVisible(),false);
   const heights = await page.locator('.abdeen-category-visual').evaluateAll(els=>els.map(el=>el.getBoundingClientRect().height));
   // Copy must remain inside the visual, including at the narrowest viewport.
   const compositions = await cards.evaluateAll(els=>els.map(el=>{
    const image = el.querySelector('.abdeen-category-visual').getBoundingClientRect();
    const copy = el.querySelector('.abdeen-category-copy').getBoundingClientRect();
    return {inside:copy.left>=image.left && copy.right<=image.right && copy.top>=image.top && copy.bottom<=image.bottom,
     ratio:image.width/image.height, cardHeight:el.getBoundingClientRect().height, imageHeight:image.height};
   }));
   compositions.forEach(tile=>{assert.ok(tile.inside);assert.ok(Math.abs(tile.ratio-4/3)<0.01);assert.equal(tile.cardHeight,tile.imageHeight);});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
   assert.equal(await page.evaluate(()=>document.body.scrollWidth),width);
   await cards.first().focus();
   assert.notEqual(await cards.first().evaluate(el=>getComputedStyle(el).outlineStyle),'none');
   await cards.first().blur();
   await page.locator('#categories').screenshot({path:`${screenshots}/categories-${width}.png`});
   await cards.first().focus();
   await page.keyboard.press('Enter');
   await page.waitForURL(origin+links[0]);
   assert.equal((await page.goto(origin+links[1])).status(),200);
   // Actual product form, CSRF, redirect, Django message and persisted basket line.
   let availableProduct = false;
   for (const product of products) {
    await page.goto(origin+product);
    if (await page.locator('#add_to_basket_form').count()) {availableProduct=true;break;}
   }
   assert.ok(availableProduct,'At least one homepage product must be available for the live browser flow.');
   assert.equal(await page.locator('#add_to_basket_form [name="quantity"]').inputValue(),'1');
   await page.locator('#add_to_basket_form button[type="submit"]').click();
   await page.locator('.abdeen-basket-confirmation').waitFor();
   const success = page.locator('#messages .alert-success').filter({has:page.locator('.abdeen-basket-confirmation')});
   assert.match(await success.innerText(),/has been added to your (cart|basket)/);
   assert.equal(await success.getAttribute('role'),'status');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
   await success.screenshot({path:`${screenshots}/added-to-basket-${width}.png`});
   await success.locator('button[data-dismiss="alert"]').focus();
   await page.keyboard.press('Enter');
   await success.waitFor({state:'detached'});
   await page.goto(origin+'/basket/');
   assert.equal(await page.locator('[name="form-0-quantity"]').inputValue(),'1');
   // Broken images retain exactly the same visual area and real link.
   await page.route('**/abdeen/images/home/categories/{men,women}.jpg',route=>route.abort());
   await page.goto(origin);
   await page.locator('#categories').scrollIntoViewIfNeeded();
   await page.waitForFunction(()=>[...document.querySelectorAll('[data-category-image]')].every(img=>img.hidden));
   assert.deepEqual(await page.locator('.abdeen-category-visual').evaluateAll(els=>els.map(el=>el.getBoundingClientRect().height)),heights);
   assert.deepEqual(await cards.evaluateAll(els=>els.map(el=>el.getAttribute('href'))),links);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
   if(width===390) await page.locator('#categories').screenshot({path:`${screenshots}/categories-fallback-390.png`});
   await page.emulateMedia({reducedMotion:'reduce'});
   assert.equal(await cards.first().locator('img').evaluate(el=>getComputedStyle(el).transitionDuration),'0s');
   assert.deepEqual(errors,[]);
   results.push({width,categories:2,links,addToBasket:true,missingImages:true,overflow:false,errors});
   await context.close();
  }
  console.log(JSON.stringify({status:'PASS',results},null,2));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
