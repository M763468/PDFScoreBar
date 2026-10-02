/* Optional real Chromium workflow. No application/API mocks.
 * PLAYWRIGHT_MODULE points to an installed Playwright module; CHROMIUM_PATH is optional.
 * node tools/review_correction/browser_acceptance.cjs URL EVIDENCE_DIRECTORY
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const [url, evidence] = process.argv.slice(2);
  if (!url || !evidence) throw new Error('Provide URL and evidence directory');
  fs.mkdirSync(evidence, { recursive: true });
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.waitForFunction(() => window.reviewCorrectionState && currentPage && measures.length);
    // Select the known retained first measure; use the actual UI for edit/save/apply.
    await page.evaluate(() => { selectedMeasure = measures[0]; updateSelectionMeta(); updateActionButtons(); });
    await page.locator('#measureSpanInput').fill('2');
    await page.locator('#addItemBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending > 0);
    if (!await page.locator('#applyBtn').isDisabled()) throw new Error('Pending edit permits apply');
    await page.locator('#saveBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending === 0);
    const recorded = await page.evaluate(() => window.reviewCorrectionState.get());
    if (recorded.package.current_result) throw new Error('Save reports a current applied result');
    await page.locator('#applyBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.current_result, {timeout: 180000});
    const applied = await page.evaluate(() => window.reviewCorrectionState.get());
    const response = await page.request.get(new URL(await page.locator('#openResultBtn').getAttribute('href'), url).href);
    const pdf = await response.body();
    if (response.status() !== 200 || !pdf.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
      throw new Error('Browser result is not a PDF');
    }
    fs.writeFileSync(path.join(evidence, 'browser-result.pdf'), pdf);
    await page.screenshot({path: path.join(evidence, 'applied.png')});
    await page.locator('#deleteItemBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending > 0);
    await page.locator('#saveBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.stale > 0);
    const stale = await page.evaluate(() => window.reviewCorrectionState.get());
    if (stale.package.current_result || stale.package.last_successful_result.identity !== applied.package.current_result.identity) {
      throw new Error('Correction removal did not preserve the previous stale result');
    }
    await page.screenshot({path: path.join(evidence, 'stale.png')});
    if (errors.length) throw new Error(errors.join('\n'));
    fs.writeFileSync(path.join(evidence, 'browser-report.json'), JSON.stringify({
      passed: true, recorded, applied, stale, errors, chromium: browser.version()
    }, null, 2));
    console.log('Browser save/apply/PDF/stale workflow passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
