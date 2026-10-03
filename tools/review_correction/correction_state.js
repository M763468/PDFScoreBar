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
