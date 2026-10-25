/* History and uploaded-PDF resume are bound to the active local review package. */
(() => {
  const session = new URLSearchParams(location.search).get("session");
  window.reviewURL = (url) => {
    if (!session) return url;
    const result = new URL(url, location.href);
    result.searchParams.set("session", session);
    return result.pathname + result.search;
  };
  const originalFetch = window.fetch.bind(window);
  window.fetch = (url, options) => originalFetch(
    typeof url === "string" && (url.startsWith("/api/") || url.startsWith("/file?"))
      ? window.reviewURL(url) : url, options,
  );
  window.addEventListener("DOMContentLoaded", () => {
    const panel = document.getElementById("historyPanel");
    const list = document.getElementById("checkpointSelect");
    const status = document.getElementById("historyStatus");
    const copy = () => window.ReviewStrings.history;
    let checkpoints = [];
    const request = async (path, body) => {
      const response = await fetch(path, body === undefined ? {} : {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`${copy().failed} (${response.status})`);
      return response.json();
    };
    const refresh = async () => {
      checkpoints = (await request("/api/checkpoints")).checkpoints;
      list.replaceChildren();
      for (const item of [...checkpoints].reverse()) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `${new Date(item.created_at).toLocaleString()} ${item.label || item.id.slice(0, 11)}`;
        list.appendChild(option);
      }
      document.getElementById("resumeBtn").disabled = Boolean(session) || !checkpoints.some(x => x.can_resume_pdf);
    };
    const action = (id, callback) => {
      document.getElementById(id).addEventListener("click", async () => {
        panel.querySelectorAll("button").forEach(x => { x.disabled = true; });
        status.textContent = copy().working;
        try { await callback(); status.textContent = copy().saved; }
        catch (error) { status.textContent = error.message; }
        finally {
          panel.querySelectorAll("button").forEach(x => { x.disabled = false; });
          await refresh().catch(error => { status.textContent = error.message; });
        }
      });
    };
    action("checkpointBtn", async () => {
      await request("/api/checkpoints", {label: document.getElementById("checkpointLabel").value});
    });
    action("resumeBtn", async () => {
      const item = checkpoints.find(x => x.id === list.value);
      if (!item?.can_resume_pdf) throw new Error(copy().noSource);
      const file = document.getElementById("resumePdf").files[0];
      if (!file || file.size > 32000000) throw new Error(copy().choosePdf);
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 32768) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
      }
      const result = await request("/api/resume", {checkpoint_id: item.id, pdf_base64: btoa(binary)});
      location.assign(result.url);
    });
    refresh().catch(error => { status.textContent = error.message; });
    window.addEventListener("review-corrections-recorded", () => refresh().catch(() => {}));
  });
})();
