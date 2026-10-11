/* Check the grouped navigation against actual generated cycle reports.
 * NODE_PATH=/path/to/node_modules node viewer/check_navigation.cjs \
 *   build/index.html build/browser/navigation
 * The gallery may also be a local HTTP URL. Generate gallery and images first.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const target = value => /^https?:\/\//.test(value) ? value : pathToFileURL(path.resolve(value)).href;

(async () => {
  assert.ok(process.argv[2], 'Supply a generated gallery path or URL');
  const gallery = target(process.argv[2]);
  const output = path.resolve(process.argv[3] || '/tmp/cpu-lab-navigation-check');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const errors = [], external = [], opened = [];
    context.on('page', page => page.on('pageerror', error => errors.push({ url: page.url(), error: String(error) })));
    context.on('request', request => {
      const url = new URL(request.url());
      if (/^https?:$/.test(url.protocol) && url.origin !== new URL(gallery).origin) external.push(url.href);
    });
    const page = await context.newPage();
    const reportPage = await context.newPage();
    await page.goto(gallery);
    await page.locator('#example-navigation').waitFor({ state: 'visible' });
    const catalog = await page.evaluate(() => JSON.parse(document.getElementById('navigation-data').textContent));
    const expected = catalog.groups.some(group => group.id === 'custom')
      ? [['simple', 'image', 'custom'], ['Simple test suite', 'Image processing', 'My applications']]
      : [['simple', 'image'], ['Simple test suite', 'Image processing']];
    assert.deepEqual(catalog.groups.map(group => group.id), expected[0]);
    assert.deepEqual(catalog.groups.map(group => group.title), expected[1]);
    assert.ok(catalog.groups.every(group => group.examples.length > 0), 'Generate both gallery and image examples first');
    const ids = catalog.groups.flatMap(group => group.examples.map(example => example.id));
    assert.equal(new Set(ids).size, ids.length, 'Catalog example IDs must be unique');

    for (const group of catalog.groups) {
      await page.locator('#navigation-group').selectOption(group.id);
      assert.deepEqual(await page.locator('#navigation-example option').evaluateAll(options => options.map(option => option.value)),
        group.examples.map(example => example.id));
      assert.deepEqual(await page.locator('.gallery-group').evaluateAll(groups => groups.filter(group => !group.hidden).map(group => group.dataset.groupId)), [group.id]);
      await page.screenshot({ path: path.join(output, `gallery-${group.id}.png`), fullPage: true });

      for (const example of group.examples) {
        await page.locator('#navigation-example').selectOption(example.id);
        const href = await page.locator('#navigation-open').getAttribute('href');
        assert.equal(await page.locator('#navigation-open').getAttribute('aria-disabled'), 'false');
        assert.equal(new URL(href, page.url()).href, new URL(example.href, gallery).href);
        // Follow the real Open control; target=_top navigates this top-level page.
        await reportPage.goto(gallery);
        await reportPage.locator('#navigation-group').selectOption(group.id);
        await reportPage.locator('#navigation-example').selectOption(example.id);
        await Promise.all([
          reportPage.waitForURL(new URL(example.href, gallery).href),
          reportPage.locator('#navigation-open').click(),
        ]);
        await reportPage.waitForFunction(() => window.cpuLabViewer);
        assert.equal(await reportPage.locator('#error').isVisible(), false);
        const actual = await reportPage.evaluate(() => {
          const data = JSON.parse(document.getElementById('trace-data').textContent);
          return { metadata: data.metadata, samples: data.trace.length };
        });
        assert.equal(actual.metadata.status, 'pass');
        assert.ok(actual.samples > 0, 'Cycle report must contain actual recorded samples');
        assert.equal(actual.metadata.navigation.current_id, example.id);
        assert.equal(await reportPage.locator('#navigation-group').inputValue(), group.id);
        assert.equal(await reportPage.locator('#navigation-example').inputValue(), example.id);
        const home = await reportPage.locator('#navigation-home').getAttribute('href');
        assert.equal(new URL(home, reportPage.url()).href, new URL(catalog.home_href, gallery).href);

        // A temporary group change must not forget the current report selection.
        const otherGroup = catalog.groups.find(candidate => candidate.id !== group.id);
        await reportPage.locator('#navigation-group').selectOption(otherGroup.id);
        await reportPage.locator('#navigation-example').selectOption(otherGroup.examples.at(-1).id);
        await reportPage.locator('#navigation-group').selectOption(group.id);
        assert.equal(await reportPage.locator('#navigation-example').inputValue(), example.id);
        opened.push({ group: group.id, id: example.id, href: example.href, samples: actual.samples,
          elf_sha256: actual.metadata.elf_sha256 });
      }

      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${group.id} gallery mobile overflow`);
      await page.screenshot({ path: path.join(output, `gallery-${group.id}-mobile.png`), fullPage: true });
      await reportPage.setViewportSize({ width: 390, height: 844 });
      assert.equal(await reportPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${group.id} cycle report mobile overflow`);
      await reportPage.screenshot({ path: path.join(output, `report-${group.id}-mobile.png`), fullPage: true });
      await reportPage.setViewportSize({ width: 1440, height: 1100 });
      await page.setViewportSize({ width: 1440, height: 1100 });
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, [], 'Navigation must not request external assets');
    const result = { status: 'pass', gallery, groups: catalog.groups.map(group => group.id),
      reports: opened, browser: browser.version(), errors, externalRequests: external.length, screenshots: output };
    fs.writeFileSync(path.join(output, 'navigation-check.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
