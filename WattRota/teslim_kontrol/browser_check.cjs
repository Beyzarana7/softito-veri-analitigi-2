const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),browser=await chromium.launch({channel:'chrome',headless:true});
 const checks=[];
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1050},locale:'tr-TR',timezoneId:'Europe/Istanbul'});
 await page.goto(process.env.WATTROTA_TEST_URL||'http://127.0.0.1:8518');
 for(const name of ['Üretim Çizelgesi','Analiz ve Bulgular','Üretim Planlama']){
  const option=page.getByTestId('stSidebar').getByText(name,{exact:true});await option.waitFor();await option.click();
  await page.getByRole('heading',{name,exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.stApp')?.getAttribute('data-teststate')!=='running');
  await page.waitForTimeout(1000);assert.equal(await page.getByTestId('stException').count(),0);
  checks.push({page:name,passed:true});
 }
 assert.equal(await page.getByTestId('stSidebar').getByRole('radio').count(),3);
 const record={passed:true,pages:checks,database_required_for_saved_demo:false,optimization_started:false};
 fs.writeFileSync(path.join(root,'teslim_kontrol','tarayici.json'),JSON.stringify(record,null,2));console.log(JSON.stringify(record));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
