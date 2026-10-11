/* Optional browser smoke check for the generated gallery and camera report.
 * NODE_PATH=/path/to/node_modules node viewer/check_reports.cjs \
 *   build/index.html build/camera/report.html /tmp/report-check [build]
 * Inputs may also be local HTTP URLs. Optional build path enables byte-for-byte
 * comparison between decoded report PNGs and the real simulator RGB dumps.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const target = value => /^https?:\/\//.test(value) ? value : pathToFileURL(path.resolve(value)).href;
(async () => {
  const gallery = target(process.argv[2]), report = target(process.argv[3]);
  const output = path.resolve(process.argv[4] || '/tmp/cpu-lab-report-check');
  const build = process.argv[5] ? path.resolve(process.argv[5]) : null;
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [], external = [];
  const allowedOrigins = new Set([new URL(gallery).origin, new URL(report).origin]);
  page.on('pageerror', error => errors.push(String(error)));
  page.on('request', request => {
    const url = new URL(request.url());
    if (/^https?:$/.test(url.protocol) && !allowedOrigins.has(url.origin)) external.push(url.href);
  });
  await page.goto(gallery);
  const cards = await page.locator('.card').count();
  if (cards === 0) await page.locator('#empty-title').waitFor();
  await page.screenshot({ path: path.join(output, 'gallery.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Gallery mobile overflow');
  await page.screenshot({ path: path.join(output, 'gallery-mobile.png'), fullPage: true });

  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(report);
  await page.waitForFunction(() => window.cpuCameraReport);
  assert.equal(await page.locator('#error').isVisible(), false);
  const data = await page.evaluate(() => JSON.parse(document.getElementById('camera-data').textContent));
  const rawComparisons = [], cycleReports = [];
  assert.equal(await page.locator('#frame-tabs button').count(), data.frames.length);
  for (const frame of data.frames) {
    await page.locator('#frame-tabs button').filter({ hasText: frame.title }).click();
    assert.equal((await page.evaluate(() => window.cpuCameraReport.getState())).selected, frame.id);
    assert.equal(await page.locator('#output-title').textContent(), frame.title);
    if (frame.roi_cycles !== undefined) {
      const expected = (frame.roi_cycles / (frame.pixels_processed || frame.width * frame.height)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      assert.equal(await page.locator('#selected-cpp').textContent(), expected);
      assert.equal(await page.locator('#roi-cycles').textContent(), frame.roi_cycles.toLocaleString('en-US'));
    } else assert.equal(await page.locator('#selected-cpp').textContent(), 'Not recorded');
    if (frame.full_cycles !== undefined) assert.equal(await page.locator('#run-cycles').textContent(), frame.full_cycles.toLocaleString('en-US'));
    if(frame.trace_href){
      assert.equal(await page.locator('#mode-trace-link').getAttribute('href'),frame.trace_href);
      assert.equal(await page.locator('#trace-link').getAttribute('href'),frame.trace_href);
      assert.match(await page.locator('#cycle-status').textContent(),/actual.*RTL run/);
      if(!(await page.evaluate(()=>window.cpuCameraReport.getState())).cycleExpanded)await page.locator('#toggle-cycle').click();
      assert.equal(await page.locator('#cycle-frame').getAttribute('src'),frame.trace_href);
      const explorer=await (await page.locator('#cycle-frame').elementHandle()).contentFrame();
      await explorer.waitForFunction(()=>window.cpuLabViewer);
      assert.equal(await explorer.locator('#error').isVisible(),false);
      const initial=await explorer.evaluate(()=>window.cpuLabViewer.getState());
      await explorer.locator('#next').click();
      assert.equal((await explorer.evaluate(()=>window.cpuLabViewer.getState())).index,Math.min(initial.index+1,initial.cycles-1));
      cycleReports.push({mode:frame.id,href:frame.trace_href,cycles:initial.cycles});
    }else if(data.frames.some(f=>f.trace_href)){
      assert.equal(await page.locator('#mode-trace-link').isVisible(),false);
      assert.equal(await page.locator('#cycle-frame').isVisible(),false);
    }
    if (build) {
      const rawPath = frame.id === 'input'
        ? path.join(build, '06_camera-copy-O2', 'input.rgb')
        : path.join(build, `06_camera-${frame.id}-O2`, 'hw.output.rgb');
      if (fs.existsSync(rawPath)) {
        const raw = fs.readFileSync(rawPath);
        assert.equal(raw.length, frame.width * frame.height * 3);
        const decoded = await page.evaluate(frame => {
          const values = [];
          for (let y = 0; y < frame.height; y++) for (let x = 0; x < frame.width; x++) {
            const rgba = window.cpuCameraReport.getPixel(frame.id, x, y);
            values.push(...rgba.slice(0, 3));
            if (rgba[3] !== 255) throw Error('Unexpected non-opaque simulator image');
          }
          return values;
        }, frame);
        assert.deepEqual(Buffer.from(decoded), raw, `PNG pixels differ from real RGB dump for ${frame.id}`);
        rawComparisons.push({ frame: frame.id, bytes: raw.length });
      }
    }
  }
  if((await page.evaluate(()=>window.cpuCameraReport.getState())).cycleExpanded){
    await page.locator('#cycle-panel').screenshot({path:path.join(output,'camera-cycle-explorer.png')});
    await page.locator('#toggle-cycle').click();
  }
  await page.evaluate(() => window.cpuCameraReport.setPixel(1, 1));
  await page.locator('#output-wrap').focus();
  await page.keyboard.press('ArrowRight');
  let state = await page.evaluate(() => window.cpuCameraReport.getState());
  assert.equal(state.x, 2); assert.equal(state.y, 1);
  await page.locator('#pixel-x').fill('7');
  await page.locator('#pixel-y').fill('9');
  state = await page.evaluate(() => window.cpuCameraReport.getState());
  assert.equal(state.x, Math.min(7, state.width - 1));
  assert.equal(state.y, Math.min(9, state.height - 1));
  const selectedIndex = data.frames.findIndex(f => f.id === state.selected);
  await page.locator('#frame-tabs button').nth(selectedIndex).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal((await page.evaluate(() => window.cpuCameraReport.getState())).selected, data.frames[(selectedIndex + 1) % data.frames.length].id);
  await page.evaluate(() => window.cpuCameraReport.select('copy'));
  assert.match(await page.locator('#pixel-difference').textContent(), /Matches the input pixel exactly/);
  await page.evaluate(() => window.cpuCameraReport.select('sobel'));
  assert.match(await page.locator('#roi-boundary').textContent(), /begin-marker store retirement/);
  await page.screenshot({ path: path.join(output, 'camera.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Camera mobile overflow');
  await page.screenshot({ path: path.join(output, 'camera-mobile.png'), fullPage: true });
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  const result = { gallery, report, cards, frames: data.frames.length, rawComparisons, cycleReports,
                   browser: browser.version(), errors, externalRequests: external.length, screenshots: output };
  fs.writeFileSync(path.join(output, 'report-check.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
