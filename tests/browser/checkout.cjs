// Run against checkout_preview.py; all orders use a disposable database.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = 'http://127.0.0.1:8023';
const screenshots = process.env.SCREENSHOT_DIR || '/tmp/abdeen-cod-screenshots';
fs.mkdirSync(screenshots,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome',headless:true});
 const results=[], errors=[];
 try {
  for(const width of [1440,1024,768,390,320]) {
   for(const mode of ['guest','account']) {
    const context=await browser.newContext({viewport:{width,height:1000}});
    await context.route('https://ajax.googleapis.com/**',r=>r.abort());
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console', message => { if(message.type()==='error' && !message.text().includes('net::ERR_')) errors.push(message.text()); });
    const fixture=await(await context.request.get(base+`/__cod_fixture__/?width=${width}`)).json();
    async function check(name) {
     await page.waitForLoadState('load');
     await page.evaluate(()=>document.fonts.ready);
     await page.evaluate(()=>window.scrollTo(0,0));
     assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width,`${name} overflow`);
     const duplicates=await page.locator('[id]').evaluateAll(ns=>ns.map(n=>n.id).filter((id,i,a)=>a.indexOf(id)!==i));
     assert.deepEqual(duplicates,[]);
     await page.screenshot({path:`${screenshots}/${mode}-${name}-${width}.png`,fullPage:true});
    }
    if(mode==='account') {
     await page.goto(base+'/accounts/login/');
     await page.locator('[name="login-username"]').fill(fixture.email);
     await page.locator('[name="login-password"]').fill('Browser-example-493!');
     await page.locator('[name="login_submit"]').click();
     await page.waitForURL(url=>!url.pathname.includes('/login'));
    }
    await page.goto(base+fixture.product);
    await page.locator('form[data-cart-add] button[type="submit"]').click();
    const checkoutButton=page.locator('.abdeen-cart-checkout');
    const viewBag=page.locator('.abdeen-cart-view');
    await checkoutButton.waitFor();
    await page.locator('[data-cart-drawer]').evaluate(async drawer => {
     await Promise.all(drawer.getAnimations().map(animation=>animation.finished));
    });
    assert.equal(await checkoutButton.locator('svg').count(),0);
    assert.match(await checkoutButton.innerText(),/CHECKOUT\s*·\s*189(?:\.00)? JOD/i);
    const buttonBox=await checkoutButton.boundingBox(), linkBox=await viewBag.boundingBox();
    assert.ok(linkBox.y>=buttonBox.y+buttonBox.height,'View bag is below checkout');
    assert.ok(Math.abs(linkBox.x-buttonBox.x)<1,'View bag is left aligned');
    await page.getByRole('link',{name:'View cart',exact:true}).click();
    await page.waitForURL('**/basket/');
    await page.locator('.abdeen-basket-checkout').click();
    await page.locator('#cod-checkout').waitFor();
    await check('checkout');
    assert.equal(await page.locator('#id_country').inputValue(),'JO');
    assert.equal(await page.locator('[name="method_code"][type="hidden"]').inputValue(),'jordan-delivery');
    assert.match(await page.locator('.cod-selected').first().innerText(),/Delivery\s+1–2 business days\s+2\.00 JOD/);
    const summary=page.locator('.abdeen-checkout-summary');
    assert.match(await summary.locator('tr').filter({hasText:'Subtotal'}).innerText(),/189 JOD/);
    assert.match(await summary.locator('tr').filter({hasText:'Shipping'}).innerText(),/2\.00 JOD/);
    assert.match(await summary.locator('.cod-total').innerText(),/191 JOD/);
    assert.equal(await page.locator('#id_country option').count(),1);
    assert.equal(await page.locator('#cod-checkout input[type="radio"]').count(),0);
    assert.equal(await page.getByRole('button',{name:'Update delivery & total'}).count(),0);
    assert.equal(await page.locator('.cod-selected').count(),2);
    assert.equal(await page.getByText('Billing address',{exact:true}).count(),0);
    if(mode==='guest') {
     assert.equal(await page.locator('#id_email').isEditable(),true);
     await page.getByRole('button',{name:'PLACE ORDER',exact:true}).click();
     await page.locator('#id_email_error').waitFor();
     assert.equal(await page.locator('#id_phone_number_error').count(),1);
     assert.equal(await page.locator('#id_line1_error').count(),1);
     await check('validation');
     await page.locator('#id_email').fill('replace-me@example.test');
     await page.locator('#id_email').fill(`guest-${width}@example.test`);
     await page.locator('#id_phone_number').fill('0791234567');
     await page.locator('#id_first_name').fill('Guest');
     await page.locator('#id_last_name').fill('Customer');
     await page.locator('#id_line1').fill('12 Example Street');
     await page.locator('#id_line4').fill('Amman');
    } else {
     assert.equal(await page.locator('#id_email').isEditable(),true);
     assert.equal(await page.locator('#id_email').inputValue(),fixture.email);
     await page.getByText('Order updates will be sent here. Your account email will not change.').waitFor();
     assert.equal(await page.locator('#id_line1').inputValue(),'24 Saved Street');
     assert.ok((await page.locator('#id_phone_number').inputValue()).includes('791234567'));
     await page.locator('.cod-addresses summary').click();
     await page.locator('.cod-addresses li a').first().click();
     assert.equal(await page.locator('#id_line1').inputValue(),'24 Saved Street');
     await page.locator('#id_email').click();
     await page.locator('#id_email').fill(`account-order-${width}@example.test`);
    }
    await page.locator('#id_notes').fill('Call on arrival');
    await check('ready');
    const submitted=await page.locator('#cod-checkout').evaluate(form=>Object.fromEntries(new FormData(form)));
    submitted.action='place_order';
    await page.getByRole('button',{name:'PLACE ORDER',exact:true}).click();
    await page.waitForURL('**/checkout/thank-you/');
    await check('confirmation');
    const order=await(await context.request.get(base+'/__cod_result__/')).json();
    assert.equal(order.source,'Cash on Delivery (COD)');
    assert.equal(order.phone,'+962791234567');
    assert.equal(Number(order.total),191);
    assert.equal(Number(order.shipping),2);
    assert.equal(Number(order.allocated),191);
    assert.equal(Number(order.balance),191);
    await page.getByText('Delivery · 2.00 JOD',{exact:true}).waitFor();
    await page.getByText('Payment due on delivery: 191 JOD',{exact:true}).waitFor();
    assert.match(await summary.locator('tr').filter({hasText:'Shipping charge'}).innerText(),/2 JOD/);
    assert.equal(Number(order.debited),0);
    assert.equal(order.transactions,0);
    assert.equal(order.payment_events,0);
    assert.equal(order.basket_orders,1);
    assert.equal(mode==='guest',order.user===null);
    assert.equal(order.email,mode==='guest'?`guest-${width}@example.test`:`account-order-${width}@example.test`);
    if(mode==='account') assert.equal(order.account_email,fixture.email);
    assert.equal(order.address,mode==='guest'?'12 Example Street':'24 Saved Street');
    assert.deepEqual(order.notifications,[{kind:'customer',status:'sent'},{kind:'merchant',status:'sent'}]);
    await page.reload();
    await page.reload();
    const refreshed=await(await context.request.get(base+'/__cod_result__/')).json();
    assert.deepEqual(refreshed,order);
    // Replay the exact original form after successful placement.
    await context.request.post(base+'/checkout/',{form:submitted});
    assert.equal((await(await context.request.get(base+'/__cod_result__/')).json()).basket_orders,1);
    if(mode==='account') {
     await page.goto(base+'/accounts/orders/');
     await page.getByText(order.number,{exact:true}).first().waitFor();
     await check('history');
     assert.match(await page.locator('tr').filter({hasText:order.number}).innerText(),/191 JOD/);
     await page.getByRole('link',{name:order.number,exact:true}).click();
     await check('order-detail');
     assert.match(await page.locator('tr').filter({hasText:'Shipping total'}).innerText(),/2 JOD/);
     assert.match(await page.locator('tr').filter({hasText:'Order total'}).innerText(),/191 JOD/);
    }
    results.push({width,mode,order:order.number,status:'PASS'});
    await context.close();
   }
  }
  // Entire checkout works with JavaScript disabled.
  const context=await browser.newContext({javaScriptEnabled:false,viewport:{width:320,height:900}});
  const page=await context.newPage();
  const fixture=await(await context.request.get(base+'/__cod_fixture__/')).json();
  await page.goto(base+fixture.product);
  await page.locator('form[data-cart-add] button[type="submit"]').click();
  await page.goto(base+'/checkout/');
  for(const [name,value] of Object.entries({email:'no-js@example.test',phone_number:'0791234567',first_name:'Guest',last_name:'Customer',line1:'12 Example Street',line4:'Amman'})) await page.locator(`[name="${name}"]`).fill(value);
  await page.getByRole('button',{name:'PLACE ORDER',exact:true}).click();
  await page.waitForURL('**/checkout/thank-you/');
  await page.getByText('Payment due on delivery: 191 JOD',{exact:true}).waitFor();
  await context.close();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({results,noJavaScript:true,errors,status:'PASS'},null,2));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
