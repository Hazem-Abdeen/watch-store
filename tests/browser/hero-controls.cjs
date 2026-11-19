// Run against tests/browser/hero_preview.py; Playwright is an optional test dependency.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome', headless:true});
 try {
 const page = await browser.newPage();
 const errors = [];
 page.on('pageerror', e => errors.push(e.message));
 const selected = () => page.locator('[data-hero-dot][aria-current="true"]').getAttribute('aria-label');
 const results = [];
 const checkArtworkSpacing = async () => {
  const bounds = await page.evaluate(() => {
   const rect = selector => document.querySelector(selector).getBoundingClientRect();
   const image = rect('[data-hero-slide]:not([hidden]) img');
   return {headerBottom: rect('header').bottom, imageTop: image.top,
    imageBottom: image.bottom, dotsTop: rect('.campaign-hero-dots').top};
  });
  assert.ok(Math.abs(bounds.imageTop - bounds.headerBottom) < 1,
   'Artwork must start immediately below the header, even with taller hidden slides');
  assert.ok(Math.abs(bounds.dotsTop - bounds.imageBottom) < 1,
   'Dots must immediately follow the artwork without reserved blank space');
 };
 for (const width of [1920,1440,768,390,320]) {
  await page.setViewportSize({width,height:900});
  await page.goto('http://127.0.0.1:8017/');
  await page.getByRole('button',{name:'Next campaign',exact:true}).waitFor({state:'visible'});
  await page.locator('[data-hero-slide]:visible img').evaluate(img => img.decode());
  const measurements = await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth, body:document.body.scrollWidth, hero:document.querySelector('#hero').getBoundingClientRect().width, source:document.querySelector('[data-hero-slide] img').currentSrc}));
  assert.equal(measurements.document, width);
  assert.equal(measurements.body, width);
  assert.equal(measurements.hero, width);
  const imageFit = await page.locator('[data-hero-slide]:visible img').evaluate(img => ({
   fit: getComputedStyle(img).objectFit,
   width: img.clientWidth, height: img.clientHeight,
   naturalRatio: img.naturalHeight / img.naturalWidth,
  }));
  assert.equal(imageFit.fit, 'contain', 'The complete artwork must be visible');
  assert.equal(imageFit.width, width, 'Artwork must fill the section horizontally');
  assert.ok(Math.abs(imageFit.height - width * imageFit.naturalRatio) < 1,
   'Artwork must keep its natural proportions without cropping or letterboxing');
  assert.equal(measurements.source.includes('Mobile'), width < 768);
  await checkArtworkSpacing();
  const art = await page.locator('[data-hero-slide]:visible picture').boundingBox();
  const arrow = await page.locator('[data-hero-next]').boundingBox();
  const dotsBox = await page.locator('.campaign-hero-dots').boundingBox();
  assert.ok(Math.abs(arrow.y + arrow.height / 2 - (art.y + art.height / 2)) < 1);
  assert.ok(Math.abs(dotsBox.y - (art.y + art.height)) < 1);
  assert.equal(await page.locator('.abdeen-nav-row').evaluate(el=>el.getBoundingClientRect().height),width>=1024?72:64);
  assert.equal((await page.locator('[data-hero-controls]').innerText()).trim(),'');
  assert.equal(await page.locator('[data-hero-rotation]').count(),0);
  await page.getByRole('button',{name:'Next campaign',exact:true}).click();
  await page.getByRole('button',{name:'Next campaign',exact:true}).waitFor({state:'visible'});
  await page.locator('[data-hero-slide]:visible img').evaluate(img => img.decode());
  assert.equal(await page.locator('[data-hero-slide]:visible').count(),1);
  assert.equal(await page.getByRole('link',{name:'Explore watches',exact:true}).getAttribute('href'),'/catalogue/');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth),width);
  await checkArtworkSpacing();
  const secondSource = await page.locator('[data-hero-slide]:visible img').evaluate(img => img.currentSrc);
  assert.ok(secondSource.includes('Second_campaign'), 'Missing mobile artwork must fall back to desktop');
  await page.getByRole('button',{name:'Previous campaign',exact:true}).click();
  assert.match(await selected(),/campaign 1/);
  assert.equal(await page.locator('[data-hero-slide][hidden]').evaluate(el=>el.inert),true);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  const focusStyle=await page.locator('[data-hero-previous]').evaluate(el=>getComputedStyle(el).outlineStyle);
  assert.notEqual(focusStyle,'none');
  // Header panels still fit and operate cleanly at every width.
  if (await page.getByLabel('Search watches',{exact:true}).count()) {
  await page.getByLabel('Search watches',{exact:true}).click();
  assert.equal(await page.locator('#home-search').isVisible(),true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#home-search').isVisible(),false);
  }
  if(width<1024) {
   await page.getByLabel('Main menu',{exact:true}).click();
   assert.equal(await page.getByRole('navigation',{name:'Mobile navigation'}).isVisible(),true);
   await page.keyboard.press('Escape');
  }
  results.push(measurements);
 }
 await page.setViewportSize({width:1440,height:900});
 await page.mouse.move(0,0);
 await page.clock.install();
 await page.goto('http://127.0.0.1:8017/');
 assert.match(await selected(), /campaign 1/);
 await page.getByRole('button',{name:'Next campaign',exact:true}).waitFor({state:'visible'});
 await page.clock.fastForward(6100);
 assert.match(await selected(), /campaign 2/);
 await page.locator('#hero').hover();
 await page.clock.fastForward(7000);
 assert.match(await selected(), /campaign 2/);
 await page.mouse.move(0,0);
 await page.clock.fastForward(6100);
 assert.match(await selected(), /campaign 1/);
 await page.clock.fastForward(6100);
 assert.match(await selected(), /campaign 2/);
 await page.getByRole('button',{name:'Previous campaign',exact:true}).focus();
 await page.clock.fastForward(7000);
 assert.match(await selected(), /campaign 2/);
 await page.keyboard.press('ArrowLeft');
 assert.match(await selected(), /campaign 1/);
 await page.keyboard.press('End');
 assert.match(await selected(), /campaign 2/);
 await page.keyboard.press('Home');
 assert.match(await selected(), /campaign 1/);
 await page.keyboard.press('Enter');
 assert.match(await selected(), /campaign 2/);
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.reload();
 await page.getByRole('button',{name:'Next campaign',exact:true}).waitFor({state:'visible'});
 await page.clock.fastForward(20000);
 assert.match(await selected(), /campaign 1/);
 assert.equal(await page.locator('[data-hero-rotation]').count(),0);
 assert.equal(await page.locator('[data-hero-slide]:visible').evaluate(el=>getComputedStyle(el).animationName),'none');
 await page.getByRole('button',{name:'Next campaign',exact:true}).click();
 assert.match(await selected(), /campaign 2/);
 // Real touch input through Chromium, including horizontal swipe and vertical scroll.
 const mobile = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 const touch = await mobile.newPage();
 await touch.clock.install();
 await touch.goto('http://127.0.0.1:8017/');
 await touch.locator('[data-hero-next]').waitFor({state:'visible'});
 const cdp = await mobile.newCDPSession(touch);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:310,y:350}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:110,y:355}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 assert.match(await touch.locator('[data-hero-dot][aria-current="true"]').getAttribute('aria-label'),/campaign 2/);
 await touch.clock.fastForward(7000);
 assert.match(await touch.locator('[data-hero-dot][aria-current="true"]').getAttribute('aria-label'),/campaign 2/);
 await page.getByRole('button',{name:'Show campaign 1',exact:true}).click();
 assert.match(await selected(), /campaign 1/);
 const nojs = await browser.newContext({javaScriptEnabled:false});
 const fallback = await nojs.newPage();
 await fallback.goto('http://127.0.0.1:8017/');
 assert.equal(await fallback.locator('[data-hero-slide]:visible').count(),1);
 assert.equal(await fallback.locator('[data-hero-controls]').isVisible(),false);
 // Banner navigation and delayed clicks after short drags.
 await page.goto('http://127.0.0.1:8017/');
 await page.locator('[data-hero-next]').waitFor({state:'visible'});
 const banner = page.locator('[data-hero-slide]:visible .campaign-hero-link');
 assert.equal(await banner.getAttribute('href'), '/catalogue/?hero=1');
 await banner.evaluate(el => {
   el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,isPrimary:true,pointerId:1,clientX:100,clientY:100}));
   window.dispatchEvent(new PointerEvent('pointermove', {pointerId:1,clientX:125,clientY:100}));
   window.dispatchEvent(new PointerEvent('pointerup', {pointerId:1,clientX:125,clientY:100}));
 });
 await page.clock.fastForward(100);
 assert.equal(await banner.evaluate(el => el.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,detail:1}))), false);
 assert.equal(page.url(), 'http://127.0.0.1:8017/');
 await banner.focus();
 await page.keyboard.press('Enter');
 await page.waitForURL('**/catalogue/?hero=1');
 assert.equal(touch.url(), 'http://127.0.0.1:8017/');
 // Every control is above the banner and must keep the current document open.
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.goto('http://127.0.0.1:8017/');
 await page.locator('[data-hero-next]').waitFor({state:'visible'});
 await page.getByRole('button', {name:'Next campaign',exact:true}).click();
 await page.getByRole('button', {name:'Previous campaign',exact:true}).click();
 await page.getByRole('button', {name:'Show campaign 1',exact:true}).click();
 assert.equal(page.url(), 'http://127.0.0.1:8017/');
 // A fresh mouse gesture after a drag still follows the banner normally.
 await banner.click({position:{x:80,y:80}});
 await page.waitForURL('**/catalogue/?hero=1');
 // A vertical touch scroll must not navigate; a deliberate tap must.
 await touch.goto('http://127.0.0.1:8017/');
 await touch.locator('[data-hero-next]').waitFor({state:'visible'});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:200,y:450}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:200,y:200}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 assert.equal(touch.url(), 'http://127.0.0.1:8017/');
 await touch.evaluate(() => window.scrollTo(0, 0));
 await touch.locator('[data-hero-slide]:visible .campaign-hero-link').tap({position:{x:80,y:80}});
 await touch.waitForURL('**/catalogue/?hero=1');
 // End of storefront-only verification.
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({results,errors,status:'PASS'},null,2));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
