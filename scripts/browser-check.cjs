const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium'});
const context=await browser.newContext({viewport:{width:390,height:844}});
const page=await context.newPage();
const password=fs.readFileSync('data/demo-accounts.txt','utf8').split('\n').find(l=>l.startsWith('admin: ')).slice(7);
let errors=[];page.on('pageerror',e=>errors.push(String(e)));
await page.goto('http://127.0.0.1:8000/login/');
await page.locator('[name=username]').fill('admin');await page.locator('[name=password]').fill(password);
await Promise.all([page.waitForURL('http://127.0.0.1:8000/'),page.locator('button').filter({hasText:'লগইন'}).click()]);
for(const path of ['/','/customers/','/new/sale/','/new/collection/','/documents/1/','/customers/1/ledger/?month=2026-10']){
 const response=await page.goto('http://127.0.0.1:8000'+path);
 if(response.status()!==200)throw Error('Page failed '+path);
 await page.evaluate(()=>document.fonts.ready);
 const fit=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
 if(!fit)throw Error('Mobile overflow '+path);
 const fields=await page.locator('input:not([type=hidden]),select,textarea').all();
 for(const field of fields){const box=await field.boundingBox();if(box&&box.width>390)throw Error('Form overflow '+path);}
}
await page.goto('http://127.0.0.1:8000/new/sale/');await page.locator('#add-line').click();
if(await page.locator('.extra-line').count()!==1)throw Error('Add line failed');
await page.goto('http://127.0.0.1:8000/documents/1/');
await page.evaluate(()=>document.fonts.ready);
if(!await page.evaluate(()=>document.fonts.check('16px "Noto Sans Bengali"')))throw Error('Bengali font unavailable');
await page.emulateMedia({media:'print'});
await page.pdf({path:'data/sample-invoice.pdf',format:'A4',printBackground:true});
await page.screenshot({path:'data/mobile-invoice.png',fullPage:true});
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: six mobile pages fit 390px; form controls fit; add-product works; bundled Bengali font loaded; invoice PDF generated; no browser JS errors. No WhatsApp links opened.');
await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
