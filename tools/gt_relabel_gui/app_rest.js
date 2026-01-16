let pages = [];
let currentIndex = 0;
let currentPage = null;

let measures = [];
let restCounts = new Map();
let selectedIndex = null;
let dirty = false;

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

const pageMeta = document.getElementById("pageMeta");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const saveBtn = document.getElementById("saveBtn");
const saveStatus = document.getElementById("saveStatus");
const dirtyStatus = document.getElementById("dirtyStatus");
const measureList = document.getElementById("measureList");
const selectedMeta = document.getElementById("selectedMeta");
const restCountInput = document.getElementById("restCountInput");
const applyBtn = document.getElementById("applyBtn");
const resetBtn = document.getElementById("resetBtn");

let image = new Image();
let viewScale = 1.0;
let viewOffset = { x: 0, y: 0 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let panOrigin = { x: 0, y: 0 };
let spaceDown = false;

const COLOR_MEASURE = "#3aa3ff";
const COLOR_MULTI = "#ff4d4f";
const COLOR_SELECTED = "#ffa940";

function fetchJSON(url) {
  return fetch(url).then((r) => r.json());
}

function setDirty(next) {
  dirty = next;
  dirtyStatus.textContent = dirty ? "Unsaved changes" : "";
}

function resetView() {
  const container = canvas.parentElement;
  canvas.width = container.clientWidth;
  canvas.height = container.clientHeight;
  const scaleX = canvas.width / image.width;
  const scaleY = canvas.height / image.height;
  viewScale = Math.min(scaleX, scaleY);
  const drawWidth = image.width * viewScale;
  const drawHeight = image.height * viewScale;
  viewOffset = {
    x: (canvas.width - drawWidth) / 2,
    y: (canvas.height - drawHeight) / 2,
  };
}

function imgToCanvas(pt) {
  return {
    x: pt.x * viewScale + viewOffset.x,
    y: pt.y * viewScale + viewOffset.y,
  };
}

function canvasToImg(pt) {
  return {
    x: (pt.x - viewOffset.x) / viewScale,
    y: (pt.y - viewOffset.y) / viewScale,
  };
}

function drawBox(box, color, thickness) {
  const [x1, y1, x2, y2] = box;
  const p1 = imgToCanvas({ x: x1, y: y1 });
  const p2 = imgToCanvas({ x: x2, y: y2 });
  ctx.strokeStyle = color;
  ctx.lineWidth = thickness;
  ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
}

function drawLabel(box, text, color) {
  const [x1, y1] = box;
  const p = imgToCanvas({ x: x1, y: y1 });
  ctx.font = "11px Arial";
  const textWidth = ctx.measureText(text).width;
  const padding = 3;
  ctx.fillStyle = "rgba(0,0,0,0.6)";
  ctx.fillRect(p.x, p.y - 14, textWidth + padding * 2, 14);
  ctx.fillStyle = color;
  ctx.fillText(text, p.x + padding, p.y - 3);
}

function renderMeasureList() {
  measureList.innerHTML = "";
  measures.forEach((m, idx) => {
    const div = document.createElement("div");
    div.className = "list-item" + (idx === selectedIndex ? " active" : "");
    const count = restCounts.get(idx) || 1;
    div.textContent = `ROI ${idx + 1} | M${m.number ?? "-"} | rest=${count}`;
    div.onclick = () => {
      selectedIndex = idx;
      restCountInput.value = count;
      updateSelectedMeta();
      draw();
      renderMeasureList();
    };
    measureList.appendChild(div);
  });
}

function updateSelectedMeta() {
  if (selectedIndex === null) {
    selectedMeta.textContent = "None";
    return;
  }
  const m = measures[selectedIndex];
  const count = restCounts.get(selectedIndex) || 1;
  selectedMeta.textContent = `ROI ${selectedIndex + 1} | Measure ${m.number ?? "-"} | Rest ${count}`;
}

function draw() {
  if (!image.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const drawWidth = image.width * viewScale;
  const drawHeight = image.height * viewScale;
  ctx.drawImage(image, viewOffset.x, viewOffset.y, drawWidth, drawHeight);

  measures.forEach((m, idx) => {
    const count = restCounts.get(idx) || 1;
    const isSelected = idx === selectedIndex;
    const color = count > 1 ? COLOR_MULTI : COLOR_MEASURE;
    drawBox(m.bbox, color, isSelected ? 3 : 1.5);
    if (isSelected) {
      drawBox(m.bbox, COLOR_SELECTED, 3);
    }
    drawLabel(m.bbox, `R${idx + 1}`, color);
  });
}

function pointInBox(pt, box) {
  const [x1, y1, x2, y2] = box;
  const minX = Math.min(x1, x2);
  const maxX = Math.max(x1, x2);
  const minY = Math.min(y1, y2);
  const maxY = Math.max(y1, y2);
  return pt.x >= minX && pt.x <= maxX && pt.y >= minY && pt.y <= maxY;
}

function loadRestGT(path) {
  if (!path) {
    return Promise.resolve({});
  }
  return fetchJSON(`/api/template?path=${encodeURIComponent(path)}`).catch(() => ({}));
}

function applyRestGT(data) {
  if (!data) return;
  if (Array.isArray(data.rest_counts)) {
    data.rest_counts.forEach((count, idx) => {
      if (typeof count === "number" && count >= 1) restCounts.set(idx, count);
    });
    return;
  }
  const overrides = data.overrides || data.rest_overrides || [];
  overrides.forEach((item) => {
    const idx = item.measure_index ?? item.measure;
    const count = item.rest_count ?? item.count ?? item.skip;
    if (typeof idx === "number" && typeof count === "number" && count >= 1) {
      restCounts.set(idx, count);
    }
  });
}

function loadPage() {
  currentPage = pages[currentIndex];
  pageMeta.textContent = currentPage.name;
  saveStatus.textContent = "";
  setDirty(false);
  selectedIndex = null;
  measures = [];
  restCounts = new Map();

  image.onload = () => {
    resetView();
    draw();
  };
  image.src = `/file?path=${encodeURIComponent(currentPage.image)}`;

  fetchJSON(`/api/template?path=${encodeURIComponent(currentPage.numbering)}`)
    .then((data) => {
      const pageData = (data.pages && data.pages[0]) || data;
      const systems = pageData.systems || [];
      const all = [];
      systems.forEach((system) => {
        (system.measures || []).forEach((m) => {
          if (m.bbox) {
            all.push({ bbox: m.bbox, number: m.number });
          }
        });
      });
      measures = all;
      return loadRestGT(currentPage.rest_gt);
    })
    .then((restData) => {
      applyRestGT(restData);
      updateSelectedMeta();
      renderMeasureList();
      draw();
    });
}

function collectOverrides() {
  const overrides = [];
  measures.forEach((_, idx) => {
    const count = restCounts.get(idx) || 1;
    if (count > 1) {
      overrides.push({ measure_index: idx, rest_count: count });
    }
  });
  return overrides;
}

function save() {
  if (!currentPage) return;
  const payload = {
    page: currentPage.name,
    overrides: collectOverrides(),
  };
  return fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(() => {
    saveStatus.textContent = "Saved";
    setDirty(false);
  });
}

applyBtn.onclick = () => {
  if (selectedIndex === null) return;
  const nextValue = parseInt(restCountInput.value, 10);
  if (!Number.isFinite(nextValue) || nextValue < 1) return;
  restCounts.set(selectedIndex, nextValue);
  setDirty(true);
  updateSelectedMeta();
  renderMeasureList();
  draw();
};

resetBtn.onclick = () => {
  if (selectedIndex === null) return;
  restCounts.set(selectedIndex, 1);
  restCountInput.value = 1;
  setDirty(true);
  updateSelectedMeta();
  renderMeasureList();
  draw();
};

saveBtn.onclick = save;

prevBtn.onclick = () => {
  const nextIndex = Math.max(0, currentIndex - 1);
  if (nextIndex === currentIndex) return;
  if (!dirty) {
    currentIndex = nextIndex;
    loadPage();
    return;
  }
  save().then(() => {
    currentIndex = nextIndex;
    loadPage();
  });
};

nextBtn.onclick = () => {
  const nextIndex = Math.min(pages.length - 1, currentIndex + 1);
  if (nextIndex === currentIndex) return;
  if (!dirty) {
    currentIndex = nextIndex;
    loadPage();
    return;
  }
  save().then(() => {
    currentIndex = nextIndex;
    loadPage();
  });
};

canvas.addEventListener("mousedown", (e) => {
  const rect = canvas.getBoundingClientRect();
  const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  if (e.button === 1 || spaceDown) {
    isPanning = true;
    panStart = pt;
    panOrigin = { ...viewOffset };
    return;
  }
  const imgPt = canvasToImg(pt);
  selectedIndex = null;
  for (let i = measures.length - 1; i >= 0; i--) {
    if (pointInBox(imgPt, measures[i].bbox)) {
      selectedIndex = i;
      break;
    }
  }
  const count = selectedIndex !== null ? restCounts.get(selectedIndex) || 1 : 1;
  restCountInput.value = count;
  updateSelectedMeta();
  renderMeasureList();
  draw();
});

canvas.addEventListener("mousemove", (e) => {
  if (!isPanning) return;
  const rect = canvas.getBoundingClientRect();
  const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  viewOffset = {
    x: panOrigin.x + (pt.x - panStart.x),
    y: panOrigin.y + (pt.y - panStart.y),
  };
  draw();
});

canvas.addEventListener("mouseup", () => {
  isPanning = false;
});

canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  const zoom = Math.exp(-e.deltaY * 0.001);
  const imgPt = canvasToImg(pt);
  viewScale = Math.min(5.0, Math.max(0.1, viewScale * zoom));
  viewOffset.x = pt.x - imgPt.x * viewScale;
  viewOffset.y = pt.y - imgPt.y * viewScale;
  draw();
}, { passive: false });

window.addEventListener("keydown", (e) => {
  const tag = e.target && e.target.tagName ? e.target.tagName.toLowerCase() : "";
  if (tag === "input" || tag === "select" || tag === "textarea") {
    return;
  }
  if (e.key === " ") spaceDown = true;
  if (e.key === "ArrowLeft") prevBtn.click();
  if (e.key === "ArrowRight") nextBtn.click();
});

window.addEventListener("keyup", (e) => {
  if (e.key === " ") spaceDown = false;
});

window.addEventListener("resize", () => {
  if (!image.complete) return;
  resetView();
  draw();
});

fetchJSON("/api/pages").then((data) => {
  pages = data.pages || [];
  if (!pages.length) {
    pageMeta.textContent = "No pages configured.";
    return;
  }
  loadPage();
});
