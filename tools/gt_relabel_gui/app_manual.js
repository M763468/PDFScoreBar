let pages = [];
let currentIndex = 0;
let currentPage = null;

let measures = [];
let baseMmrOverrides = [];
let barlines = [];
let movementEvidenceCandidates = [];
let allMovementEvidenceCandidates = [];
let resolvedMovementBoundaries = [];
let selectedMovementSystem = null;
let correctionsByType = {
  mmr_measure_span: [],
  barline_construction: [],
  measure_construction: [],
  movement_boundary: [],
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
const exportMovementBtn = document.getElementById("exportMovementBtn");
const helpBtn = document.getElementById("helpBtn");
const helpPanel = document.getElementById("helpPanel");
const selectModeBtn = document.getElementById("selectModeBtn");
const drawModeBtn = document.getElementById("drawModeBtn");
const addItemBtn = document.getElementById("addItemBtn");
const deleteItemBtn = document.getElementById("deleteItemBtn");

const typeSelect = document.getElementById("typeSelect");
const opSelect = document.getElementById("opSelect");
const measureSpanRow = document.getElementById("measureSpanRow");
const measureSpanInput = document.getElementById("measureSpanInput");
const movementBoundaryPanel = document.getElementById("movementBoundaryPanel");
const movementSystemRow = document.getElementById("movementSystemRow");
const movementSystemInput = document.getElementById("movementSystemInput");
const movementTargetMeta = document.getElementById("movementTargetMeta");
const movementPageStatus = document.getElementById("movementPageStatus");
const reasonInput = document.getElementById("reasonInput");

const showMeasuresToggle = document.getElementById("showMeasuresToggle");
const showBarlinesToggle = document.getElementById("showBarlinesToggle");
const showLabelsToggle = document.getElementById("showLabelsToggle");
const showBaseToggle = document.getElementById("showBaseToggle");
const showManualToggle = document.getElementById("showManualToggle");
const showMovementToggle = document.getElementById("showMovementToggle");

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
const COLOR_BASE_MMR = "#46c46b";
const COLOR_MANUAL = "#b35cff";
const COLOR_SUPPRESSED = "#ff3b30";
const COLOR_BARLINE = "#46c46b";
const COLOR_SELECTED = "#ff8a00";
const COLOR_DRAFT = "#ff3b30";
const COLOR_MOVEMENT_CANDIDATE = "#ffd60a";
const COLOR_MOVEMENT_BOUNDARY = "#b35cff";
const COLOR_MOVEMENT_EXISTING = "#00c2ff";
const COLOR_MOVEMENT_REJECTED = "#9aa0a6";
const HIT_PADDING = 7;

const OPS = {
  mmr_measure_span: [
    ["set_measure_span", "Set measure span"],
    ["suppress", "Suppress MMR override"],
  ],
  barline_construction: [
    ["remove_barline", "Remove existing barline"],
    ["add_barline", "Add barline"],
  ],
  measure_construction: [["force_measure", "Force measure interval"]],
  movement_boundary: [
    ["boundary", "Set boundary BEFORE target system"],
    ["no_boundary", "Reject candidate (no boundary here)"],
  ],
};

function fetchJSON(url) {
  return fetch(url).then((response) => {
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
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

function displayIndex(value) {
  const numeric = parseInt(value, 10);
  return Number.isFinite(numeric) ? numeric + 1 : value;
}

function displayPageNumberFor(page, fallbackIndex) {
  if (page && page.source_page_number !== undefined) return page.source_page_number;
  if (page && page.page !== undefined) return displayIndex(page.page);
  if (page && page.page_index !== undefined) return displayIndex(page.page_index);
  return displayIndex(fallbackIndex);
}

function displayPageNumber() {
  return displayPageNumberFor(currentPage, currentIndex);
}

function measureDisplayLabel(measure) {
  return `S${displayIndex(measure.system)} M${displayIndex(measure.measure)}`;
}

function operationLabel(correctionType, op) {
  const match = (OPS[correctionType] || []).find(([value]) => value === op);
  return match ? match[1] : op;
}

function manualItemSummary(item, index, correctionType) {
  const parts = [
    `Staged ${index + 1}`,
    operationLabel(correctionType, item.op),
    `Page ${displayIndex(item.page)}`,
  ];
  if (item.system !== undefined) parts.push(`System ${displayIndex(item.system)}`);
  if (item.measure !== undefined) parts.push(`Measure ${displayIndex(item.measure)}`);
  if (item.interval !== undefined) parts.push(`Measure ${displayIndex(item.interval)}`);
  if (item.measure_span !== undefined) parts.push(`span ${item.measure_span}`);
  if (Array.isArray(item.bbox)) parts.push(`bbox=[${item.bbox.join(", ")}]`);
  return parts.join(" · ");
}

function measureKey(page, system, measure) {
  return `${page}:${system}:${measure}`;
}

function selectedMeasureKey() {
  if (!selectedMeasure) return null;
  return measureKey(pageValue(), selectedMeasure.system, selectedMeasure.measure);
}

function setDirty(correctionType, isDirty) {
  if (isDirty) dirtyTypes.add(correctionType);
  else dirtyTypes.delete(correctionType);
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
  selectedItemIndex = null;
  updateControlState();
}

function updateControlState() {
  const type = currentType();
  const op = currentOp();
  measureSpanRow.style.display =
    type === "mmr_measure_span" && op === "set_measure_span" ? "flex" : "none";
  movementBoundaryPanel.style.display = type === "movement_boundary" ? "" : "none";
  if (type === "movement_boundary" && selectedMeasure && selectedMovementSystem === null) {
    selectedMovementSystem = selectedMeasure.system;
    movementSystemInput.value = String(displayIndex(selectedMovementSystem));
  }
  if (type === "movement_boundary") {
    addItemBtn.textContent =
      op === "boundary" ? "Stage boundary before system" : "Stage candidate rejection";
  } else {
    addItemBtn.textContent = "Stage change";
  }
  drawModeBtn.disabled = !(type === "barline_construction");
  if (drawModeBtn.disabled && mode === "draw") setMode("select");
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
  return { x: pt.x * viewScale + viewOffset.x, y: pt.y * viewScale + viewOffset.y };
}

function canvasToImg(pt) {
  return { x: (pt.x - viewOffset.x) / viewScale, y: (pt.y - viewOffset.y) / viewScale };
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

function systemBounds(system) {
  const systemMeasures = measures.filter(
    (measure) => String(measure.system) === String(system)
  );
  if (!systemMeasures.length) return null;
  return systemMeasures.reduce(
    (bounds, measure) => [
      Math.min(bounds[0], measure.bbox[0]),
      Math.min(bounds[1], measure.bbox[1]),
      Math.max(bounds[2], measure.bbox[2]),
      Math.max(bounds[3], measure.bbox[3]),
    ],
    [
      systemMeasures[0].bbox[0],
      systemMeasures[0].bbox[1],
      systemMeasures[0].bbox[2],
      systemMeasures[0].bbox[3],
    ]
  );
}

function movementReviewAt(system) {
  return itemsForCurrentPage("movement_boundary").find(
    (item) => String(item.system) === String(system)
  );
}

function resolvedMovementAt(system) {
  return resolvedMovementBoundaries.find(
    (item) =>
      String(item.page) === String(pageValue()) &&
      String(item.system) === String(system)
  );
}

function movementStateAt(system) {
  const review = movementReviewAt(system);
  const candidate = movementCandidateAt(system);
  const resolved = resolvedMovementAt(system);
  if (review) {
    if (review.op === "boundary") {
      return {
        kind: candidate ? "reviewed_candidate_boundary" : "manual_boundary",
        label: candidate ? "Reviewed boundary" : "Manual boundary",
        color: COLOR_MOVEMENT_BOUNDARY,
        dashed: false,
      };
    }
    return {
      kind: "reviewed_no_boundary",
      label: "Reviewed: no boundary",
      color: COLOR_MOVEMENT_REJECTED,
      dashed: true,
    };
  }
  if (resolved) {
    return {
      kind: "existing_resolved_boundary",
      label: "Existing resolved boundary",
      color: COLOR_MOVEMENT_EXISTING,
      dashed: false,
    };
  }
  if (candidate) {
    return {
      kind: "unresolved_candidate",
      label: "Unresolved candidate",
      color: COLOR_MOVEMENT_CANDIDATE,
      dashed: true,
    };
  }
  return null;
}

function movementSystemsOnPage() {
  const systems = new Set();
  movementEvidenceCandidates.forEach((candidate) => {
    if (
      String(candidate.page) === String(pageValue()) &&
      candidate.state === "ambiguous_review_required"
    ) {
      systems.add(String(candidate.system));
    }
  });
  itemsForCurrentPage("movement_boundary").forEach((item) => systems.add(String(item.system)));
  resolvedMovementBoundaries.forEach((item) => {
    if (String(item.page) === String(pageValue())) systems.add(String(item.system));
  });
  return Array.from(systems)
    .map((value) => parseInt(value, 10))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
}

function drawMovementMarker(system, state, selected = false) {
  const bounds = systemBounds(system);
  if (!bounds) return;
  const [x1, y1, x2, y2] = bounds;
  const lineY = Math.max(2, y1 - 8);
  const p1 = imgToCanvas({ x: Math.max(0, x1 - 8), y: lineY });
  const p2 = imgToCanvas({ x: Math.min(image.width, x2 + 8), y: lineY });
  ctx.save();
  ctx.strokeStyle = selected ? COLOR_SELECTED : state.color;
  ctx.lineWidth = selected ? 4 : 3;
  ctx.setLineDash(state.dashed && !selected ? [8, 5] : []);
  ctx.beginPath();
  ctx.moveTo(p1.x, p1.y);
  ctx.lineTo(p2.x, p2.y);
  ctx.stroke();
  ctx.setLineDash([]);
  const labelBox = [x1, lineY, x2, y2];
  drawLabel(
    labelBox,
    `${selected ? "TARGET" : state.label}: before S${displayIndex(system)}`,
    selected ? COLOR_SELECTED : state.color
  );
  if (selected) drawBox(bounds, COLOR_SELECTED, 3, true);
  ctx.restore();
}

function updateMovementTargetMeta() {
  if (!movementTargetMeta || !movementPageStatus) return;
  if (currentType() !== "movement_boundary") return;

  const system = selectedMovementSystem;
  if (system === null || !Number.isFinite(system)) {
    movementTargetMeta.textContent =
      "No target system selected. Click anywhere inside the intended system or enter its system number.";
  } else {
    const bounds = systemBounds(system);
    const state = movementStateAt(system);
    const clicked =
      selectedMeasure && String(selectedMeasure.system) === String(system)
        ? ` Selected via Measure ${displayIndex(selectedMeasure.measure)}; that measure is only used to identify the system.`
        : "";
    const status = state ? ` Current state: ${state.label}.` : " Current state: no candidate or resolved boundary.";
    movementTargetMeta.textContent = bounds
      ? `Target: System ${displayIndex(system)}. A boundary will be placed BEFORE this system.${clicked}${status}`
      : `System ${displayIndex(system)} is not present on this page.`;
  }

  const systems = movementSystemsOnPage();
  const counts = {
    existing: 0,
    reviewed: 0,
    rejected: 0,
    candidates: 0,
  };
  systems.forEach((systemIndex) => {
    const state = movementStateAt(systemIndex);
    if (!state) return;
    if (state.kind === "existing_resolved_boundary") counts.existing += 1;
    else if (state.kind === "reviewed_no_boundary") counts.rejected += 1;
    else if (state.kind === "unresolved_candidate") counts.candidates += 1;
    else counts.reviewed += 1;
  });
  movementPageStatus.textContent =
    `This page: existing resolved boundaries ${counts.existing} · reviewed/staged boundaries ${counts.reviewed} · reviewed no-boundary ${counts.rejected} · unresolved candidates ${counts.candidates}`;
}

function draw() {
  if (!image.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, viewOffset.x, viewOffset.y, image.width * viewScale, image.height * viewScale);

  const showMeasures = showMeasuresToggle.checked;
  const showBarlines = showBarlinesToggle.checked;
  const showLabels = showLabelsToggle.checked;
  const showBase = showBaseToggle.checked;
  const showManual = showManualToggle.checked;

  const baseMap = baseMmrMap();
  const manualMap = manualMmrMap();
  measures.forEach((measure) => {
    const effective = effectiveMmrState(measure, baseMap, manualMap);
    const baseVisible = showBase && effective.baseSpan > 1;
    const manualVisible = showManual && Boolean(effective.manualOp);
    const geometryVisible = showMeasures || baseVisible || manualVisible;
    if (!geometryVisible) return;

    let color = COLOR_MEASURE;
    let thickness = 1.5;
    let fill = false;
    if (baseVisible) color = COLOR_BASE_MMR;
    if (manualVisible) {
      color = effective.manualOp === "suppress" ? COLOR_SUPPRESSED : COLOR_MANUAL;
      thickness = 2.5;
      fill = true;
    }

    let label = measureDisplayLabel(measure);
    if ((baseVisible || manualVisible) && (effective.baseSpan > 1 || effective.effectiveSpan > 1 || effective.manualOp)) {
      label += ` b${effective.baseSpan}->e${effective.effectiveSpan}`;
    }
    drawBox(measure.bbox, color, thickness, fill);
    if (showLabels) drawLabel(measure.bbox, label, color);
  });

  if (showBarlines) {
    barlines.forEach((barline, index) => {
      drawBox(barline.bbox, COLOR_BARLINE, 1.2);
      if (showLabels) drawLabel(barline.bbox, `B${index + 1}`, COLOR_BARLINE);
    });
  }

  if (showManual) {
    itemsForCurrentPage("barline_construction").forEach((item) => {
      if (!Array.isArray(item.bbox)) return;
      const isRemove = item.op === "remove_barline";
      const color = isRemove ? COLOR_SUPPRESSED : COLOR_MANUAL;
      drawBox(item.bbox, color, 2.5, isRemove);
      if (showLabels) drawLabel(item.bbox, operationLabel("barline_construction", item.op), color);
    });

    itemsForCurrentPage("measure_construction").forEach((item) => {
      const measure = measures.find(
        (candidate) =>
          String(candidate.system) === String(item.system) &&
          String(candidate.measure) === String(item.interval)
      );
      if (!measure) return;
      drawBox(measure.bbox, COLOR_MANUAL, 2.5, true);
      if (showLabels) drawLabel(measure.bbox, operationLabel("measure_construction", item.op), COLOR_MANUAL);
    });
  }

  if (showMovementToggle.checked) {
    movementSystemsOnPage().forEach((system) => {
      const state = movementStateAt(system);
      if (state) drawMovementMarker(system, state, false);
    });
  }

  if (
    currentType() === "movement_boundary" &&
    selectedMovementSystem !== null &&
    systemBounds(selectedMovementSystem)
  ) {
    drawMovementMarker(
      selectedMovementSystem,
      movementStateAt(selectedMovementSystem) || {
        label: "Target",
        color: COLOR_SELECTED,
        dashed: false,
      },
      true
    );
  }

  if (selectedMeasure && currentType() !== "movement_boundary") {
    drawBox(selectedMeasure.bbox, COLOR_SELECTED, 3, true);
    drawLabel(selectedMeasure.bbox, measureDisplayLabel(selectedMeasure), COLOR_SELECTED);
  }
  if (selectedBarline) {
    drawBox(selectedBarline.bbox, COLOR_SELECTED, 3, true);
    const barlineIndex = barlines.indexOf(selectedBarline);
    drawLabel(
      selectedBarline.bbox,
      barlineIndex >= 0 ? `Barline ${barlineIndex + 1}` : "Selected barline",
      COLOR_SELECTED
    );
  }

  if (selectedItemIndex !== null && currentType() !== "mmr_measure_span") {
    const stagedItem = itemsForCurrentPage(currentType())[selectedItemIndex];
    if (stagedItem && Array.isArray(stagedItem.bbox)) {
      drawBox(stagedItem.bbox, COLOR_SELECTED, 3, true);
    } else if (stagedItem && currentType() === "measure_construction") {
      const measure = measures.find(
        (candidate) =>
          String(candidate.system) === String(stagedItem.system) &&
          String(candidate.measure) === String(stagedItem.interval)
      );
      if (measure) drawBox(measure.bbox, COLOR_SELECTED, 3, true);
    }
  }

  if (draftBBox) {
    drawBox(draftBBox, COLOR_DRAFT, 2);
    drawLabel(draftBBox, "Draft", COLOR_DRAFT);
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
    if (pointInImageBox(imgPt, measures[i].bbox)) return measures[i];
  }
  return null;
}

function pickBarline(imgPt) {
  for (let i = barlines.length - 1; i >= 0; i--) {
    if (pointInImageBox(imgPt, barlines[i].bbox)) return barlines[i];
  }
  return null;
}

function pickSystem(imgPt) {
  const systems = Array.from(new Set(measures.map((measure) => String(measure.system))))
    .map((value) => parseInt(value, 10))
    .filter((value) => Number.isFinite(value));
  for (let i = systems.length - 1; i >= 0; i--) {
    const bounds = systemBounds(systems[i]);
    if (bounds && pointInImageBox(imgPt, bounds)) return systems[i];
  }
  return null;
}

function baseMmrMap() {
  const page = pageValue();
  const result = new Map();
  baseMmrOverrides.forEach((item) => {
    if (String(item.page) !== String(page)) return;
    result.set(measureKey(item.page, item.system, item.measure), item);
  });
  return result;
}

function manualMmrMap() {
  const result = new Map();
  itemsForCurrentPage("mmr_measure_span").forEach((item) => {
    result.set(measureKey(item.page, item.system, item.measure), item);
  });
  return result;
}

function effectiveMmrState(measure, baseMap = null, manualMap = null) {
  const page = pageValue();
  const key = measureKey(page, measure.system, measure.measure);
  const base = (baseMap || baseMmrMap()).get(key);
  const manual = (manualMap || manualMmrMap()).get(key);
  const baseSkip = base && base.skip !== undefined ? parseInt(base.skip, 10) : 0;
  const baseSpan = Number.isFinite(baseSkip) ? baseSkip + 1 : 1;
  let effectiveSpan = baseSpan;
  let manualOp = null;
  if (manual) {
    manualOp = manual.op;
    if (manual.op === "suppress") effectiveSpan = 1;
    if (manual.op === "set_measure_span") effectiveSpan = parseInt(manual.measure_span, 10);
  }
  return {
    base,
    manual,
    baseSpan,
    effectiveSpan: Number.isFinite(effectiveSpan) ? effectiveSpan : 1,
    manualOp,
  };
}

function updateSelectionMeta() {
  const parts = [];
  if (currentType() === "movement_boundary" && selectedMovementSystem !== null) {
    const source =
      selectedMeasure && String(selectedMeasure.system) === String(selectedMovementSystem)
        ? ` (clicked Measure ${displayIndex(selectedMeasure.measure)})`
        : "";
    parts.push(
      `Movement target: Page ${displayPageNumber()} / System ${displayIndex(selectedMovementSystem)}${source} — boundary position is BEFORE this system`
    );
  } else if (selectedMeasure) {
    const state = effectiveMmrState(selectedMeasure);
    parts.push(
      `Page ${displayPageNumber()} / System ${displayIndex(selectedMeasure.system)} / Measure ${displayIndex(selectedMeasure.measure)} | base=${state.baseSpan} effective=${state.effectiveSpan}`
    );
  }
  if (selectedBarline) {
    const barlineIndex = barlines.indexOf(selectedBarline);
    const label = barlineIndex >= 0 ? `Barline ${barlineIndex + 1}` : "Selected barline";
    parts.push(`${label} | bbox=[${selectedBarline.bbox.join(", ")}]`);
  }
  if (draftBBox) parts.push(`Draft bbox=[${draftBBox.join(", ")}]`);
  if (selectedItemIndex !== null && currentType() !== "mmr_measure_span") {
    const item = itemsForCurrentPage(currentType())[selectedItemIndex];
    if (item) parts.push(manualItemSummary(item, selectedItemIndex, currentType()));
  }
  selectionMeta.textContent = parts.length ? parts.join(" | ") : "No selection";
  updateMovementTargetMeta();
}

function renderPageList() {
  pageList.innerHTML = "";
  pages.forEach((page, index) => {
    const div = document.createElement("div");
    div.className = "list-item" + (index === currentIndex ? " active" : "");
    const pageNumber = displayPageNumberFor(page, index);
    const pageCoordinate =
      page.page !== undefined
        ? page.page
        : page.page_index !== undefined
          ? page.page_index
          : index;
    const pageCandidates = allMovementEvidenceCandidates.filter(
      (candidate) =>
        String(candidate.page) === String(pageCoordinate) &&
        candidate.state === "ambiguous_review_required"
    );
    const reviews = (correctionsByType.movement_boundary || []).filter(
      (item) => String(item.page) === String(pageCoordinate)
    );
    const reviewedSystems = new Set(reviews.map((item) => String(item.system)));
    const unresolvedCandidates = pageCandidates.filter(
      (candidate) => !reviewedSystems.has(String(candidate.system))
    ).length;
    const reviewedBoundaries = reviews.filter((item) => item.op === "boundary").length;
    const reviewedNoBoundary = reviews.filter((item) => item.op === "no_boundary").length;
    const movementParts = [];
    if (unresolvedCandidates) movementParts.push(`candidate ${unresolvedCandidates}`);
    if (reviewedBoundaries) movementParts.push(`boundary ${reviewedBoundaries}`);
    if (reviewedNoBoundary) movementParts.push(`no-boundary ${reviewedNoBoundary}`);
    const movementSummary = movementParts.length ? ` · movement: ${movementParts.join(", ")}` : "";
    div.textContent =
      `Page ${pageNumber}${page.name ? ` · ${page.name}` : ""}${movementSummary}`;
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

function renderMmrRows() {
  const selectedKey = selectedMeasureKey();
  const baseMap = baseMmrMap();
  const manualMap = manualMmrMap();
  measures.forEach((measure) => {
    const state = effectiveMmrState(measure, baseMap, manualMap);
    const div = document.createElement("div");
    const key = measureKey(pageValue(), measure.system, measure.measure);
    div.className = "list-item" + (key === selectedKey ? " active" : "");
    let status = "Normal";
    if (state.baseSpan > 1) status = "Base MMR";
    if (state.manualOp === "set_measure_span") status = "Staged: set span";
    if (state.manualOp === "suppress") status = "Staged: suppress";
    div.textContent = `System ${displayIndex(measure.system)} · Measure ${displayIndex(measure.measure)} | base=${state.baseSpan} → effective=${state.effectiveSpan} | ${status}`;
    div.onclick = () => selectMeasure(measure);
    itemList.appendChild(div);
  });
  if (!measures.length) {
    const div = document.createElement("div");
    div.className = "small";
    div.textContent = "No measure boxes loaded from the numbering artifact.";
    itemList.appendChild(div);
  }
}

function movementCandidateAt(system) {
  return movementEvidenceCandidates.find(
    (candidate) =>
      String(candidate.page) === String(pageValue()) &&
      String(candidate.system) === String(system) &&
      candidate.state === "ambiguous_review_required"
  );
}

function movementEvidenceText(candidate) {
  const evidence = {
    signals: candidate.signals || [],
    references: candidate.references || {},
  };
  return JSON.stringify(evidence);
}

function renderMovementRows() {
  const items = itemsForCurrentPage("movement_boundary");
  const bySystem = new Map(items.map((item, index) => [String(item.system), { item, index }]));
  const systems = movementSystemsOnPage();

  const guide = document.createElement("div");
  guide.className = "small";
  guide.textContent =
    "All locations below mean BEFORE System N. Click a row to target that system on the score.";
  itemList.appendChild(guide);

  systems.forEach((system) => {
    const review = bySystem.get(String(system));
    const candidate = movementCandidateAt(system);
    const resolved = resolvedMovementAt(system);
    const state = movementStateAt(system);
    if (!state) return;

    const div = document.createElement("div");
    div.className =
      "list-item" +
      (selectedMovementSystem !== null && String(selectedMovementSystem) === String(system)
        ? " active"
        : "");

    const title = document.createElement("div");
    let suffix = state.label;
    if (review && review.op === "boundary" && candidate) suffix = "reviewed candidate → boundary";
    else if (review && review.op === "boundary") suffix = "manual boundary";
    else if (review && review.op === "no_boundary") suffix = "candidate rejected / no boundary";
    else if (resolved) suffix = `existing resolved boundary · reset=${resolved.reset_number ?? 1}`;
    else if (candidate) suffix = "unresolved candidate";
    title.textContent = `BEFORE System ${displayIndex(system)} · ${suffix}`;
    div.appendChild(title);

    if (candidate) {
      const raw = document.createElement("div");
      raw.className = "small";
      raw.textContent = `Raw evidence: ${movementEvidenceText(candidate)}`;
      div.appendChild(raw);
    }

    div.onclick = () => {
      selectedMovementSystem = system;
      selectedMeasure = null;
      selectedBarline = null;
      movementSystemInput.value = String(displayIndex(system));
      selectedItemIndex = review ? review.index : null;
      updateSelectionMeta();
      renderItems();
      draw();
    };
    itemList.appendChild(div);
  });

  if (!systems.length) {
    const div = document.createElement("div");
    div.className = "small";
    div.textContent =
      "No movement candidate or resolved boundary is recorded on this page. Click a system to add a boundary manually before it.";
    itemList.appendChild(div);
  }
}

function renderManualItems() {
  const type = currentType();
  const items = itemsForCurrentPage(type);
  items.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "list-item" + (index === selectedItemIndex ? " active" : "");
    div.textContent = manualItemSummary(item, index, type);
    div.onclick = () => {
      selectedItemIndex = index;
      updateSelectionMeta();
      renderItems();
      draw();
    };
    itemList.appendChild(div);
  });
  if (!items.length) {
    const div = document.createElement("div");
    div.className = "small";
    div.textContent = "No staged corrections for this page/type.";
    itemList.appendChild(div);
  }
}

function updateActionButtons() {
  const type = currentType();
  if (type === "mmr_measure_span") {
    const canClear = Boolean(selectedMeasure && manualMmrMap().get(selectedMeasureKey()));
    deleteItemBtn.textContent = "Clear staged override";
    deleteItemBtn.disabled = !canClear;
    return;
  }
  const items = itemsForCurrentPage(type);
  const canUnstage = selectedItemIndex !== null && Boolean(items[selectedItemIndex]);
  deleteItemBtn.textContent = "Unstage selected";
  deleteItemBtn.disabled = !canUnstage;
}

function renderItems() {
  itemList.innerHTML = "";
  if (currentType() === "mmr_measure_span") renderMmrRows();
  else if (currentType() === "movement_boundary") renderMovementRows();
  else renderManualItems();
  updateActionButtons();
}

function currentReason() {
  return reasonInput.value.trim() || "manual correction";
}

function removeManualMmrForSelected(pageItems) {
  const key = selectedMeasureKey();
  return pageItems.filter((item) => measureKey(item.page, item.system, item.measure) !== key);
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
    replaceItemsForCurrentPage(type, removeManualMmrForSelected(itemsForCurrentPage(type)).concat([item]));
    setDirty(type, true);
    renderItems();
    updateSelectionMeta();
    draw();
    saveStatus.textContent = `Staged: ${operationLabel(type, item.op)}. Save writes corrections only; re-run evaluation separately.`;
    return;
  }

  if (type === "movement_boundary") {
    const visibleSystem = parseInt(movementSystemInput.value, 10);
    if (!Number.isFinite(visibleSystem) || visibleSystem < 1) {
      saveStatus.textContent = "System must be a visible 1-based integer.";
      return;
    }
    const system = visibleSystem - 1;
    selectedMovementSystem = system;
    if (!systemBounds(system)) {
      saveStatus.textContent = `System ${visibleSystem} is not present on this page.`;
      updateSelectionMeta();
      draw();
      return;
    }
    const candidate = movementCandidateAt(system);
    if (op === "no_boundary" && !candidate) {
      saveStatus.textContent =
        "Candidate absence is not a reviewed no-boundary. Mark no boundary only for an explicit candidate.";
      return;
    }
    item = {
      op,
      page,
      system,
      reason: currentReason(),
      evidence_candidate_id: candidate ? candidate.id : null,
      review_kind: candidate
        ? op === "boundary"
          ? "accepted_candidate"
          : "rejected_candidate"
        : "manual_boundary",
    };
    const pageItems = itemsForCurrentPage(type).filter(
      (existing) => String(existing.system) !== String(system)
    );
    pageItems.push(item);
    replaceItemsForCurrentPage(type, pageItems);
    setDirty(type, true);
    selectedItemIndex = pageItems.length - 1;
    renderItems();
    updateSelectionMeta();
    draw();
    saveStatus.textContent =
      item.op === "boundary"
        ? `Staged boundary BEFORE System ${visibleSystem}.`
        : `Staged candidate rejection: no boundary before System ${visibleSystem}.`;
    return;
  }

  if (type === "barline_construction") {
    const bbox = op === "remove_barline" && selectedBarline ? selectedBarline.bbox : draftBBox;
    if (!bbox) {
      saveStatus.textContent = "Select a barline or draw a bbox first.";
      return;
    }
    item = { op, page, bbox: bbox.map((value) => Math.round(value)), reason: currentReason() };
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
  updateSelectionMeta();
  draw();
  saveStatus.textContent = `Staged: ${operationLabel(type, item.op)}. Save writes corrections only; re-run evaluation separately.`;
}

function deleteSelectedItem() {
  const type = currentType();
  if (type === "mmr_measure_span" && selectedMeasure) {
    replaceItemsForCurrentPage(type, removeManualMmrForSelected(itemsForCurrentPage(type)));
    setDirty(type, true);
    renderItems();
    updateSelectionMeta();
    draw();
    saveStatus.textContent = "Removed manual MMR correction for selected measure.";
    return;
  }
  const pageItems = itemsForCurrentPage(type);
  if (selectedItemIndex === null || !pageItems[selectedItemIndex]) return;
  pageItems.splice(selectedItemIndex, 1);
  selectedItemIndex = null;
  replaceItemsForCurrentPage(type, pageItems);
  setDirty(type, true);
  updateSelectionMeta();
  renderItems();
  draw();
  saveStatus.textContent = "Removed staged correction.";
}

function loadCorrections() {
  const types = Object.keys(correctionsByType);
  const page = pageValue();
  return Promise.all(
    types.map((type) =>
      fetchJSON(
        `/api/manual_corrections?type=${encodeURIComponent(type)}&page=${encodeURIComponent(page)}`
      )
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
  resolvedMovementBoundaries = [];
  if (!path) return Promise.resolve();
  return fetchJSON(`/api/template?path=${encodeURIComponent(path)}`).then((data) => {
    const metadata = data && data.numbering_metadata;
    const recordedBoundaries =
      metadata && Array.isArray(metadata.movement_boundaries)
        ? metadata.movement_boundaries
        : [];
    resolvedMovementBoundaries = recordedBoundaries.filter(
      (boundary) =>
        boundary &&
        boundary.system !== undefined &&
        (boundary.page === undefined || String(boundary.page) === String(pageValue()))
    );
    const pageData = (data.pages && data.pages[0]) || data;
    const systems = pageData.systems || [];
    systems.forEach((system, systemIndex) => {
      (system.measures || []).forEach((measure, measureIndex) => {
        const bbox = measure.bbox || measure.measure_bbox || measure.bounds;
        if (!Array.isArray(bbox) || bbox.length !== 4) return;
        measures.push({
          bbox: bbox.map((value) => Math.round(value)),
          number: measure.number,
          system: system.index ?? system.system ?? systemIndex,
          measure: measure.index ?? measure.measure ?? measure.measure_number ?? measureIndex,
        });
      });
    });
  });
}

function normalizeMmrRecords(data) {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.measure_overrides)) return data.measure_overrides;
  if (Array.isArray(data.overrides)) return data.overrides;
  if (Array.isArray(data.items)) return data.items;
  return [];
}

function mmrPathFromPage(page) {
  return page.mmr || page.mmr_results || page.measure_overrides || page.overrides || null;
}

function loadMmr(path) {
  baseMmrOverrides = [];
  if (!path) return Promise.resolve();
  return fetchJSON(`/api/template?path=${encodeURIComponent(path)}`)
    .then((data) => {
      baseMmrOverrides = normalizeMmrRecords(data)
        .filter((item) => item && item.system !== undefined && item.measure !== undefined)
        .map((item) => ({
          ...item,
          page: item.page !== undefined ? item.page : pageValue(),
          system: parseInt(item.system, 10),
          measure: parseInt(item.measure, 10),
          skip: item.skip !== undefined ? parseInt(item.skip, 10) : 0,
        }));
    })
    .catch((error) => {
      baseMmrOverrides = [];
      saveStatus.textContent = `MMR base load failed: ${error.message}`;
    });
}

function barlinePathFromPage(page) {
  return page.barlines || page.barline_candidates || page.detected_barlines || null;
}

function loadMovementEvidence(path) {
  movementEvidenceCandidates = [];
  allMovementEvidenceCandidates = [];
  if (!path) return Promise.resolve();
  return fetchJSON(`/api/template?path=${encodeURIComponent(path)}`)
    .then((data) => {
      allMovementEvidenceCandidates = Array.isArray(data.candidates) ? data.candidates : [];
      movementEvidenceCandidates = allMovementEvidenceCandidates.filter(
        (candidate) => String(candidate.page) === String(pageValue())
      );
    })
    .catch((error) => {
      movementEvidenceCandidates = [];
      allMovementEvidenceCandidates = [];
      saveStatus.textContent = `Movement evidence load failed: ${error.message}`;
    });
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

function selectMeasure(measure) {
  selectedMeasure = measure;
  selectedBarline = null;
  selectedItemIndex = null;
  const state = effectiveMmrState(measure);
  measureSpanInput.value = String(state.effectiveSpan || state.baseSpan || 1);
  if (currentType() === "movement_boundary") {
    selectedMovementSystem = measure.system;
    movementSystemInput.value = String(displayIndex(measure.system));
  }
  updateSelectionMeta();
  renderItems();
  draw();
}

function loadPage() {
  currentPage = pages[currentIndex];
  selectedMeasure = null;
  selectedBarline = null;
  selectedItemIndex = null;
  selectedMovementSystem = null;
  draftBBox = null;
  saveStatus.textContent = "";
  exportMovementBtn.style.display = currentPage.movement_boundary_evidence ? "" : "none";
  pageMeta.textContent = `Page ${displayPageNumber()}${currentPage.name ? ` · ${currentPage.name}` : ""} | Save writes correction JSON only`;

  image.onload = () => {
    resetView();
    draw();
  };
  image.src = `/file?path=${encodeURIComponent(currentPage.image)}`;

  Promise.all([
    loadNumbering(currentPage.numbering),
    loadMmr(mmrPathFromPage(currentPage)),
    loadBarlines(barlinePathFromPage(currentPage)),
    loadMovementEvidence(currentPage.movement_boundary_evidence),
    loadCorrections(),
  ]).then(() => {
    updateSelectionMeta();
    renderItems();
    renderPageList();
    draw();
  });
}

function saveCorrectionType(type) {
  if (!currentPage) return Promise.resolve(null);
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
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    })
    .then((data) => {
      setDirty(type, false);
      return { type, output: data.output };
    });
}

function saveCorrectionTypes(types) {
  const uniqueTypes = Array.from(new Set(types));
  if (!currentPage || !uniqueTypes.length) return Promise.resolve([]);
  return Promise.all(uniqueTypes.map((type) => saveCorrectionType(type)))
    .then((saved) => {
      if (saved.length === 1) {
        saveStatus.textContent = `Saved ${saved[0].type}: ${saved[0].output}. Re-run evaluation separately.`;
      } else {
        saveStatus.textContent = `Saved ${saved.length} correction types: ${saved.map((item) => item.type).join(", ")}. Re-run evaluation separately.`;
      }
      return saved;
    })
    .catch((error) => {
      saveStatus.textContent = `Save failed: ${error.message}`;
      throw error;
    });
}

function saveDirtyTypes() {
  const types = Array.from(dirtyTypes);
  if (!types.length) {
    saveStatus.textContent = "No staged changes to save.";
    return Promise.resolve([]);
  }
  return saveCorrectionTypes(types);
}

function switchPage(nextIndex) {
  if (nextIndex === currentIndex) return;
  saveCorrectionTypes(Array.from(dirtyTypes))
    .then(() => {
      currentIndex = nextIndex;
      loadPage();
    })
    .catch((error) => {
      console.error("Page switch aborted due to save failure:", error);
    });
}

selectModeBtn.onclick = () => setMode("select");
drawModeBtn.onclick = () => setMode("draw");
addItemBtn.onclick = addCorrectionItem;
deleteItemBtn.onclick = deleteSelectedItem;
saveBtn.onclick = () => {
  saveDirtyTypes().catch(() => {});
};
exportMovementBtn.onclick = () => {
  saveDirtyTypes()
    .then(() =>
      fetch("/api/export_movement_boundaries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      })
    )
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    })
    .then((data) => {
      saveStatus.textContent =
        `Exported ${data.count} resolved movement boundaries: ${data.output}`;
    })
    .catch((error) => {
      saveStatus.textContent = `Movement boundary export failed: ${error.message}`;
    });
};
helpBtn.onclick = () => {
  helpPanel.open = true;
  helpPanel.scrollIntoView({ behavior: "smooth", block: "start" });
};

typeSelect.onchange = updateOps;
opSelect.onchange = updateControlState;
movementSystemInput.oninput = () => {
  const visibleSystem = parseInt(movementSystemInput.value, 10);
  selectedMovementSystem =
    Number.isFinite(visibleSystem) && visibleSystem >= 1 ? visibleSystem - 1 : null;
  selectedMeasure = null;
  selectedBarline = null;
  selectedItemIndex = null;
  updateSelectionMeta();
  renderItems();
  draw();
};

[
  showMeasuresToggle,
  showBarlinesToggle,
  showLabelsToggle,
  showBaseToggle,
  showManualToggle,
  showMovementToggle,
].forEach((toggle) => {
  toggle.onchange = draw;
});

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

  if (currentType() === "movement_boundary") {
    const system = pickSystem(imgPt);
    if (system !== null) {
      selectedMovementSystem = system;
      selectedMeasure = pickMeasure(imgPt);
      selectedBarline = null;
      selectedItemIndex = null;
      movementSystemInput.value = String(displayIndex(system));
      updateSelectionMeta();
      renderItems();
      draw();
      return;
    }
    selectedMovementSystem = null;
    selectedMeasure = null;
    selectedBarline = null;
    selectedItemIndex = null;
    movementSystemInput.value = "";
    updateSelectionMeta();
    renderItems();
    draw();
    return;
  }

  // In barline correction mode, barlines usually lie inside measure boxes.
  // Prioritize the active correction surface so measure hit-testing does not
  // make existing barlines effectively unselectable.
  if (currentType() === "barline_construction") {
    const barline = pickBarline(imgPt);
    if (barline) {
      selectedMeasure = null;
      selectedBarline = barline;
      selectedItemIndex = null;
      updateSelectionMeta();
      renderItems();
      draw();
      return;
    }
  }

  const measure = pickMeasure(imgPt);
  if (measure) selectMeasure(measure);
  else {
    selectedMeasure = null;
    selectedBarline = pickBarline(imgPt);
    updateSelectionMeta();
    renderItems();
    draw();
  }
});

canvas.addEventListener("mousemove", (event) => {
  const rect = canvas.getBoundingClientRect();
  const pt = { x: event.clientX - rect.left, y: event.clientY - rect.top };

  if (isPanning) {
    viewOffset = { x: panOrigin.x + (pt.x - panStart.x), y: panOrigin.y + (pt.y - panStart.y) };
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
  if (tag === "input" || tag === "select" || tag === "textarea") return;
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
