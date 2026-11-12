// Two simultaneous POSTs against the same basket, using the isolated preview.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:8023';
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
 try {
  const context=await browser.newContext();
  const page=await context.newPage();
  const fixture=await(await context.request.get(base+'/__cod_fixture__/')).json();
  await page.goto(base+fixture.product);
  await page.locator('form[data-cart-add] button[type="submit"]').click();
  await page.locator('[data-cart-close]').click();
  await page.goto(base+'/checkout/');
  const data=await page.locator('#cod-checkout').evaluate(form=>Object.fromEntries(new FormData(form)));
  Object.assign(data,{action:'place_order',email:'concurrent@example.test',phone_number:'0791234567',first_name:'Concurrent',last_name:'Customer',line1:'12 Example Street',line4:'Amman'});
  const responses=await Promise.all([1,2].map(()=>context.request.post(base+'/checkout/',{form:data,maxRedirects:0})));
  const statuses=responses.map(r=>r.status());
  assert.deepEqual(statuses,[302,302]);
  await page.goto(base+'/checkout/thank-you/');
  await page.getByRole('heading',{name:'Thank you for your order',exact:true}).waitFor();
  const response=await context.request.get(base+'/__cod_result__/');
  assert.equal(response.status(),200);
  const order=await response.json();
  assert.equal(order.basket_orders,1);
  assert.equal(order.transactions,0);
  assert.equal(Number(order.debited),0);
  assert.equal(Number(order.shipping),2);
  assert.equal(Number(order.total),191);
  assert.equal(Number(order.balance),191);
  assert.deepEqual(order.notifications,[{kind:'customer',status:'sent'},{kind:'merchant',status:'sent'}]);
  console.log(JSON.stringify({statuses,order:order.number,basketOrders:order.basket_orders,status:'PASS'}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
