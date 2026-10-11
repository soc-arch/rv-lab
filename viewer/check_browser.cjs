/* Optional maintainer smoke check. Requires Playwright and its Chromium binary.
 * NODE_PATH=/path/to/node_modules node viewer/check_browser.cjs report.html /tmp/viewer-check
 * Consumes an actual generated report; never generates a synthetic CPU trace.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const report = /^https?:\/\//.test(process.argv[2]) ? process.argv[2] : path.resolve(process.argv[2]);
  const reportUrl = /^https?:\/\//.test(report) ? report : pathToFileURL(report).href;
  const reportOrigin = new URL(reportUrl).origin;
  const output = path.resolve(process.argv[3] || '/tmp/cpu-lab-viewer-check');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== reportOrigin) requests.push(request.url());
  });
  await page.goto(reportUrl);
  await page.waitForFunction(() => window.cpuLabViewer);
  assert.equal(await page.locator('#error').isVisible(), false);
  const source = await page.evaluate(() => JSON.parse(document.getElementById('trace-data').textContent));
  const state = () => page.evaluate(() => window.cpuLabViewer.getState());
  const initial = await state();
  assert.equal(initial.cycles, source.trace.length);
  if (initial.mainIndex >= 0) assert.equal(initial.index, initial.mainIndex);

  if(initial.index < initial.cycles-1){
    await page.locator('#next').click();
    assert.equal((await state()).index,initial.index+1);
    await page.locator('#previous').click();
    assert.equal((await state()).index,initial.index);
  }else if(initial.index>0){
    assert.equal(await page.locator('#next').isDisabled(),true);
    await page.locator('#previous').click();
    assert.equal((await state()).index,initial.index-1);
    await page.locator('#next').click();
    assert.equal((await state()).index,initial.index);
  }
  await page.evaluate(() => window.cpuLabViewer.seek(0));
  const firstRetirement = source.trace.findIndex((s, i) => i > 0 && s.commit.valid);
  if (firstRetirement >= 0) {
    await page.locator('#retire').click();
    assert.equal((await state()).index, firstRetirement);
  }
  const geometry = await page.evaluate(() => {
    const box = id => document.querySelector('#node-' + id + ' rect').getBBox();
    const read = box('rf-read'), write = box('rf-write'), decode = box('decoder'), alu = box('alu'), lsu = box('lsu'), ram = box('dmem');
    return { readNearDecode: read.x > decode.x && read.x < alu.x, writeAfterExecution: write.x > alu.x,
      ramBelowLsu: ram.y > lsu.y + lsu.height, memoryArrowsVertical: ['request','response'].every(kind => {
        const wire = document.getElementById('wire-memory-' + kind), a = wire.getPointAtLength(0), b = wire.getPointAtLength(wire.getTotalLength());
        return wire.dataset.direction === 'vertical' && Math.abs(a.x-b.x) < 0.1 && Math.abs(a.y-b.y) > 20;
      }), identityRF: document.getElementById('identity-rf') !== null, identityRAM: document.getElementById('identity-ram') !== null };
  });
  assert.ok(Object.values(geometry).every(Boolean), 'RF views and vertical memory geometry');
  const store = source.trace.findIndex(s => s.execute.valid && (s.execute.insn & 127) === 0x23 && s.commit.valid);
  if (store >= 0) {
    await page.evaluate(i => window.cpuLabViewer.seek(i), store);
    assert.equal(await page.locator('#node-rf-write').getAttribute('class'), 'node', 'Store retirement must not imply RF write');
    assert.equal(await page.locator('#wire-wb').getAttribute('class'), 'wire');
    assert.match(await page.locator('#writeback-value').textContent(), /disabled/);
  }
  const busCases = new Map();
  source.trace.forEach((s, i) => { for (const name of ['instruction','data']) {
    const p = s.ports?.[name]; if (!p) return;
    for (const kind of ['req','resp']) {
      assert.equal(!!p[kind+'_accepted'], !!p[kind+'_valid'] && !!p[kind+'_ready'], 'Actual trace handshake invariant');
      const key = [name,kind,p[kind+'_valid'],p[kind+'_ready'],kind==='resp'?p.resp_error:0].join(':');
      if (!busCases.has(key)) busCases.set(key,{ index:i,name,kind });
    }
  }});
  for (const {index,name,kind} of busCases.values()) {
    await page.evaluate(i => window.cpuLabViewer.seek(i), index);
    const s=source.trace[index], p=s.ports[name], id=(name==='instruction'?'i':'d')+'-'+(kind==='req'?'request':'response');
    const title=await page.locator('#'+id+' strong').textContent();
    if(p[kind+'_accepted'])assert.match(title,/ACCEPTED/);
    else if(p[kind+'_valid'])assert.match(title,/OFFERED — WAITING/);
    else assert.match(title,/not valid/);
    const wireId=name==='data'?'memory-'+(kind==='req'?'request':'response'):kind==='req'?'pc':'fetch-response';
    const classes=await page.locator('#wire-'+wireId).getAttribute('class');
    assert.equal(classes.split(' ').includes('strong'),!!p[kind+'_accepted']);
    assert.equal(classes.split(' ').includes('offered'),!!p[kind+'_valid']&&!p[kind+'_ready']);
    if(kind==='resp'&&p.resp_valid&&p.resp_error){
      assert.match(await page.locator('#'+id).textContent(),/ERROR \(data not usable\)/);
      assert.match(classes,/error/);
      if(name==='data')assert.equal(await page.locator('#node-rf-write').getAttribute('class'),'node','Faulting data response must not write RF');
      await page.screenshot({path:path.join(output,name+'-error.png'),fullPage:true});
    }
    assert.equal((await page.locator('#wire-fetch').getAttribute('class')).split(' ').includes('strong'),!!s.fetch.accepted,'Memory response and slot admission are distinct');
  }
  assert.equal(await page.locator('#legacy-trace').isVisible(),busCases.size===0);
  const samples = new Map();
  source.trace.forEach((s, i) => { if (!samples.has(s.execute.state)) samples.set(s.execute.state, i); });
  for (const [name, index] of samples) {
    await page.evaluate(index => window.cpuLabViewer.seek(index), index);
    const s = source.trace[index];
    assert.equal(await page.locator('#cycle-number').textContent(), s.cycle.toLocaleString('en-US'));
    if (s.execute.valid) assert.equal(await page.locator('#state-name').textContent(), name.replaceAll('_', ' '));
    assert.equal(await page.locator('#node-rf-write').getAttribute('class'), 'node' + (s.regs.wb_enable ? ' retire-active' : ''));
    assert.equal(await page.locator('#node-wb').getAttribute('class'), 'node' + (s.regs.wb_enable ? ' retire-active' : ''));
    if (s.units.div) assert.match(await page.locator('#node-div').getAttribute('class'), /active/);
  }
  // Literal sources are text, not interpreted HTML. Numeric bits match the trace.
  const divWait = source.trace.findIndex(s => s.execute.state === 'DIV_WAIT' && !s.commit.valid);
  if (divWait >= 0) {
    await page.evaluate(index => window.cpuLabViewer.seek(index), divWait);
    assert.match(await page.locator('#explanation').textContent(), /same instruction remains/);
    assert.equal(await page.locator('#node-slot').getAttribute('class'), 'node wait-active');
    await page.screenshot({ path: path.join(output, 'divide-wait.png'), fullPage: true });
  }
  const last = source.trace.length - 1;
  await page.evaluate(index => window.cpuLabViewer.seek(Math.max(0, index - 1)), last);
  await page.locator('#speed').selectOption('30');
  await page.locator('#play').click();
  await page.waitForFunction(() => !window.cpuLabViewer.getState().playing);
  assert.equal((await state()).index, last);
  assert.equal(await page.locator('#next').isDisabled(), true);
  if (initial.mainIndex >= 0) await page.locator('#main').click();
  const pc = source.trace[(await state()).index].execute.pc;
  await page.locator('#address').fill('0x' + pc.toString(16));
  await page.locator('#find').click();
  assert.equal(source.trace[(await state()).index].execute.pc, pc);
  if (initial.mainIndex >= 0) await page.locator('#main').click();

  const overflow = await page.evaluate(() => {
    const failures = [];
    for (const node of document.querySelectorAll('svg .node')) {
      const box = node.querySelector('rect').getBBox();
      for (const label of node.querySelectorAll('text')) {
        const text = label.getBBox();
        if (text.x < box.x || text.x + text.width > box.x + box.width - 4) failures.push(node.id + ': ' + label.textContent);
      }
    }
    return failures;
  });
  assert.deepEqual(overflow, [], 'SVG node text overflow');
  await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'mobile page overflow');
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, [], 'report must make no network requests');
  const summary = { report, checkedCycles: source.trace.length, executionStates: [...samples.keys()], handshakeCases: busCases.size, geometry,
                    browser: browser.version(), externalRequests: requests.length, errors, screenshots: output };
  fs.writeFileSync(path.join(output, 'browser-check.json'), JSON.stringify(summary, null, 2) + '\n');
  console.log(JSON.stringify(summary, null, 2));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
