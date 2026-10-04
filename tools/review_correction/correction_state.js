/* Product state for the package-scoped user entry only. Engine semantics stay on the server. */
(() => {
  const panel = document.getElementById("correctionStatePanel") || document.createElement("section");
  panel.id = "correctionStatePanel";
  panel.setAttribute("aria-live", "polite");
  if (!panel.parentNode) document.getElementById("sidebarHeader").appendChild(panel);
  let updateChain = Promise.resolve();
  let latestState = null;
  const request = async (url, body) => {
    const response = await fetch(url, body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`${window.ReviewStrings.state.requestFailed} (${response.status})`);
    return response.json();
  };
  function render(state) {
    const copy = window.ReviewStrings.state;
    latestState = state;
    panel.replaceChildren();
    const heading = document.createElement("strong");
    heading.textContent = copy.heading;
    if (!document.getElementById("statePanel")) panel.appendChild(heading);
    const summary = document.createElement("div");
    summary.className = "small";
    const statusNames = window.ReviewStrings.state.statuses || {};
    summary.textContent = `${statusNames[state.package.status] || (state.labels || {})[state.package.status] || state.package.status} · ${state.package.counts.pending} ${copy.pending} · ${state.package.counts.recorded} ${copy.recorded} · ${state.package.counts.error} ${copy.errors}`;
    panel.appendChild(summary);
    for (const entry of state.states || []) {
      if (currentPage && String(entry.page) !== String(pageValue())) continue;
      const line = document.createElement("div");
      line.className = "small";
      const statuses = [entry.edit_status === "none" ? null : entry.edit_status, entry.recording_status]
        .filter(Boolean).map(key => statusNames[key] || (state.labels || {})[key] || key);
      const typeName = copy.types[entry.correction_type] || entry.correction_type;
      line.textContent = `${copy.page} ${Number(entry.page) + 1} · ${typeName}: ${statuses.join(" · ")}`;
      if (entry.error) line.textContent += ` · ${entry.error}`;
      panel.appendChild(line);
    }
    const identity = document.getElementById("resultIdentity");
    if (identity) identity.textContent = `${copy.source}: ${state.package.current_identity.source_identity} · ${copy.result}: ${state.package.last_successful_result?.result_identity || "—"}`;
    window.dispatchEvent(new CustomEvent("correction-state", {detail: state}));
  }
  async function refresh() { render(await request("/api/state")); }
  function enqueue(operation) {
    const result = updateChain.then(operation);
    updateChain = result.catch(error => {
      panel.textContent = `${window.ReviewStrings.state.unavailable}: ${error.message}`;
    });
    return result;
  }
  const originalControls = updateControlState;
  updateControlState = function() {
    originalControls();
    if (latestState) render(latestState);
  };
  const recordedDrafts = new Map();
  const draftKey = (page, type) => JSON.stringify([String(page), type]);
  const originalDirty = setDirty;
  setDirty = function(type, dirty) {
    if (!currentPage) { originalDirty(type, dirty); return; }
    const page = pageValue();
    const items = JSON.parse(JSON.stringify(itemsForCurrentPage(type)));
    // The save completion belongs to its captured draft, not a newer editor value.
    if (!dirty && recordedDrafts.get(draftKey(page, type)) !== JSON.stringify(items)) dirty = true;
    originalDirty(type, dirty);
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
      try {
        const result = await originalSave(type, page, captured);
        recordedDrafts.set(draftKey(page, type), JSON.stringify(captured));
        return result;
      }
      finally { await refresh(); }
    });
  };
  const feedback = (key, values, fallback) => {
    const template = window.ReviewStrings?.feedback?.[key] || fallback;
    return template.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
  };
  // Navigation must also keep edits made while its automatic save is in flight.
  switchPage = function(nextIndex) {
    if (nextIndex === currentIndex) return;
    return waitForMovementSaves()
      .then(() => saveCorrectionTypes(Array.from(dirtyTypes)))
      .then(() => {
        if (dirtyTypes.size) {
          saveStatus.textContent = feedback("pageEditedDuringSave", {},
            "New edits remain unsaved. Save them before changing page.");
          return;
        }
        currentIndex = nextIndex;
        loadPage();
      })
      .catch(error => {
        saveStatus.textContent = feedback("pageSaveFailed", {error: error.message},
          "Page change stopped because saving failed: {error}");
      });
  };
  // This user-only adapter observes completion of the actual finalization request.
  exportMovementBtn.onclick = async function(event) {
    event.currentTarget.blur();
    releaseTransientInteraction();
    const remaining = unresolvedMovementSuggestionCount();
    if (remaining > 0) {
      saveStatus.textContent = feedback("finishBlocked", {count: remaining},
        "Review the remaining {count} boundary suggestions before finishing.");
      return;
    }
    try {
      await waitForMovementSaves();
      const data = await request("/api/export_movement_boundaries", {});
      saveStatus.textContent = feedback("finishMovement", {count: data.count},
        "Movement review finished. {count} confirmed boundaries are ready for the next numbering run.");
    } catch (error) {
      saveStatus.textContent = feedback("finishMovementFailed", {error: error.message},
        "Could not finish movement review: {error}");
    } finally {
      await enqueue(refresh);
    }
  };
  window.reviewCorrectionState = {refresh: () => enqueue(refresh), ready: () => updateChain, get: () => latestState};
  enqueue(refresh);
})();

/* Apply controls consume server state; no correction interpretation lives here. */
(() => {
  const copy = () => window.ReviewStrings.result;
  // Keep result controls outside the refreshed state panel so they survive state updates.
  let host = document.getElementById("applicationControls");
  if (!host) {
    host = document.createElement("section");
    host.id = "applicationControls";
    document.getElementById("sidebarHeader").appendChild(host);
  }
  let apply = document.getElementById("applyBtn");
  let open = document.getElementById("openResultBtn");
  let status = document.getElementById("applicationStatus");
  if (!apply) {
    apply = document.createElement("button"); apply.id = "applyBtn"; apply.className = "btn";
    apply.textContent = copy().apply; host.appendChild(apply);
  }
  if (!open) {
    open = document.createElement("a"); open.id = "openResultBtn"; open.className = "btn";
    open.textContent = copy().open; host.appendChild(open);
  }
  if (!status) { status = document.createElement("div"); status.id = "applicationStatus"; host.appendChild(status); }
  apply.textContent = copy().apply;
  open.textContent = copy().open;
  let timer = null;
  function update(state) {
    if (!state) return;
    const strings = copy();
    apply.textContent = strings.apply;
    open.textContent = strings.open;
    const summary = state.package;
    const running = (state.states || []).some(entry => entry.application_status === "applying");
    const pending = summary.counts.pending > 0;
    const errors = (state.states || []).some(entry => entry.error && entry.application_status !== "error");
    apply.disabled = running || pending || errors;
    const last = summary.last_successful_result;
    open.hidden = !last;
    open.href = "/api/result"; open.target = "_blank"; open.rel = "noopener";
    status.textContent = running ? strings.running : pending ? strings.pending
      : last && !summary.current_result ? strings.stale
      : last ? strings.current : strings.ready;
    const failure = (state.states || []).find(entry => entry.error);
    if (failure) status.textContent = `${strings.failure}: ${failure.error}`;
    if (running && !timer) timer = setInterval(() => window.reviewCorrectionState.refresh().catch(() => {}), 1000);
    if (!running && timer) { clearInterval(timer); timer = null; }
  }
  window.addEventListener("correction-state", event => update(event.detail));
  window.reviewApplyResult = {refresh: () => update(window.reviewCorrectionState?.get())};
  apply.onclick = async () => {
    apply.disabled = true;
    try {
      await window.reviewCorrectionState.ready();
      const response = await fetch("/api/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      if (!response.ok) throw new Error(`${copy().requestFailed} (${response.status})`);
      await window.reviewCorrectionState.refresh();
    } catch (error) {
      status.textContent = `${copy().failure}: ${error.message}`;
      apply.disabled = false;
    }
  };
  if (window.reviewCorrectionState.get()) update(window.reviewCorrectionState.get());
})();
