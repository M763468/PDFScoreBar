let pages = [];
let currentIndex = 0;
let currentPage = null;

let measures = [];
let barlines = [];
let correctionsByType = {
  mmr_measure_span: [],
  barline_construction: [],
  measure_construction: [],
};

let selectedMeasure = null;
let selectedBarline = null;
let selectedItemIndex = null;
let draftBBox = null;
let mode = "select";
let dirtyTypes = new Set();

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

const pageList = document.getElementById("pageList");
const itemList = document.getElementById("itemList");
const pageMeta = document.getElementById("pageMeta");
const saveStatus = document.getElementById("saveStatus");
const dirtyStatus = document.getElementById("dirtyStatus");
const selectionMeta = document.getElementById("selectionMeta");

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const saveBtn = document.getElementById("saveBtn");
const selectModeBtn = document.getElementById("selectModeBtn");
const drawModeBtn = document.getElementById("drawModeBtn");
const addItemBtn = document.getElementById("addItemBtn");
const deleteItemBtn = document.getElementById("deleteItemBtn");

const typeSelect = document.getElementById("typeSelect");
const opSelect = document.getElementById("opSelect");
const measureSpanRow = document.getElementById("measureSpanRow");
const measureSpanInput = document.getElementById("measureSpanInput");
const reasonInput = document.getElementById("reasonInput");

let image = new Image();
let viewScale = 1.0;
let viewOffset = { x: 0, y: 0 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let panOrigin = { x: 0, y: 0 };
let isDrawing = false;
let drawStart = null;
let spaceDown = false;

const COLOR_MEASURE = "#3aa3ff";
const COLOR_BARLINE = "#46c46b";
const COLOR_SELECTED = "#ff8a00";
const COLOR_DRAFT = "#ff3b30";
const HIT_PADDING = 7;

const OPS = {
  mmr_measure_span: [
    ["set_measure_span", "set_measure_span"],
    ["suppress", "suppress"],
  ],
  barline_construction: [
    ["add_barline", "add_barline"],
    ["remove_barline", "remove_barline"],
  ],
  measure_construction: [["force_measure", "force_measure"]],
};

function fetchJSON(url) {
  return fetch(url).then((response) => {
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
  });
}

function currentType() {
  return typeSelect.value;
}

function currentOp() {
  return opSelect.value;
}

function pageValue() {
  if (!currentPage) return currentIndex;
  if (currentPage.page !== undefined) return currentPage.page;
  if (currentPage.page_index !== undefined) return currentPage.page_index;
  return currentIndex;
}

function setDirty(correctionType, isDirty) {
  if (isDirty) {
    dirtyTypes.add(correctionType);
  } else {
    dirtyTypes.delete(correctionType);
  }
  dirtyStatus.textContent = dirtyTypes.size
    ? `Unsaved: ${Array.from(dirtyTypes).join(", ")}`
    : "";
}

function updateOps() {
  opSelect.innerHTML = "";
  OPS[currentType()].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    opSelect.appendChild(option);
  });
  updateControlState();
}

function updateControlState() {
  const type = currentType();
  const op = currentOp();
  measureSpanRow.style.display =
    type === "mmr_measure_span" && op === "set_measure_span" ? "flex" : "none";
  drawModeBtn.disabled = !(type === "barline_construction");
  if (drawModeBtn.disabled && mode === "draw") {
    setMode("select");
  }
  renderItems();
  updateSelectionMeta();
  draw();
}

function setMode(nextMode) {
  mode = nextMode;
  selectModeBtn.classList.toggle("active", mode === "select");
  drawModeBtn.classList.toggle("active", mode === "draw");
  canvas.style.cursor = mode === "draw" ? "crosshair" : "default";
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

function drawBox(box, color, thickness, fill = false) {
  const [x1, y1, x2, y2] = box;
  const p1 = imgToCanvas({ x: x1, y: y1 });
  const p2 = imgToCanvas({ x: x2, y: y2 });
  ctx.strokeStyle = color;
  ctx.lineWidth = thickness;
  ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
  if (fill) {
    ctx.fillStyle = "rgba(255, 138, 0, 0.15)";
    ctx.fillRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
  }
}

function drawLabel(box, text, color) {
  const [x1, y1] = box;
  const p = imgToCanvas({ x: x1, y: y1 });
  ctx.font = "11px Arial";
  const textWidth = ctx.measureText(text).width;
  ctx.fillStyle = "rgba(0,0,0,0.65)";
  ctx.fillRect(p.x, p.y - 14, textWidth + 6, 14);
  ctx.fillStyle = color;
  ctx.fillText(text, p.x + 3, p.y - 3);
}

function draw() {
  if (!image.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const drawWidth = image.width * viewScale;
  const drawHeight = image.height * viewScale;
  ctx.drawImage(image, viewOffset.x, viewOffset.y, drawWidth, drawHeight);

  measures.forEach((measure) => {
    drawBox(measure.bbox, COLOR_MEASURE, 1.5);
    drawLabel(measure.bbox, `S${measure.system} M${measure.measure}`, COLOR_MEASURE);
  });

  barlines.forEach((barline, index) => {
    drawBox(barline.bbox, COLOR_BARLINE, 1.2);
    drawLabel(barline.bbox, `B${index + 1}`, COLOR_BARLINE);
  });

  if (selectedMeasure) {
    drawBox(selectedMeasure.bbox, COLOR_SELECTED, 3, true);
  }
  if (selectedBarline) {
    drawBox(selectedBarline.bbox, COLOR_SELECTED, 3, true);
  }
  if (draftBBox) {
    drawBox(draftBBox, COLOR_DRAFT, 2);
    drawLabel(draftBBox, "draft", COLOR_DRAFT);
  }
  if (isDrawing && drawStart) {
    ctx.strokeStyle = COLOR_DRAFT;
    ctx.lineWidth = 2;
    ctx.strokeRect(drawStart.x, drawStart.y, drawStart.w, drawStart.h);
  }
}

function pointInImageBox(imgPt, box) {
  const [x1, y1, x2, y2] = box;
  const minX = Math.min(x1, x2) - HIT_PADDING / viewScale;
  const maxX = Math.max(x1, x2) + HIT_PADDING / viewScale;
  const minY = Math.min(y1, y2) - HIT_PADDING / viewScale;
  const maxY = Math.max(y1, y2) + HIT_PADDING / viewScale;
  return imgPt.x >= minX && imgPt.x <= maxX && imgPt.y >= minY && imgPt.y <= maxY;
}

function pickMeasure(imgPt) {
  for (let i = measures.length - 1; i >= 0; i--) {
    if (pointInImageBox(imgPt, measures[i].bbox)) {
      return measures[i];
    }
  }
  return null;
}

function pickBarline(imgPt) {
  for (let i = barlines.length - 1; i >= 0; i--) {
    if (pointInImageBox(imgPt, barlines[i].bbox)) {
      return barlines[i];
    }
  }
  return null;
}

function updateSelectionMeta() {
  const parts = [];
  if (selectedMeasure) {
    parts.push(
      `measure: page=${pageValue()} system=${selectedMeasure.system} measure=${selectedMeasure.measure}`
    );
  }
  if (selectedBarline) {
    parts.push(`barline bbox=[${selectedBarline.bbox.join(", ")}]`);
  }
  if (draftBBox) {
    parts.push(`draft bbox=[${draftBBox.join(", ")}]`);
  }
  selectionMeta.textContent = parts.length ? parts.join(" | ") : "No selection";
}

function renderPageList() {
  pageList.innerHTML = "";
  pages.forEach((page, index) => {
    const div = document.createElement("div");
    div.className = "list-item" + (index === currentIndex ? " active" : "");
    div.textContent = page.name || `page ${index}`;
    div.onclick = () => switchPage(index);
    pageList.appendChild(div);
  });
}

function itemsForCurrentPage(correctionType) {
  const page = pageValue();
  return (correctionsByType[correctionType] || []).filter(
    (item) => String(item.page) === String(page)
  );
}

function replaceItemsForCurrentPage(correctionType, pageItems) {
  const page = pageValue();
  const kept = (correctionsByType[correctionType] || []).filter(
    (item) => String(item.page) !== String(page)
  );
  correctionsByType[correctionType] = kept.concat(pageItems);
}

function renderItems() {
  const type = currentType();
  const items = itemsForCurrentPage(type);
  itemList.innerHTML = "";
  items.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "list-item" + (index === selectedItemIndex ? " active" : "");
    div.textContent = `${index + 1}. ${item.op} ${JSON.stringify(item)}`;
    div.onclick = () => {
      selectedItemIndex = index;
      renderItems();
    };
    itemList.appendChild(div);
  });
  if (!items.length) {
    const div = document.createElement("div");
    div.className = "small";
    div.textContent = "No items for this page/type.";
    itemList.appendChild(div);
  }
}

function currentReason() {
  return reasonInput.value.trim() || "manual correction";
}

function addCorrectionItem() {
  const type = currentType();
  const op = currentOp();
  const page = pageValue();
  let item = null;

  if (type === "mmr_measure_span") {
    if (!selectedMeasure) {
      saveStatus.textContent = "Select a measure first.";
      return;
    }
    item = {
      op,
      page,
      system: selectedMeasure.system,
      measure: selectedMeasure.measure,
      reason: currentReason(),
    };
    if (op === "set_measure_span") {
      const span = parseInt(measureSpanInput.value, 10);
      if (!Number.isFinite(span) || span < 1) {
        saveStatus.textContent = "measure_span must be >= 1.";
        return;
      }
      item.measure_span = span;
    }
  }

  if (type === "barline_construction") {
    const bbox = op === "remove_barline" && selectedBarline ? selectedBarline.bbox : draftBBox;
    if (!bbox) {
      saveStatus.textContent = "Select a barline or draw a bbox first.";
      return;
    }
    item = {
      op,
      page,
      bbox: bbox.map((value) => Math.round(value)),
      reason: currentReason(),
    };
  }

  if (type === "measure_construction") {
    if (!selectedMeasure) {
      saveStatus.textContent = "Select a measure interval first.";
      return;
    }
    item = {
      op: "force_measure",
      page,
      system: selectedMeasure.system,
      interval: selectedMeasure.measure,
      reason: currentReason(),
    };
  }

  if (!item) return;
  const pageItems = itemsForCurrentPage(type);
  pageItems.push(item);
  replaceItemsForCurrentPage(type, pageItems);
  setDirty(type, true);
  selectedItemIndex = pageItems.length - 1;
  renderItems();
  saveStatus.textContent = `Added ${item.op}.`;
}

function deleteSelectedItem() {
  const type = currentType();
  const pageItems = itemsForCurrentPage(type);
  if (selectedItemIndex === null || !pageItems[selectedItemIndex]) {
    return;
  }
  pageItems.splice(selectedItemIndex, 1);
  selectedItemIndex = null;
  replaceItemsForCurrentPage(type, pageItems);
  setDirty(type, true);
  renderItems();
}

function loadCorrections() {
  const types = Object.keys(correctionsByType);
  return Promise.all(
    types.map((type) =>
      fetchJSON(`/api/manual_corrections?type=${encodeURIComponent(type)}`)
        .then((data) => {
          correctionsByType[type] = Array.isArray(data.items) ? data.items : [];
        })
        .catch(() => {
          correctionsByType[type] = [];
        })
    )
  );
}

function loadNumbering(path) {
  measures = [];
  if (!path) return Promise.resolve();
  return fetchJSON(`/api/template?path=${encodeURIComponent(path)}`).then((data) => {
    const pageData = (data.pages && data.pages[0]) || data;
    const systems = pageData.systems || [];
    systems.forEach((system, systemIndex) => {
      (system.measures || []).forEach((measure, measureIndex) => {
        if (!measure.bbox) return;
        measures.push({
          bbox: measure.bbox.map((value) => Math.round(value)),
          number: measure.number,
          system: system.index ?? system.system ?? systemIndex,
          measure: measure.index ?? measure.measure ?? measureIndex,
        });
      });
    });
  });
}

function barlinePathFromPage(page) {
  return page.barlines || page.barline_candidates || page.detected_barlines || null;
}

function loadBarlines(path) {
  barlines = [];
  if (!path) return Promise.resolve();
  return fetchJSON(`/api/boxes?path=${encodeURIComponent(path)}`)
    .then((data) => {
      barlines = (data.boxes || [])
        .map((item) => item.bbox || item.barline_location || item)
        .filter((box) => Array.isArray(box) && box.length === 4)
        .map((box) => ({ bbox: box.map((value) => Math.round(value)) }));
    })
    .catch(() => {
      barlines = [];
    });
}

function loadPage() {
  currentPage = pages[currentIndex];
  selectedMeasure = null;
  selectedBarline = null;
  selectedItemIndex = null;
  draftBBox = null;
  saveStatus.textContent = "";
  pageMeta.textContent = `${currentPage.name || currentIndex} | page=${pageValue()}`;

  image.onload = () => {
    resetView();
    draw();
  };
  image.src = `/file?path=${encodeURIComponent(currentPage.image)}`;

  Promise.all([
    loadNumbering(currentPage.numbering),
    loadBarlines(barlinePathFromPage(currentPage)),
    loadCorrections(),
  ]).then(() => {
    updateSelectionMeta();
    renderItems();
    renderPageList();
    draw();
  });
}

function saveCurrentType() {
  if (!currentPage) return Promise.resolve();
  const type = currentType();
  const payload = {
    page: pageValue(),
    correction_type: type,
    items: itemsForCurrentPage(type),
  };
  return fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return response.json();
    })
    .then((data) => {
      setDirty(type, false);
      saveStatus.textContent = `Saved ${type}: ${data.output}`;
    })
    .catch((error) => {
      saveStatus.textContent = `Save failed: ${error.message}`;
    });
}

function switchPage(nextIndex) {
  if (nextIndex === currentIndex) return;
  const savePromises = Array.from(dirtyTypes).map((type) => {
    typeSelect.value = type;
    updateOps();
    return saveCurrentType();
  });
  Promise.all(savePromises).then(() => {
    currentIndex = nextIndex;
    loadPage();
  });
}

selectModeBtn.onclick = () => setMode("select");
drawModeBtn.onclick = () => setMode("draw");
addItemBtn.onclick = addCorrectionItem;
deleteItemBtn.onclick = deleteSelectedItem;
saveBtn.onclick = saveCurrentType;

typeSelect.onchange = () => {
  selectedItemIndex = null;
  updateOps();
};
opSelect.onchange = updateControlState;

prevBtn.onclick = () => switchPage(Math.max(0, currentIndex - 1));
nextBtn.onclick = () => switchPage(Math.min(pages.length - 1, currentIndex + 1));

canvas.addEventListener("mousedown", (event) => {
  const rect = canvas.getBoundingClientRect();
  const pt = { x: event.clientX - rect.left, y: event.clientY - rect.top };

  if (event.button === 1 || spaceDown) {
    isPanning = true;
    panStart = pt;
    panOrigin = { ...viewOffset };
    return;
  }

  if (mode === "draw" && currentType() === "barline_construction") {
    isDrawing = true;
    drawStart = { x: pt.x, y: pt.y, w: 0, h: 0 };
    return;
  }

  const imgPt = canvasToImg(pt);
  selectedMeasure = pickMeasure(imgPt);
  selectedBarline = pickBarline(imgPt);
  updateSelectionMeta();
  draw();
});

canvas.addEventListener("mousemove", (event) => {
  const rect = canvas.getBoundingClientRect();
  const pt = { x: event.clientX - rect.left, y: event.clientY - rect.top };

  if (isPanning) {
    viewOffset = {
      x: panOrigin.x + (pt.x - panStart.x),
      y: panOrigin.y + (pt.y - panStart.y),
    };
    draw();
    return;
  }

  if (isDrawing && drawStart) {
    drawStart.w = pt.x - drawStart.x;
    drawStart.h = pt.y - drawStart.y;
    draw();
  }
});

canvas.addEventListener("mouseup", (event) => {
  if (isDrawing && drawStart) {
    const rect = canvas.getBoundingClientRect();
    const end = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    const startImg = canvasToImg({ x: drawStart.x, y: drawStart.y });
    const endImg = canvasToImg(end);
    draftBBox = normalizeBox([startImg.x, startImg.y, endImg.x, endImg.y]);
    isDrawing = false;
    drawStart = null;
    updateSelectionMeta();
    draw();
    return;
  }
  isPanning = false;
});

canvas.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const pt = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    const zoom = Math.exp(-event.deltaY * 0.001);
    const imgPt = canvasToImg(pt);
    viewScale = Math.min(5.0, Math.max(0.1, viewScale * zoom));
    viewOffset.x = pt.x - imgPt.x * viewScale;
    viewOffset.y = pt.y - imgPt.y * viewScale;
    draw();
  },
  { passive: false }
);

window.addEventListener("keydown", (event) => {
  const tag = event.target && event.target.tagName ? event.target.tagName.toLowerCase() : "";
  if (tag === "input" || tag === "select" || tag === "textarea") {
    return;
  }
  if (event.key === " ") spaceDown = true;
  if (event.key === "ArrowLeft") prevBtn.click();
  if (event.key === "ArrowRight") nextBtn.click();
  if (event.key === "Delete" || event.key === "Backspace") deleteSelectedItem();
});

window.addEventListener("keyup", (event) => {
  if (event.key === " ") spaceDown = false;
});

window.addEventListener("resize", () => {
  if (!image.complete) return;
  resetView();
  draw();
});

updateOps();

fetchJSON("/api/pages").then((data) => {
  pages = data.pages || [];
  if (!pages.length) {
    pageMeta.textContent = "No pages configured.";
    return;
  }
  loadPage();
});
