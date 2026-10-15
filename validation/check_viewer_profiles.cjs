// =============================================================================
// HY-RV | check_viewer_profiles
// Description: Check actual preset labels and the external-core reference-view boundary.
// Purpose: Computer architecture and RTL design education and lab exercises.
// Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
// Website: https://dsa.hanyang.ac.kr
// Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
// AI tools such as Codex or Claude may have assisted in creating or modifying
// this file. See applicable manifests and verification records for provenance.
// Preserve existing license, copyright, and original author notices.
// =============================================================================
// External/unknown pages are explicit render-only fixtures, not CPU measurements.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const base = path.resolve(process.argv[2] || 'build/validation-p1');
  const fixtures = path.join(base, 'viewer-profile-fixtures');
  const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const checks = [];
  const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  for (const preset of ['ant_j0', 'ant_j1', 'btfnt_j0', 'btfnt_j1']) {
    const file = path.join(base, preset, '04_muldiv-O2/trace.html');
    await page.goto(pathToFileURL(file).href);
    await page.waitForFunction(() => window.cpuLabViewer);
    const text = await page.locator('#value-early-jal').textContent();
    assert.match(text, preset.endsWith('j1') ? /\bON\b/ : /\bOFF\b/);
    assert.match(await page.locator('#value-bp-policy').textContent(), preset.startsWith('btfnt') ? /BTFNT/ : /ANT/);
    assert.equal(await page.locator('#architecture-diagram').isVisible(), true);
    assert.match(await page.locator('#core-profile-note').textContent(), new RegExp(preset));
    checks.push({preset, status:'pass', page_sha256:sha(file), early_jal_label:text});
  }
  for (const name of ['external', 'unknown']) {
    const file = path.join(fixtures, name, 'trace.html');
    await page.goto(pathToFileURL(file).href);
    await page.waitForFunction(() => window.cpuLabViewer);
    assert.equal(await page.locator('#architecture-diagram').isVisible(), false);
    assert.match(await page.locator('#core-profile-note').textContent(), /reference|not.*P1|not recorded/i);
    checks.push({fixture:name, status:'pass', scope:'render-only fixture; no external CPU measurement', page_sha256:sha(file)});
  }
  assert.deepEqual(errors, []);
  fs.mkdirSync(path.join(base, 'browser-profiles'), {recursive:true});
  const receipt = {status:'pass', browser:browser.version(), checks, errors};
  fs.writeFileSync(path.join(base, 'browser-profiles/receipt.json'), JSON.stringify(receipt, null, 2)+'\n');
  console.log(JSON.stringify(receipt, null, 2));
  await browser.close();
})().catch(error => {console.error(error); process.exit(1);});
