let pages = [];
let currentIndex = 0;
let currentPage = null;
let editableBoxes = [];
let referenceLayers = [];
let editableSources = [];
let selectedIndex = null;
let mode = "select";
let currentType = "barline";

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const pageList = document.getElementById("pageList");
const pageMeta = document.getElementById("pageMeta");
const saveStatus = document.getElementById("saveStatus");
const dirtyStatus = document.getElementById("dirtyStatus");
const stats = document.getElementById("stats");
const layerList = document.getElementById("layerList");
const legend = document.getElementById("legend");

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const saveBtn = document.getElementById("saveBtn");
const modeSelectBtn = document.getElementById("modeSelectBtn");
const modeDrawBtn = document.getElementById("modeDrawBtn");
const deleteBtn = document.getElementById("deleteBtn");
const dedupBtn = document.getElementById("dedupBtn");
const typeSelect = document.getElementById("typeSelect");

let image = new Image();
let viewScale = 1.0;
let viewOffset = { x: 0, y: 0 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let panOrigin = { x: 0, y: 0 };
let isDrawing = false;
let drawStart = null;
let dragMode = null;
let dragHandle = null;
let dragOffset = { x: 0, y: 0 };
let spaceDown = false;
let dirty = false;

const HANDLE_SIZE = 8;
const HIT_PADDING = 6;
const EDITABLE_COLOR = "#00c2d1";
const SELECTED_COLOR = "#ff8a00";
const DRAW_COLOR = "#ff3b30";
const DEDUP_X_TOL = 3;
const DEDUP_Y_OVERLAP = 0.7;

function fetchJSON(url) {
  return fetch(url).then((r) => r.json());
}

function setMode(nextMode) {
  mode = nextMode;
  modeSelectBtn.classList.toggle("active", mode === "select");
  modeDrawBtn.classList.toggle("active", mode === "draw");
  canvas.style.cursor = mode === "draw" ? "crosshair" : "default";
}

function renderPageList() {
  pageList.innerHTML = "";
  pages.forEach((page, idx) => {
    const div = document.createElement("div");
    div.className = "list-item" + (idx === currentIndex ? " active" : "");
    div.textContent = page.name;
    div.onclick = () => {
      saveThenSwitch(idx);
    };
    pageList.appendChild(div);
  });
}

function renderLayers() {
  layerList.innerHTML = "";
  legend.innerHTML = "";

  const editableEntry = document.createElement("label");
  editableEntry.className = "small";
  editableEntry.innerHTML = `<input type="checkbox" id="showEditable" checked /> All editable`;
  layerList.appendChild(editableEntry);

  editableSources.forEach((source, idx) => {
    const label = document.createElement("label");
    label.className = "small";
    label.innerHTML = `<input type="checkbox" data-editable="${idx}" ${source.visible ? "checked" : ""} /> ${source.label}`;
    layerList.appendChild(label);

    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = source.color;
    legend.appendChild(makeLegend(source.label, dot));
  });

  referenceLayers.forEach((layer, idx) => {
    const label = document.createElement("label");
    label.className = "small";
    label.innerHTML = `<input type="checkbox" data-layer="${idx}" ${layer.visible ? "checked" : ""} /> ${layer.label}`;
    layerList.appendChild(label);

    const dotRef = document.createElement("span");
    dotRef.className = "dot";
    dotRef.style.background = layer.color;
    legend.appendChild(makeLegend(layer.label, dotRef));
  });

  const selectedDot = document.createElement("span");
  selectedDot.className = "dot";
  selectedDot.style.background = SELECTED_COLOR;
  legend.appendChild(makeLegend("Selected", selectedDot));

  const drawDot = document.createElement("span");
  drawDot.className = "dot";
  drawDot.style.background = DRAW_COLOR;
  legend.appendChild(makeLegend("Draw preview", drawDot));

  layerList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.onchange = (e) => {
      if (cb.id === "showEditable") {
        draw();
        return;
      }
      if (cb.dataset.editable) {
        const idx = parseInt(e.target.dataset.editable, 10);
        editableSources[idx].visible = e.target.checked;
        draw();
        return;
      }
      const idx = parseInt(e.target.dataset.layer, 10);
      referenceLayers[idx].visible = e.target.checked;
      draw();
    };
  });
}

function makeLegend(label, dotEl) {
  const span = document.createElement("span");
  span.appendChild(dotEl);
  const text = document.createElement("span");
  text.textContent = label;
  span.appendChild(text);
  return span;
}

function loadPage() {
  currentPage = pages[currentIndex];
  selectedIndex = null;
  saveStatus.textContent = "";
  dirty = false;
  updateDirtyStatus();
  pageMeta.textContent = `${currentPage.name}`;

  image.onload = () => {
    resetView();
    draw();
  };
  image.src = `/file?path=${encodeURIComponent(currentPage.image)}`;

  const sources = (currentPage.editable_sources && currentPage.editable_sources.length)
    ? currentPage.editable_sources
    : [{ label: "base", path: currentPage.editable, color: EDITABLE_COLOR }];
  editableSources = sources.map((src) => ({ ...src, visible: true }));
  if (!editableSources.find((src) => src.label === "manual")) {
    editableSources.push({ label: "manual", path: null, color: DRAW_COLOR, visible: true });
  }
  editableBoxes = [];
  Promise.all(
    editableSources
      .filter((source) => source.path)
      .map((source) =>
        fetchJSON(`/api/boxes?path=${encodeURIComponent(source.path)}`).then((data) => {
          const items = (data.boxes || []).map((b) => normalizeEditable(b));
          items.forEach((item) => {
            item.source = source.label;
            item.color = source.color;
          });
          editableBoxes = editableBoxes.concat(items);
        })
      )
  ).then(() => {
    updateStats();
    syncTypeSelect();
    renderLayers();
    draw();
  });

  referenceLayers = [];
  const refs = currentPage.references || [];
  refs.forEach((ref) => {
    fetchJSON(`/api/boxes?path=${encodeURIComponent(ref.path)}`).then((data) => {
      referenceLayers.push({
        label: ref.label,
        color: ref.color,
        boxes: (data.boxes || []).map((b) => extractBox(b)).filter(Boolean),
        visible: true,
      });
      renderLayers();
      draw();
    });
  });
  renderLayers();
  renderPageList();
}

function extractBox(item) {
  if (Array.isArray(item)) return item;
  if (item && Array.isArray(item.bbox)) return item.bbox;
  if (item && Array.isArray(item.barline_location)) return item.barline_location;
  return null;
}

function normalizeEditable(item) {
  if (Array.isArray(item)) {
    return { bbox: item, type: "barline", source: "base", color: EDITABLE_COLOR };
  }
  if (item && Array.isArray(item.bbox)) {
    return { bbox: item.bbox, type: item.barline_type || item.type || "barline", source: "base", color: EDITABLE_COLOR };
  }
  if (item && Array.isArray(item.barline_location)) {
    return { bbox: item.barline_location, type: item.barline_type || item.type || "barline", source: "base", color: EDITABLE_COLOR };
  }
  return { bbox: [0, 0, 0, 0], type: "barline", source: "base", color: EDITABLE_COLOR };
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

function drawBoxes(boxes, color, thickness, highlightSelected) {
  const baseColor = color;
  ctx.lineWidth = thickness;
  boxes.forEach((b, idx) => {
    ctx.strokeStyle = baseColor;
    const box = Array.isArray(b) ? b : b.bbox;
    if (!box) return;
    const [x1, y1, x2, y2] = box;
    const p1 = imgToCanvas({ x: x1, y: y1 });
    const p2 = imgToCanvas({ x: x2, y: y2 });
    ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
    if (highlightSelected && idx === selectedIndex) {
      drawSelectedBox(p1, p2, box);
      ctx.lineWidth = thickness;
    }
  });
}

function drawHandles(p1, p2, color) {
  ctx.fillStyle = color;
  const handles = [
    [p1.x, p1.y],
    [p2.x, p1.y],
    [p2.x, p2.y],
    [p1.x, p2.y],
  ];
  handles.forEach(([hx, hy]) => {
    ctx.fillRect(hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
  });
}

function drawSelectedBox(p1, p2, box) {
  ctx.strokeStyle = SELECTED_COLOR;
  ctx.lineWidth = 3;
  ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
  ctx.fillStyle = "rgba(255, 138, 0, 0.15)";
  ctx.fillRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
  drawHandles(p1, p2, SELECTED_COLOR);
  drawTypeLabel(p1, box);
}

function drawTypeLabel(p1, box) {
  if (!box || selectedIndex === null) return;
  const label = editableBoxes[selectedIndex]?.type || "barline";
  const source = editableBoxes[selectedIndex]?.source || "base";
  const text = `${label} (${source})`;
  ctx.font = "12px Arial";
  const textWidth = ctx.measureText(text).width;
  ctx.fillStyle = "rgba(0, 0, 0, 0.65)";
  ctx.fillRect(p1.x + 4, p1.y - 18, textWidth + 8, 16);
  ctx.fillStyle = "#fff";
  ctx.fillText(text, p1.x + 8, p1.y - 6);
}

function draw() {
  if (!image.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const drawWidth = image.width * viewScale;
  const drawHeight = image.height * viewScale;
  ctx.drawImage(image, viewOffset.x, viewOffset.y, drawWidth, drawHeight);

  const showEditable = document.getElementById("showEditable");
  if (showEditable && showEditable.checked) {
    editableBoxes.forEach((box) => {
      const source = editableSources.find((s) => s.label === box.source);
      if (source && !source.visible) return;
      drawBoxes([box], box.color || EDITABLE_COLOR, 2, false);
    });
  }
  referenceLayers.forEach((layer) => {
    if (!layer.visible) return;
    drawBoxes(layer.boxes, layer.color, 1, false);
  });
  if (showEditable && showEditable.checked && selectedIndex !== null && editableBoxes[selectedIndex]) {
    const box = editableBoxes[selectedIndex].bbox;
    const p1 = imgToCanvas({ x: box[0], y: box[1] });
    const p2 = imgToCanvas({ x: box[2], y: box[3] });
    drawSelectedBox(p1, p2, box);
  }

  if (isDrawing && drawStart) {
    ctx.strokeStyle = DRAW_COLOR;
    ctx.lineWidth = 2;
    ctx.strokeRect(drawStart.x, drawStart.y, drawStart.w, drawStart.h);
  }
}

function normalizeBox(box) {
  let [x1, y1, x2, y2] = box;
  if (x2 < x1) [x1, x2] = [x2, x1];
  if (y2 < y1) [y1, y2] = [y2, y1];
  const maxX = image.complete ? image.width : Number.MAX_SAFE_INTEGER;
  const maxY = image.complete ? image.height : Number.MAX_SAFE_INTEGER;
  return [
    Math.max(0, Math.min(maxX, Math.round(x1))),
    Math.max(0, Math.min(maxY, Math.round(y1))),
    Math.max(0, Math.min(maxX, Math.round(x2))),
    Math.max(0, Math.min(maxY, Math.round(y2))),
  ];
}

function hitHandle(pt, box) {
  const [x1, y1, x2, y2] = box;
  const p1 = imgToCanvas({ x: x1, y: y1 });
  const p2 = imgToCanvas({ x: x2, y: y2 });
  const handles = [
    [p1.x, p1.y],
    [p2.x, p1.y],
    [p2.x, p2.y],
    [p1.x, p2.y],
  ];
  for (let i = 0; i < handles.length; i++) {
    const [hx, hy] = handles[i];
    if (Math.abs(pt.x - hx) <= HANDLE_SIZE && Math.abs(pt.y - hy) <= HANDLE_SIZE) {
      return i;
    }
  }
  return null;
}

function pointInBox(pt, box) {
  const [x1, y1, x2, y2] = box;
  const p1 = imgToCanvas({ x: x1, y: y1 });
  const p2 = imgToCanvas({ x: x2, y: y2 });
  const minX = Math.min(p1.x, p2.x) - HIT_PADDING;
  const maxX = Math.max(p1.x, p2.x) + HIT_PADDING;
  const minY = Math.min(p1.y, p2.y) - HIT_PADDING;
  const maxY = Math.max(p1.y, p2.y) + HIT_PADDING;
  return pt.x >= minX && pt.x <= maxX && pt.y >= minY && pt.y <= maxY;
}

canvas.addEventListener("mousedown", (e) => {
  const rect = canvas.getBoundingClientRect();
  const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };

  if (e.button === 1 || spaceDown) {
    isPanning = true;
    panStart = pt;
    panOrigin = { ...viewOffset };
    return;
  }

  if (mode === "draw") {
    isDrawing = true;
    drawStart = { x: pt.x, y: pt.y, w: 0, h: 0 };
    return;
  }

  if (selectedIndex !== null && editableBoxes[selectedIndex]) {
    const handle = hitHandle(pt, editableBoxes[selectedIndex].bbox);
    if (handle !== null) {
      dragMode = "resize";
      dragHandle = handle;
      return;
    }
    if (pointInBox(pt, editableBoxes[selectedIndex].bbox)) {
      dragMode = "move";
      const [x1, y1] = imgToCanvas({ x: editableBoxes[selectedIndex].bbox[0], y: editableBoxes[selectedIndex].bbox[1] });
      dragOffset = { x: pt.x - x1, y: pt.y - y1 };
      return;
    }
  }

  selectedIndex = null;
  for (let i = editableBoxes.length - 1; i >= 0; i--) {
    if (pointInBox(pt, editableBoxes[i].bbox)) {
      selectedIndex = i;
      break;
    }
  }
  syncTypeSelect();
  draw();
});

canvas.addEventListener("mousemove", (e) => {
  const rect = canvas.getBoundingClientRect();
  const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };

  if (isPanning) {
    viewOffset = {
      x: panOrigin.x + (pt.x - panStart.x),
      y: panOrigin.y + (pt.y - panStart.y),
    };
    draw();
    return;
  }

  if (mode === "draw" && isDrawing && drawStart) {
    drawStart.w = pt.x - drawStart.x;
    drawStart.h = pt.y - drawStart.y;
    draw();
    return;
  }

  if (dragMode && selectedIndex !== null) {
    const imgPt = canvasToImg(pt);
    let [x1, y1, x2, y2] = editableBoxes[selectedIndex].bbox;
    if (dragMode === "move") {
      const width = x2 - x1;
      const height = y2 - y1;
      const origin = canvasToImg({ x: pt.x - dragOffset.x, y: pt.y - dragOffset.y });
      editableBoxes[selectedIndex].bbox = [origin.x, origin.y, origin.x + width, origin.y + height];
    } else if (dragMode === "resize") {
      if (dragHandle === 0) {
        x1 = imgPt.x; y1 = imgPt.y;
      } else if (dragHandle === 1) {
        x2 = imgPt.x; y1 = imgPt.y;
      } else if (dragHandle === 2) {
        x2 = imgPt.x; y2 = imgPt.y;
      } else if (dragHandle === 3) {
        x1 = imgPt.x; y2 = imgPt.y;
      }
      editableBoxes[selectedIndex].bbox = [x1, y1, x2, y2];
    }
    editableBoxes[selectedIndex].bbox = normalizeBox(editableBoxes[selectedIndex].bbox);
    setDirty(true);
    draw();
  }
});

canvas.addEventListener("mouseup", (e) => {
  if (isPanning) {
    isPanning = false;
    return;
  }
  if (mode === "draw" && isDrawing && drawStart) {
    const end = { x: drawStart.x + drawStart.w, y: drawStart.y + drawStart.h };
    const imgStart = canvasToImg({ x: drawStart.x, y: drawStart.y });
    const imgEnd = canvasToImg(end);
    const newBox = normalizeBox([imgStart.x, imgStart.y, imgEnd.x, imgEnd.y]);
    editableBoxes.push({ bbox: newBox, type: currentType, source: "manual", color: DRAW_COLOR });
    selectedIndex = editableBoxes.length - 1;
    updateStats();
    isDrawing = false;
    drawStart = null;
    syncTypeSelect();
    setDirty(true);
    draw();
  }
  dragMode = null;
  dragHandle = null;
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

window.addEventListener("resize", () => {
  if (!image.complete) return;
  resetView();
  draw();
});

window.addEventListener("keydown", (e) => {
  if (e.key === " ") spaceDown = true;
  if (e.key === "ArrowLeft") prevBtn.click();
  if (e.key === "ArrowRight") nextBtn.click();
  if (e.key.toLowerCase() === "n") setMode("draw");
  if (e.key.toLowerCase() === "v") setMode("select");
  if (e.key === "Delete" || e.key === "Backspace") deleteSelected();
  if (e.key.toLowerCase() === "s") save();
});

window.addEventListener("keyup", (e) => {
  if (e.key === " ") spaceDown = false;
});

function deleteSelected() {
  if (selectedIndex === null) return;
  editableBoxes.splice(selectedIndex, 1);
  selectedIndex = null;
  updateStats();
  syncTypeSelect();
  setDirty(true);
  draw();
}

function save() {
  if (!currentPage) return;
  return fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page: currentPage.name,
      boxes: editableBoxes.map((b) => ({ bbox: b.bbox, barline_type: b.type })),
    }),
  }).then(() => {
    saveStatus.textContent = "Saved";
    setDirty(false);
  });
}

prevBtn.onclick = () => {
  const nextIndex = Math.max(0, currentIndex - 1);
  saveThenSwitch(nextIndex);
};

nextBtn.onclick = () => {
  const nextIndex = Math.min(pages.length - 1, currentIndex + 1);
  saveThenSwitch(nextIndex);
};

saveBtn.onclick = save;
modeSelectBtn.onclick = () => setMode("select");
modeDrawBtn.onclick = () => setMode("draw");
deleteBtn.onclick = deleteSelected;
dedupBtn.onclick = () => runAutoDedup();
typeSelect.onchange = () => {
  if (selectedIndex !== null && editableBoxes[selectedIndex]) {
    editableBoxes[selectedIndex].type = typeSelect.value;
  } else {
    currentType = typeSelect.value;
  }
  setDirty(true);
  draw();
};

fetchJSON("/api/pages").then((data) => {
  pages = data.pages || [];
  if (!pages.length) {
    pageMeta.textContent = "No pages configured.";
    return;
  }
  renderPageList();
  loadPage();
});

function updateStats() {
  const counts = editableBoxes.reduce((acc, b) => {
    const label = b.source || "base";
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
  const summary = Object.entries(counts)
    .map(([k, v]) => `${k}:${v}`)
    .join(" ");
  stats.textContent = `Boxes: ${editableBoxes.length}${summary ? " (" + summary + ")" : ""}`;
}

function syncTypeSelect() {
  if (selectedIndex !== null && editableBoxes[selectedIndex]) {
    typeSelect.value = editableBoxes[selectedIndex].type || "barline";
  } else {
    typeSelect.value = currentType;
  }
}

function setDirty(next) {
  dirty = next;
  updateDirtyStatus();
}

function updateDirtyStatus() {
  dirtyStatus.textContent = dirty ? "Unsaved changes" : "";
}

function saveThenSwitch(nextIndex) {
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
}

function runAutoDedup() {
  if (!editableBoxes.length) return;
  const toRemove = new Set();
  const sorted = editableBoxes
    .map((b, idx) => ({ idx, box: b.bbox }))
    .sort((a, b) => ((a.box[0] + a.box[2]) / 2) - ((b.box[0] + b.box[2]) / 2));

  for (let i = 0; i < sorted.length; i++) {
    if (toRemove.has(sorted[i].idx)) continue;
    const [x1a, y1a, x2a, y2a] = sorted[i].box;
    const cxa = (x1a + x2a) / 2;
    const ha = Math.abs(y2a - y1a);
    for (let j = i + 1; j < sorted.length; j++) {
      if (toRemove.has(sorted[j].idx)) continue;
      const [x1b, y1b, x2b, y2b] = sorted[j].box;
      const cxb = (x1b + x2b) / 2;
      const dx = Math.abs(cxb - cxa);
      if (dx > DEDUP_X_TOL) break;
      const overlap = Math.max(0, Math.min(y2a, y2b) - Math.max(y1a, y1b));
      const minH = Math.max(1, Math.min(Math.abs(y2a - y1a), Math.abs(y2b - y1b)));
      const overlapRatio = overlap / minH;
      if (overlapRatio >= DEDUP_Y_OVERLAP) {
        const hb = Math.abs(y2b - y1b);
        const removeIdx = ha >= hb ? sorted[j].idx : sorted[i].idx;
        toRemove.add(removeIdx);
      }
    }
  }

  if (!toRemove.size) return;
  editableBoxes = editableBoxes.filter((_, idx) => !toRemove.has(idx));
  selectedIndex = null;
  updateStats();
  syncTypeSelect();
  setDirty(true);
  draw();
}
