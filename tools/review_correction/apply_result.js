/* Apply controls consume server state; no correction interpretation lives here. */
(() => {
  const copy = window.ReviewStrings.result;
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
    apply.textContent = copy.apply; host.appendChild(apply);
  }
  if (!open) {
    open = document.createElement("a"); open.id = "openResultBtn"; open.className = "btn";
    open.textContent = copy.open; host.appendChild(open);
  }
  if (!status) { status = document.createElement("div"); status.id = "applicationStatus"; host.appendChild(status); }
  apply.textContent = copy.apply;
  open.textContent = copy.open;
  let timer = null;
  function update(state) {
    const summary = state.package;
    const running = (state.states || []).some(entry => entry.application_status === "applying");
    const pending = summary.counts.pending > 0;
    const errors = (state.states || []).some(entry => entry.error && entry.application_status !== "error");
    apply.disabled = running || pending || errors;
    const last = summary.last_successful_result;
    open.hidden = !last;
    open.href = "/api/result"; open.target = "_blank"; open.rel = "noopener";
    status.textContent = running ? copy.running : pending ? copy.pending
      : last && !summary.current_result ? copy.stale
      : last ? copy.current : copy.ready;
    const failure = (state.states || []).find(entry => entry.error);
    if (failure) status.textContent = `${copy.failure}: ${failure.error}`;
    if (running && !timer) timer = setInterval(() => window.reviewCorrectionState.refresh().catch(() => {}), 1000);
    if (!running && timer) { clearInterval(timer); timer = null; }
  }
  window.addEventListener("correction-state", event => update(event.detail));
  apply.onclick = async () => {
    apply.disabled = true;
    try {
      await window.reviewCorrectionState.ready();
      const response = await fetch("/api/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      if (!response.ok) throw new Error(`${copy.requestFailed} (${response.status})`);
      await window.reviewCorrectionState.refresh();
    } catch (error) {
      status.textContent = error.message;
      apply.disabled = false;
    }
  };
  if (window.reviewCorrectionState.get()) update(window.reviewCorrectionState.get());
})();
