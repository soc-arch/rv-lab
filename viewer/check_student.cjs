/* Verify actual student output/performance reports over HTTP or extracted files.
 * NODE_PATH=/path/to/node_modules node viewer/check_student.cjs BASE_URL OUTPUT_DIR
 * BASE_URL ends in /; it may be http://127.0.0.1:8770/ or file:///.../build/.
 */
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const { chromium }=require('playwright');
(async()=>{
 const base=process.argv[2], output=path.resolve(process.argv[3]);
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}), errors=[], external=[], checked=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(/^https?:/.test(r.url())&&new URL(r.url()).origin!==new URL(base).origin)external.push(r.url());});
  for(const opt of ['O0','O2']){
   await page.goto(new URL(`10_performance-${opt}/report.html`,base).href);
   assert.equal(await page.locator('h1').textContent(),`10_performance · ${opt}`);
   const content=await page.locator('main').textContent();
   assert.match(content,/sum\(1\.\.32\)=528/);assert.match(content,/RTL marker ROI/);
   assert.match(content,/Software CSR interval/);assert.match(content,/actual retirements recorded/);
   assert.match(content,/100 MHz/);assert.match(content,/PASS/);
   for(const label of ['Source & disassembly','Cycle viewer','Retired instructions (CSV)','Retired instructions (JSONL)','Measurement JSON']){
    assert.equal(await page.getByRole('link',{name:label,exact:true}).count(),1);
   }
   await page.screenshot({path:path.join(output,`${opt}.png`),fullPage:true});
   await page.setViewportSize({width:390,height:844});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Mobile page overflow');
   await page.screenshot({path:path.join(output,`${opt}-mobile.png`),fullPage:true});
   await page.setViewportSize({width:1440,height:1000});
   checked.push(opt);
  }
  await page.goto(new URL('check_failure-O2/report.html',base).href);
  assert.match(await page.locator('main').textContent(),/FAIL/);
  await page.goto(new URL('hang-O2/report.html',base).href);
  assert.match(await page.locator('main').textContent(),/cycle_budget/);
  assert.match(await page.locator('main').textContent(),/incomplete/);
  await page.goto(new URL('results.html',base).href);
  assert.ok(await page.locator('a[href="10_performance-O2/report.html"]').count());
  assert.ok(await page.locator('a[href="10_performance-O0/report.html"]').count());
  await page.locator('a[href="10_performance-O2/report.html"]').click();
  assert.match(page.url(),/10_performance-O2\/report.html$/);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const receipt={status:'pass',base,optimizations:checked,failedRun:true,timeout:true,errors,externalRequests:external.length,browser:browser.version()};
  fs.writeFileSync(path.join(output,'student-check.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log(JSON.stringify(receipt,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
