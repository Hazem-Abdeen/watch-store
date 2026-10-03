// Run against tests/browser/messages_preview.py. No production fixture URL is added.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-message-screenshots';
fs.mkdirSync(screenshots, {recursive:true});
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome',headless:true});
 try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error=>errors.push(error.message));
  const results = [];
  for(const width of [1440,768,390,320]) {
   await page.setViewportSize({width,height:1000});
   await page.goto('http://127.0.0.1:8020/__messages__/');
   await page.waitForFunction(()=>document.querySelector('#legacy-alert').dataset.abdeenMessage);
   const root = page.locator('#main-content');
   for(const state of ['success','danger','warning','info']) {
    const alert = root.locator(`#messages .alert-${state}`);
    assert.equal(await alert.count(),1);
    assert.equal(await alert.getAttribute('role'),state==='danger'?'alert':'status');
    assert.equal(await alert.evaluate(el=>getComputedStyle(el,'::before').maskImage.includes('svg')),true);
    assert.ok(await alert.evaluate(el=>el.scrollWidth<=el.clientWidth));
   }
   const described = await root.locator('input[aria-invalid="true"]').evaluateAll(inputs=>inputs.map(input=>({id:input.id,ids:(input.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean).map(id=>({id,exists:!!document.getElementById(id)}))})));
   assert.ok(described.length>=3);
   described.forEach(field=>{assert.ok(field.ids.length>0);field.ids.forEach(id=>assert.equal(id.exists,true));});
   const dimensions = await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth}));
   assert.equal(dimensions.document,width);
   assert.equal(dimensions.body,width);
   await root.locator('#messages').scrollIntoViewIfNeeded();
   await page.screenshot({path:`${screenshots}/messages-${width}.png`,fullPage:true});
   const first = root.locator('#messages .alert').first();
   await first.locator('button').focus();
   await page.keyboard.press('Tab');
   await page.keyboard.press('Shift+Tab');
   assert.notEqual(await first.locator('button').evaluate(el=>getComputedStyle(el).outlineStyle),'none');
   await page.keyboard.press('Enter');
   await page.waitForFunction(()=>document.querySelectorAll('#messages .alert').length===3);
   assert.equal(await root.locator('#messages .alert').first().locator('button').evaluate(el=>el===document.activeElement),true);
   // Use Oscar's unmodified AJAX API, including its trusted HTML and clear behavior.
   await page.evaluate(()=>{oscar.messages.clear();oscar.messages.success('<p>AJAX basket update. <a href="/basket/">View basket</a></p>');});
   await root.locator('#messages .alert button[data-dismiss="alert"]').waitFor();
   assert.equal(await root.locator('#messages .alert').getAttribute('role'),'status');
   assert.equal(await root.getByRole('link',{name:'View basket',exact:true}).getAttribute('href'),'/basket/');
   await root.locator('#messages .alert button').focus();
   await page.keyboard.press('Space');
   await page.waitForFunction(()=>!document.querySelector('#messages .alert'));
   assert.equal(await root.evaluate(el=>el===document.activeElement),true);
   await page.evaluate(()=>{oscar.messages.error('AJAX error.');oscar.messages.warning('AJAX warning.');oscar.messages.info('AJAX info.');});
   await page.waitForFunction(()=>document.querySelectorAll('#messages .abdeen-message').length===3);
   assert.equal(await root.locator('#messages .alert-danger').getAttribute('role'),'alert');
   await page.goto('http://127.0.0.1:8020/__messages__/?checkout=1');
   assert.equal(await page.locator('.abdeen-checkout').count(),1);
   assert.equal(await page.locator('#messages .alert-danger').getAttribute('role'),'alert');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
   if(width===320) await page.screenshot({path:`${screenshots}/checkout-320.png`,fullPage:true});
   results.push(dimensions);
  }
  // Real invalid login uses the same inline errors without authenticating anyone.
  await page.goto('http://127.0.0.1:8020/accounts/login/');
  await page.locator('#login_form').evaluate(form=>form.noValidate=true);
  await page.locator('[name="login-username"]').fill('invalid');
  await page.locator('[name="login-password"]').fill('incorrect');
  await page.locator('[name="login_submit"]').click();
  await page.locator('#login_form .abdeen-field-errors').waitFor();
  assert.equal(await page.locator('#login_form .alert-danger').getAttribute('role'),'alert');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),320);
  await page.screenshot({path:`${screenshots}/login-320.png`,fullPage:true});
  // Preserve the existing authentication gate on the real checkout route.
  await page.goto('http://127.0.0.1:8020/checkout/');
  assert.equal(new URL(page.url()).pathname,'/accounts/login/');
  assert.equal(new URL(page.url()).searchParams.get('next'),'/checkout/');
  assert.equal(await page.locator('#login_form').count(),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),320);
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('http://127.0.0.1:8020/__messages__/');
  assert.equal(await page.locator('#messages .alert').first().evaluate(el=>getComputedStyle(el).transitionDuration),'0s');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({results,errors,status:'PASS'},null,2));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
