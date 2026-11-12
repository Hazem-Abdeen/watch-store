// Run against accounts_preview.py; all writes go to its disposable database.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = 'http://127.0.0.1:8022';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-account-screenshots';
fs.mkdirSync(screenshots, {recursive:true});
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome', headless:true});
 const results = [], errors = [];
 try {
  for (const width of [1440,768,390,320]) {
   const context = await browser.newContext({viewport:{width,height:1000}});
   // Exercise the bundled jQuery fallback without depending on an external CDN.
   await context.route('https://ajax.googleapis.com/**', route=>route.abort());
   const page = await context.newPage();
   page.on('pageerror', error=>errors.push(error.message));
   const fixture = await (await context.request.get(`${base}/__account_fixture__/?width=${width}`)).json();
   const checked = [];
   async function check(name) {
    await page.waitForLoadState('load');
    await page.evaluate(()=>document.fonts.ready);
    await page.screenshot({path:`${screenshots}/${name}-${width}.png`,fullPage:true});
    const dimensions = await page.evaluate(()=>({viewport:innerWidth, document:document.documentElement.scrollWidth, body:document.body.scrollWidth}));
    assert.equal(dimensions.document,width,`${name}: document overflow`);
    assert.equal(dimensions.body,width,`${name}: body overflow`);
    assert.equal(await page.locator('a[href*="wishlist"]').count(),0,`${name}: wishlist visible`);
    assert.equal(await page.locator('[data-home-header]').count(),1);
    assert.equal(await page.locator('.abdeen-footer').count(),1);
    const duplicateIds = await page.locator('[id]').evaluateAll(nodes=>nodes.map(n=>n.id).filter((id,i,all)=>all.indexOf(id)!==i));
    assert.deepEqual(duplicateIds,[],`${name}: duplicate IDs`);
    const missingDescriptions = await page.locator('#main-content [aria-describedby]').evaluateAll(nodes=>
     nodes.flatMap(node=>(node.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&!document.getElementById(id))));
    assert.deepEqual(missingDescriptions,[],`${name}: missing field descriptions`);
    checked.push(name);
   }
   await page.goto(base+'/accounts/login/');
   assert.equal(await page.locator('.abdeen-account-link').getAttribute('href'),'/accounts/login/');
   await check('login');
   await page.locator('[name="login-username"]').fill(fixture.email);
   await page.locator('[name="login-password"]').fill('incorrect');
   await page.locator('[name="login_submit"]').click();
   await page.getByText('The email or password is incorrect.',{exact:true}).waitFor();
   await check('login-error');
   await page.goto(base+'/accounts/register/');
   assert.equal(await page.locator('#register_form input:not([type="hidden"])').count(),3);
   await check('register');
   await page.goto(base+'/password-reset/');
   await check('reset');
   await page.locator('[name="email"]').fill(fixture.email);
   await page.getByRole('button',{name:'Send reset link'}).click();
   await page.waitForURL('**/password-reset/done/');
   await check('reset-done');
   await page.goto(base+fixture.reset);
   await check('reset-confirm');
   await page.locator('[name="new_password1"]').fill('Changed-browser-password-827!');
   await page.locator('[name="new_password2"]').fill('Changed-browser-password-827!');
   await page.getByRole('button',{name:'Save new password'}).click();
   await page.waitForURL('**/password-reset/complete/');
   await check('reset-complete');
   await page.goto(base+fixture.reset);
   await page.getByText('This link is no longer valid',{exact:true}).waitFor();
   await check('reset-expired');
   await page.goto(base+fixture.product);
   await page.locator('form[data-cart-add] button[type="submit"]').click();
   await page.locator('[data-cart-close]').click();
   await page.goto(base+'/basket/');
   await page.locator('.abdeen-basket-checkout').click();
   await page.locator('#cod-checkout').waitFor();
   await check('checkout');
   await page.getByRole('button',{name:'PLACE ORDER',exact:true}).click();
   await page.locator('#id_email_error').waitFor();
   await check('checkout-error');
   // Sign in through Oscar's native customer login and retain the basket.
   await page.getByRole('link',{name:'Sign in',exact:true}).click();
   await page.locator('[name="login-username"]').fill(fixture.email);
   await page.locator('[name="login-password"]').fill('Changed-browser-password-827!');
   await page.locator('[name="login_submit"]').click();
   await page.waitForURL('**/checkout/');
   assert.equal(await page.locator('.abdeen-account-link').getAttribute('href'),'/accounts/');
   await page.locator('.abdeen-account-link').click();
   await page.waitForURL('**/accounts/profile/');
   await check('account');
   for (const [name,url] of [['orders','/accounts/orders/'],['order',fixture.order],['addresses','/accounts/addresses/'],['address-add','/accounts/addresses/add/'],['details','/accounts/profile/edit/'],['change-password','/accounts/change-password/']]) {
    await page.goto(base+url); await check(name);
   }
   await page.getByRole('button',{name:'Sign out',exact:true}).click();
   await page.waitForURL(base+'/');
   await page.goto(base+'/accounts/register/?next=/checkout/shipping-address/');
   await page.locator('[name="email"]').fill(`registered-browser-${width}-${Date.now()}@example.test`);
   await page.locator('[name="password1"]').fill('Registration-browser-358!');
   await page.locator('[name="password2"]').fill('Registration-browser-358!');
   await page.getByRole('button',{name:'Create account',exact:true}).click();
   await page.waitForURL(/\/(checkout\/shipping-address|basket)\//);
   assert.equal(await page.locator('.abdeen-account-link').getAttribute('href'),'/accounts/');
   results.push({width,checked});
   await context.close();
  }
  // Guest entry and sign-in remain usable without JavaScript.
  const context = await browser.newContext({javaScriptEnabled:false,viewport:{width:320,height:900}});
  const page = await context.newPage();
  const fixture = await (await context.request.get(`${base}/__account_fixture__/`)).json();
  await page.goto(base+fixture.product);
  await page.locator('form[data-cart-add] button[type="submit"]').click();
  await page.goto(base+'/checkout/');
  await page.locator('#id_email').fill('no-js@example.test');
  await page.getByRole('button',{name:'PLACE ORDER',exact:true}).click();
  await page.locator('#id_phone_number_error').waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),320);
  await context.close();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({results,noJavaScriptGuest:true,errors,status:'PASS'},null,2));
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
