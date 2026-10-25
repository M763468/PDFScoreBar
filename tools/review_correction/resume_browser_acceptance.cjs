/* Real browser: immutable checkpoint -> uploaded annotated PDF -> isolated Save/Apply/undo.
 * No HTTP or engine mocks. Supply URL, private PDF path, evidence directory.
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const [url, pdf, evidence] = process.argv.slice(2);
  if (!url || !pdf || !evidence) throw new Error('Supply URL, PDF and evidence directory');
  fs.mkdirSync(evidence, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
  const report = {passed: false, errors: [], chromium: browser.version()};
  try {
    const page = await browser.newPage({viewport: {width: 1600, height: 1100}});
    page.on('pageerror', error => report.errors.push(error.message));
    await page.goto(url);
    await page.waitForFunction(() => currentPage && measures.length > 0);
    const initial = await page.evaluate(async () => (await fetch('/api/state')).json());
    report.originalIdentity = initial.package.current_identity;
    await page.locator('#historyPanel').evaluate(el => { el.open = true; });
    await page.waitForFunction(() => document.querySelector('#checkpointSelect').options.length > 0);
    const firstCheckpoint = await page.locator('#checkpointSelect').inputValue();
    const initialCount = await page.locator('#checkpointSelect option').count();
    await page.locator('#checkpointLabel').fill('browser saved state');
    await page.locator('#checkpointBtn').click();
    await page.waitForFunction(count => document.querySelector('#checkpointSelect').options.length > count, initialCount);
    // Explicitly select the older checkpoint, rather than always restoring latest.
    await page.locator('#checkpointSelect').selectOption(firstCheckpoint);
    await page.locator('#resumePdf').setInputFiles(pdf);
    await page.locator('#resumeBtn').click();
    await page.waitForURL('**/?session=s_*', {timeout: 180000});
    const sessionUrl = page.url();
    await page.waitForFunction(() => currentPage?.display_image && image.complete && measures.length > 0);
    report.session = new URL(sessionUrl).searchParams.get('session');
    const fresh = await page.evaluate(async () => (await fetch('/api/state')).json());
    if (fresh.package.current_result || fresh.package.last_successful_result) throw new Error('Resume inherited applied success');
    report.resumedCorrectionsIdentity = fresh.package.current_identity.corrections_identity;
    await page.screenshot({path: path.join(evidence, 'resumed.png')});
    const apply = async name => {
      await page.locator('#applyBtn').click();
      await page.waitForFunction(() => {
        const state = window.reviewCorrectionState.get();
        if (state?.package.status === 'error') throw new Error(JSON.stringify(state.package.last_application));
        return state?.package.current_result;
      }, null, {timeout: 240000});
      const state = await page.evaluate(() => window.reviewCorrectionState.get());
      report[name] = state.package.current_result;
      const link = await page.locator('#openResultBtn').getAttribute('href');
      if (!link.includes(`session=${report.session}`)) throw new Error('Result link lost its session');
      const response = await page.request.get(new URL(link, page.url()).href);
      const bytes = await response.body();
      if (!response.ok() || bytes.subarray(0, 5).toString() !== '%PDF-') throw new Error('Result PDF unavailable');
      fs.writeFileSync(path.join(evidence, `${name}.pdf`), bytes);
      await page.screenshot({path: path.join(evidence, `${name}.png`)});
      await page.waitForFunction(async () => {
        const history = await (await fetch('/api/checkpoints')).json();
        return history.applications.at(-1)?.status === 'succeeded';
      });
    };
    await apply('baseline');
    await page.locator('#typeSelect').selectOption('mmr_measure_span');
    const point = await page.evaluate(() => {
      const box = measures[0].bbox;
      const pos = imgToCanvas({x: (box[0]+box[2])/2, y: (box[1]+box[3])/2});
      const rect = canvas.getBoundingClientRect();
      return {x: rect.left + pos.x*rect.width/canvas.width, y: rect.top + pos.y*rect.height/canvas.height};
    });
    await page.mouse.click(point.x, point.y);
    await page.waitForFunction(() => selectedMeasure === measures[0]);
    await page.locator('#measureSpanInput').fill('2');
    await page.locator('#addItemBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending > 0);
    await page.locator('#saveBtn').click();
    await page.waitForFunction(() => {
      const pkg = window.reviewCorrectionState.get().package;
      return pkg.counts.pending === 0 && !pkg.current_result && pkg.last_successful_result;
    });
    await apply('edited');
    await page.locator('#deleteItemBtn').click();
    await page.locator('#saveBtn').click();
    await page.waitForFunction(() => !window.reviewCorrectionState.get().package.current_result);
    await apply('undone');
    await page.reload();
    await page.waitForFunction(() => window.reviewCorrectionState?.get()?.package.current_result);
    const originalTab = await browser.newPage();
    await originalTab.goto(url);
    const unchanged = await originalTab.evaluate(async () => (await fetch('/api/state')).json());
    if (JSON.stringify(unchanged.package.current_identity) !== JSON.stringify(initial.package.current_identity)) {
      throw new Error('Original package changed during resumed review');
    }
    if (report.errors.length) throw new Error(report.errors.join('\n'));
    report.applicationStatuses = await page.evaluate(async () =>
      (await (await fetch('/api/checkpoints')).json()).applications.map(item => item.status));
    if (report.applicationStatuses.join(',') !== 'succeeded,succeeded,succeeded') throw new Error('Application history lost an attempt');
    report.passed = true;
    console.log('Checkpoint selection / annotated upload / isolated Save / Apply / undo / reload passed');
  } catch (error) {
    report.failure = error.stack;
    throw error;
  } finally {
    fs.writeFileSync(path.join(evidence, 'browser-report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
