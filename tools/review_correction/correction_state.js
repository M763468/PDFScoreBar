/* Product state for the package-scoped user entry only. Engine semantics stay on the server. */
(() => {
  const panel = document.getElementById("correctionStatePanel") || document.createElement("section");
  panel.id = "correctionStatePanel";
  panel.setAttribute("aria-live", "polite");
  if (!panel.parentNode) document.getElementById("sidebarHeader").appendChild(panel);
  let updateChain = Promise.resolve();
  let latestState = null;
  const typeNames = {
    mmr_measure_span: "Measure span", measure_construction: "Measure",
    barline_construction: "Barline", movement_boundary: "Movement boundary",
  };
  const request = async (url, body) => {
    const response = await fetch(url, body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.json();
  };
  function render(state) {
    latestState = state;
    panel.replaceChildren();
    const heading = document.createElement("strong");
    heading.textContent = "Correction status";
    panel.appendChild(heading);
    const summary = document.createElement("div");
    summary.className = "small";
    summary.textContent = (state.labels || {})[state.package.status] || state.package.status;
    panel.appendChild(summary);
    for (const entry of state.states || []) {
      const line = document.createElement("div");
      line.className = "small";
      const statuses = [entry.edit_status, entry.recording_status, entry.application_status]
        .filter(Boolean).map(key => (state.labels || {})[key] || key);
      line.textContent = `Page ${Number(entry.page) + 1} · ${typeNames[entry.correction_type] || entry.correction_type}: ${statuses.join(" · ")}`;
      if (entry.error) line.textContent += ` · ${entry.error}`;
      panel.appendChild(line);
    }
    window.dispatchEvent(new CustomEvent("correction-state", {detail: state}));
  }
  async function refresh() { render(await request("/api/state")); }
  function enqueue(operation) {
    const result = updateChain.then(operation);
    updateChain = result.catch(error => {
      panel.textContent = `Correction status unavailable: ${error.message}`;
    });
    return result;
  }
  const originalDirty = setDirty;
  setDirty = function(type, dirty) {
    originalDirty(type, dirty);
    if (!currentPage) return;
    const page = pageValue();
    const items = JSON.parse(JSON.stringify(itemsForCurrentPage(type)));
    enqueue(async () => {
      await request(dirty ? "/api/state/pending" : "/api/state/pending/clear",
        dirty ? {page, correction_type: type, items} : {page, correction_type: type});
      await refresh();
    });
  };
  const originalSave = saveCorrectionPage;
  saveCorrectionPage = function(type, page, items) {
    const captured = JSON.parse(JSON.stringify(items));
    return enqueue(async () => {
      await request("/api/state/pending", {page, correction_type: type, items: captured});
      try { return await originalSave(type, page, captured); }
      finally { await refresh(); }
    });
  };
  // Finalizing movement review changes the consumed correction set as well.
  exportMovementBtn.addEventListener("click", () => {
    const timer = setInterval(() => { if (!exportMovementBtn.disabled) { clearInterval(timer); enqueue(refresh); } }, 100);
  });
  window.reviewCorrectionState = {refresh: () => enqueue(refresh), ready: () => updateChain, get: () => latestState};
  enqueue(refresh);
})();
