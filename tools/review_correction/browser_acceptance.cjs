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
    await page.waitForFunction(() => document.querySelectorAll('#pageList button').length === pages.length);
    const pageChoices = page.locator('#pageList button');
    if (await pageChoices.count() !== await page.evaluate(() => pages.length) || await page.locator('#pageList button[aria-current="page"]').count() !== 1) {
      throw new Error('Page navigation does not expose the current page accessibly');
    }
    await page.locator('#nextPageBtn').click();
    await page.waitForFunction(() => currentIndex === 1 && currentPage && measures.length > 0);
    await page.locator('#previousPageBtn').click();
    await page.waitForFunction(() => currentIndex === 0 && currentPage && measures.length > 0);
    const firstMeasurePoint = async () => page.evaluate(() => {
      const box = measures[0].bbox;
      const point = imgToCanvas({x: (box[0] + box[2]) / 2, y: (box[1] + box[3]) / 2});
      const rect = canvas.getBoundingClientRect();
      return {x: rect.left + point.x * rect.width / canvas.width, y: rect.top + point.y * rect.height / canvas.height};
    });
    await page.locator('#canvas').focus();
    const firstMeasure = await firstMeasurePoint();
    await page.mouse.click(firstMeasure.x, firstMeasure.y);
    await page.waitForFunction(() => selectedMeasure === measures[0]);
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => selectedMeasure === measures[1]);
    await page.keyboard.press('ArrowLeft');
    await page.waitForFunction(() => selectedMeasure === measures[0]);

    await page.locator('#typeSelect').selectOption('barline_construction');
    await page.waitForFunction(() => barlines.length > 0);
    const firstBarlinePoint = await page.evaluate(() => {
      const box = barlines[0].bbox;
      const point = imgToCanvas({x: (box[0] + box[2]) / 2, y: (box[1] + box[3]) / 2});
      const rect = canvas.getBoundingClientRect();
      return {x: rect.left + point.x * rect.width / canvas.width, y: rect.top + point.y * rect.height / canvas.height};
    });
    await page.mouse.click(firstBarlinePoint.x, firstBarlinePoint.y);
    await page.waitForFunction(() => selectedBarline === barlines[0]);
    await page.locator('#opSelect').selectOption('remove_barline');
    await page.locator('#addItemBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending > 0);
    await page.locator('#saveBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending === 0);

    await page.locator('#typeSelect').selectOption('movement_boundary');
    await page.locator('#itemListHeading').click();
    const firstSystemPoint = await page.evaluate(() => {
      const box = systemBounds(0);
      const point = imgToCanvas({x: (box[0] + box[2]) / 2, y: (box[1] + box[3]) / 2});
      const rect = canvas.getBoundingClientRect();
      return {x: rect.left + point.x * rect.width / canvas.width, y: rect.top + point.y * rect.height / canvas.height};
    });
    await page.mouse.click(firstSystemPoint.x, firstSystemPoint.y);
    await page.waitForFunction(() => selectedMovementSystem === 0);
    await page.locator('#movementAfterBtn').click();
    await page.waitForFunction(() => document.querySelector('#saveStatus').textContent.includes('Saved a boundary after') || document.querySelector('#saveStatus').textContent.includes('境界を保存しました'));
    const movementRows = await page.locator('#itemList').innerText();
    if (!movementRows.includes('After Page 1 / System 1') && !movementRows.includes('ページ1・段1の後')) {
      throw new Error('Movement boundary added after a system is not shown at its source location');
    }

    await page.locator('#typeSelect').selectOption('mmr_measure_span');
    await page.mouse.click(firstMeasure.x, firstMeasure.y);
    await page.waitForFunction(() => selectedMeasure === measures[0]);
    await page.locator('#measureSpanInput').fill('2');
    await page.locator('#addItemBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending > 0);
    if (!await page.locator('#applyBtn').isDisabled()) throw new Error('Pending edit permits apply');
    await page.locator('#saveBtn').click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending === 0);
    const recorded = await page.evaluate(() => window.reviewCorrectionState.get());
    if (recorded.package.current_result) throw new Error('Save reports a current applied result');
    await page.locator('#previewNumbersBtn').click();
    await page.waitForFunction(() => document.querySelector('#saveStatus').textContent.includes('Provisional numbering updated') || document.querySelector('#saveStatus').textContent.includes('仮番号'));
    if (await page.locator('#previewNumbersBtn').getAttribute('aria-pressed') !== 'true') {
      throw new Error('Numbering preview is not exposed as active');
    }
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
