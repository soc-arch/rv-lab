/* Check a real registered application over HTTP or an extracted offline ZIP.
 * NODE_PATH=/path/to/node_modules node viewer/check_registration.cjs BASE_URL OUTPUT
 */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const base = process.argv[2], output = path.resolve(process.argv[3]);
  fs.mkdirSync(output, {recursive:true});
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:1440, height:1050}});
    const errors = [], external = [], reports = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('request', r => {if (/^https?:/.test(r.url()) && new URL(r.url()).origin !== new URL(base).origin) external.push(r.url());});
    await page.goto(new URL('index.html', base).href);
    const catalog = await page.evaluate(() => JSON.parse(document.getElementById('navigation-data').textContent));
    const custom = catalog.groups.find(g => g.id === 'custom');
    assert.equal(custom.title, 'My applications');
    assert.ok(custom.examples.length > 0);
    await page.locator('#navigation-group').selectOption('custom');
    await page.screenshot({path:path.join(output, 'my-applications.png'), fullPage:true});
    for (const example of custom.examples) {
      await page.goto(new URL('index.html', base).href);
      await page.locator('#navigation-group').selectOption('custom');
      await page.locator('#navigation-example').selectOption(example.id);
      await page.locator('#navigation-open').click();
      await page.waitForFunction(() => window.cpuLabViewer);
      const data = await page.evaluate(() => JSON.parse(document.getElementById('trace-data').textContent));
      assert.ok(data.trace.length > 1);
      assert.equal(data.metadata.navigation.current_id, example.id);
      assert.equal(await page.locator('#navigation-group').inputValue(), 'custom');
      await page.evaluate(() => window.cpuLabViewer.seek(0));
      await page.locator('#next').click();
      assert.equal(await page.evaluate(() => window.cpuLabViewer.getState().index), 1);
      const samples = new Map();
      data.trace.forEach((s,i) => {if (!samples.has(s.execute.state)) samples.set(s.execute.state,i);});
      for (const index of samples.values()) {
        await page.evaluate(i => window.cpuLabViewer.seek(i), index);
        const s = data.trace[index];
        assert.equal(await page.locator('#cycle-number').textContent(), s.cycle.toLocaleString('en-US'));
        assert.equal(await page.locator('#node-rf-write').getAttribute('class'), 'node' + (s.regs.wb_enable ? ' retire-active' : ''));
      }
      await page.screenshot({path:path.join(output, example.id + '.png'), fullPage:true});
      await page.setViewportSize({width:390, height:844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.setViewportSize({width:1440, height:1050});
      await page.locator('#navigation-home').click();
      assert.match(page.url(), /index.html$/);
      const reportUrl = new URL(example.href.replace(/trace.html$/, 'report.html'), base).href;
      await page.goto(reportUrl);
      assert.match(await page.locator('main').textContent(), /PASS/);
      assert.match(await page.locator('main').textContent(), /Retired instructions/);
      reports.push({id:example.id, samples:data.trace.length, states:[...samples.keys()], elf_sha256:data.metadata.elf_sha256});
    }
    await page.goto(new URL('course/index.html', base).href);
    const lessons = await page.locator('main a[href]').evaluateAll(links => [...new Set(links.map(a=>a.href))].filter(href => /\/0[1-8][^/]*\.html$/.test(href)));
    assert.equal(lessons.length, 8);
    for (const url of lessons) {
      await page.goto(url);
      assert.ok((await page.locator('main').textContent()).length > 1000);
      await page.setViewportSize({width:390, height:844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, url);
      await page.setViewportSize({width:1440, height:1050});
    }
    await page.goto(new URL('course/index.html', base).href);
    await page.screenshot({path:path.join(output, 'course.png'), fullPage:true});
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    const receipt = {status:'pass', base, reports, lessons:lessons.length, errors, externalRequests:external.length, browser:browser.version()};
    fs.writeFileSync(path.join(output, 'registration-check.json'), JSON.stringify(receipt,null,2) + '\n');
    console.log(JSON.stringify(receipt,null,2));
  } finally {await browser.close();}
})().catch(e => {console.error(e); process.exitCode=1;});
