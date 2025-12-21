const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const pageSelect = document.getElementById("pageSelect");
const categoryFilter = document.getElementById("categoryFilter");
const labelButtons = document.getElementById("labelButtons");
const statusEl = document.getElementById("status");
const boxList = document.getElementById("boxList");
const pageMeta = document.getElementById("pageMeta");
const showOverlay = document.getElementById("showOverlay");
const showBoxes = document.getElementById("showBoxes");
const saveBtn = document.getElementById("saveBtn");
const summaryBtn = document.getElementById("summaryBtn");
const clearLabelBtn = document.getElementById("clearLabel");

let manifest = null;
let labelsConfig = null;
let currentPage = null;
let boxes = [];
let labels = {};
let activeLabel = null;
let activeBoxId = null;
let baseImg = new Image();
let overlayImg = new Image();

const categoryColors = {
  final_matched: "#00FF00",
  final_unmatched: "#FF0000",
  rejected_row: "#FFA500",
  rejected_geom: "#8000FF",
  fn_target_unmatched: "#FF00FF",
};

function setStatus(msg) {
  statusEl.textContent = msg;
}

function fetchJSON(path) {
  return fetch(path).then((r) => r.json());
}

function updateCanvasSize() {
  canvas.width = baseImg.width;
  canvas.height = baseImg.height;
}

function draw() {
  if (!baseImg.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(baseImg, 0, 0);
  if (showOverlay.checked && overlayImg.src) {
    if (overlayImg.complete) {
      ctx.drawImage(overlayImg, 0, 0);
    }
  }
  if (!showBoxes.checked) return;
  const filtered = getFilteredBoxes();
  filtered.forEach((b) => {
    const color = categoryColors[b.category] || "#FFFFFF";
    ctx.strokeStyle = color;
    ctx.lineWidth = b.id === activeBoxId ? 3 : 2;
    ctx.strokeRect(b.bbox[0], b.bbox[1], b.bbox[2] - b.bbox[0], b.bbox[3] - b.bbox[1]);
  });
}

function getFilteredBoxes() {
  const cat = categoryFilter.value;
  if (cat === "all") return boxes;
  return boxes.filter((b) => b.category === cat);
}

function populateBoxList() {
  boxList.innerHTML = "";
  const filtered = getFilteredBoxes();
  filtered.forEach((b) => {
    const div = document.createElement("div");
    div.className = "list-item" + (b.id === activeBoxId ? " active" : "");
    div.textContent = `${b.id} | ${b.category} | ${b.provenance || "n/a"} | label: ${labels[b.id] || "-"}`;
    div.onclick = () => {
      activeBoxId = b.id;
      draw();
      populateBoxList();
    };
    boxList.appendChild(div);
  });
}

function loadPage(page) {
  currentPage = page;
  pageMeta.textContent = page.name;
  return Promise.all([
    fetchJSON(`/file?path=${encodeURIComponent(page.boxes)}`),
  ]).then(([boxData]) => {
    boxes = boxData;
    labels = {};
    activeBoxId = null;
    baseImg = new Image();
    overlayImg = new Image();
    baseImg.onload = () => {
      updateCanvasSize();
      draw();
    };
    overlayImg.onload = () => draw();
    baseImg.src = `/file?path=${encodeURIComponent(page.image)}`;
    overlayImg.src = page.overlay ? `/file?path=${encodeURIComponent(page.overlay)}` : "";
    populateBoxList();
    draw();
  });
}

function initLabels() {
  labelButtons.innerHTML = "";
  labelsConfig.labels.forEach((label) => {
    const btn = document.createElement("button");
    btn.className = "label-btn";
    btn.textContent = label;
    btn.onclick = () => {
      activeLabel = label;
      document.querySelectorAll(".label-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    };
    labelButtons.appendChild(btn);
  });
}

canvas.addEventListener("click", (e) => {
  const rect = canvas.getBoundingClientRect();
  const x = Math.round((e.clientX - rect.left) * (canvas.width / rect.width));
  const y = Math.round((e.clientY - rect.top) * (canvas.height / rect.height));
  const filtered = getFilteredBoxes();
  const hit = filtered.find((b) => x >= b.bbox[0] && x <= b.bbox[2] && y >= b.bbox[1] && y <= b.bbox[3]);
  if (!hit) return;
  activeBoxId = hit.id;
  if (activeLabel) {
    labels[hit.id] = activeLabel;
  }
  draw();
  populateBoxList();
});

categoryFilter.addEventListener("change", () => {
  populateBoxList();
  draw();
});

showOverlay.addEventListener("change", draw);
showBoxes.addEventListener("change", draw);

clearLabelBtn.addEventListener("click", () => {
  if (!activeBoxId) return;
  delete labels[activeBoxId];
  populateBoxList();
});

saveBtn.addEventListener("click", () => {
  if (!currentPage) return;
  fetch("/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page: currentPage.name, labels }),
  })
    .then((r) => r.json())
    .then((data) => setStatus(`Saved: ${data.path}`))
    .catch((err) => setStatus(`Save failed: ${err}`));
});

summaryBtn.addEventListener("click", () => {
  fetch("/summary", { method: "POST" })
    .then((r) => r.json())
    .then((data) => setStatus(`Summary: ${data.path}`))
    .catch((err) => setStatus(`Summary failed: ${err}`));
});

Promise.all([fetchJSON("/manifest"), fetchJSON("/labels")]).then(([m, l]) => {
  manifest = m;
  labelsConfig = l;
  initLabels();
  pageSelect.innerHTML = "";
  manifest.pages.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.name;
    pageSelect.appendChild(opt);
  });
  const categories = ["all", ...new Set(manifest.pages.flatMap((p) => []))];
  categoryFilter.innerHTML = "";
  ["all", "final_unmatched", "final_matched", "rejected_row", "rejected_geom", "fn_target_unmatched"].forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    categoryFilter.appendChild(opt);
  });
  loadPage(manifest.pages[0]);
});

pageSelect.addEventListener("change", () => {
  const page = manifest.pages.find((p) => p.name === pageSelect.value);
  if (page) loadPage(page);
});
