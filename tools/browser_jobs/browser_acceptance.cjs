/* Run against a distribution serve root with a one-page score PDF containing measures. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

async function assertRejectedWithoutPathLeak(response, label) {
  const status = response.status();
  assert.ok(status >= 400 && status < 500, `${label}: expected 4xx rejection, got ${status}`);
  const body = await response.text();
  const combined = `${response.statusText()}\n${body}`;
  const leakPattern =
    /resumed_sessions|manual_correction_input\.json|Traceback|\[Errno|\[WinError|[A-Za-z]:[\\/]|\\\\|(?:^|[\s'"(])\/(?:home|tmp|workspace|var|opt|mnt)\//i;
  assert.ok(!leakPattern.test(combined), `${label}: leaked internal path in error response: ${combined}`);
  return status;
}

async function main() {
  const [url, pdf, evidence, existingJob, existingFailure] = process.argv.slice(2);
  if (!url || !pdf || !evidence) throw new Error("Supply launcher URL, score PDF and evidence directory");
  fs.mkdirSync(evidence, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  });
  const errors = [];
  const report = { chromium: browser.version(), passed: false, errors };
  try {
    const page = await browser.newPage({ locale: "en-US", acceptDownloads: true, viewport: { width: 1600, height: 1100 } });
    page.setDefaultTimeout(30000);
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(url);
    await page.locator("#language").click();
    assert.equal(await page.locator("html").getAttribute("lang"), "ja");
    await page.locator("#language").click();
    const submit = async (name, buffer, pages) => {
      await page.locator("#pdf").setInputFiles({ name, mimeType: "application/pdf", buffer });
      await page.locator("#pages").fill(pages);
      const [response] = await Promise.all([
        page.waitForResponse(response => response.url() === new URL("/api/jobs", url).href &&
          response.request().method() === "POST"),
        page.locator("#start").click(),
      ]);
      assert.equal(response.status(), 200);
      const confirmation = page.locator("#submission-status").filter({ hasText: "Job submitted" });
      await confirmation.waitFor();
      const id = (await confirmation.textContent()).match(/job-[0-9a-f]{12,32}/)?.[0];
      assert.ok(id, "Job ID missing from browser confirmation");
      return id;
    };
    const source = fs.readFileSync(pdf);
    const row = jobId => page.locator("#jobs li").filter({ hasText: jobId });
    const id = existingJob || await submit("試用 score.pdf", source, "1");
    report.job = id;
    console.log("Selected numbering job", id);
    if (!existingJob) {
      await row(id).getByText(/Queued|Processing/).waitFor();
      console.log("Observed queued or running state");
    }
    const bad = existingFailure || await submit("broken.pdf", Buffer.from("not a PDF"), "");
    report.failedJob = bad;
    console.log("Selected invalid PDF job", bad);
    const ready = row(id).getByRole("link", { name: "Open correction GUI" });
    await ready.waitFor({ timeout: 600000 });
    await row(bad).getByText(/Failed.*PDF could not be read/).waitFor();
    assert.equal(await row(bad).getByRole("link").count(), 0);
    const expectedPdf = new URL(await row(id).getByRole("link", { name: "Open numbered PDF" }).getAttribute("href"), url);
    const original = await page.request.get(expectedPdf.href);
    assert.equal(original.status(), 200);
    assert.equal((await original.body()).subarray(0, 5).toString(), "%PDF-");
    const [download] = await Promise.all([
      page.waitForEvent("download"), row(id).getByRole("link", { name: "Download" }).click(),
    ]);
    assert.match(download.suggestedFilename(), /\.pdf$/);
    await page.screenshot({ path: path.join(evidence, "jobs.png") });
    console.log("Verified numbered PDF and download");
    await ready.click();
    const reviewUrl = page.url();
    assert.equal(new URL(reviewUrl).pathname, `/jobs/${id}/review/`);
    await page.waitForFunction(() => typeof currentPage !== "undefined" && currentPage && typeof measures !== "undefined" && measures.length > 0);
    await page.locator("#typeSelect").selectOption("mmr_measure_span");
    const point = await page.evaluate(() => {
      const box = measures[0].bbox;
      const position = imgToCanvas({ x: (box[0] + box[2]) / 2, y: (box[1] + box[3]) / 2 });
      const rect = canvas.getBoundingClientRect();
      return { x: rect.left + position.x * rect.width / canvas.width, y: rect.top + position.y * rect.height / canvas.height };
    });
    await page.mouse.click(point.x, point.y);
    await page.waitForFunction(() => selectedMeasure === measures[0]);
    await page.locator("#measureSpanInput").fill("2");
    await page.locator("#addItemBtn").click();
    await page.waitForFunction(() => window.reviewCorrectionState.get().package.counts.pending > 0);
    await page.locator("#saveBtn").click();
    await page.waitForFunction(() => {
      const state = window.reviewCorrectionState?.get()?.package;
      if (!state) return false;
      return state.counts.pending === 0 && state.current_identity.corrections_identity;
    });
    await page.locator("#applyBtn").click();
    await page.waitForFunction(() => {
      const state = window.reviewCorrectionState?.get()?.package;
      if (!state) return false;
      if (state.status === "error") throw new Error(JSON.stringify(state.last_application));
      return state.current_result;
    }, null, { timeout: 240000 });
    console.log("Saved and applied a correction");
    const resultLink = await page.locator("#openResultBtn").getAttribute("href");
    const corrected = await page.request.get(new URL(resultLink, reviewUrl).href);
    assert.equal(corrected.status(), 200);
    assert.equal((await corrected.body()).subarray(0, 5).toString(), "%PDF-");
    assert.deepEqual(await (await page.request.get(expectedPdf.href)).body(), await original.body());
    const reopened = await browser.newPage({ locale: "en-US" });
    reopened.setDefaultTimeout(30000);
    reopened.on("pageerror", error => errors.push(error.message));
    await reopened.goto(url);
    await reopened.locator(`a[href="/jobs/${id}/review/"]`).click();
    await reopened.waitForFunction(() => window.reviewCorrectionState?.get()?.package.current_result);
    await reopened.locator("#historyPanel").evaluate(panel => { panel.open = true; });
    await reopened.waitForFunction(() =>
      document.querySelector("#checkpointSelect").options.length > 0 &&
      !document.querySelector("#resumeBtn").disabled);
    await reopened.locator("#resumePdf").setInputFiles({ name: "original.pdf", mimeType: "application/pdf", buffer: source });
    const [resumedResponse] = await Promise.all([
      reopened.waitForResponse(response => response.url() === reviewUrl + "api/resume", { timeout: 180000 }),
      reopened.locator("#resumeBtn").click(),
    ]);
    assert.equal(resumedResponse.status(), 200);
    await reopened.waitForURL("**/review/?session=s_*", { timeout: 180000 });
    const resumed = new URL(reopened.url());
    assert.equal(resumed.pathname, new URL(reviewUrl).pathname);
    const session = resumed.searchParams.get("session");
    const crossed = await reopened.request.get(new URL(`/jobs/${bad}/review/api/state?session=${session}`, url).href);
    await assertRejectedWithoutPathLeak(crossed, "cross-job failed target");
    const unknownGet = await reopened.request.get(new URL(`/jobs/${id}/review/api/state?session=s_00000000000000000000000000000000`, url).href);
    assert.equal(await assertRejectedWithoutPathLeak(unknownGet, "unknown session GET"), 404);
    const unknownPost = await reopened.request.post(
      new URL(`/jobs/${id}/review/api/save?session=s_00000000000000000000000000000000`, url).href,
      {
        headers: {
          Origin: new URL(url).origin,
          "Content-Type": "application/json",
        },
        data: JSON.stringify({ page: 0, correction_type: "barline_construction", items: [] }),
      },
    );
    assert.equal(await assertRejectedWithoutPathLeak(unknownPost, "unknown session POST"), 404);
    const malformedGet = await reopened.request.get(new URL(`/jobs/${id}/review/api/state?session=../../other`, url).href);
    assert.equal(await assertRejectedWithoutPathLeak(malformedGet, "malformed session GET"), 400);
    await reopened.waitForFunction(() => typeof currentPage !== "undefined" && currentPage && typeof measures !== "undefined" && measures.length > 0);
    await reopened.screenshot({ path: path.join(evidence, "resumed.png") });
    assert.deepEqual(errors, []);
    report.session = session;
    report.passed = true;
    console.log("PDF submission / progress / failure / download / correction / apply / reopen / checkpoint resume passed");
  } catch (error) {
    report.failure = error.stack;
    throw error;
  } finally {
    fs.writeFileSync(path.join(evidence, "browser-report.json"), JSON.stringify(report, null, 2));
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
