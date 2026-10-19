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
let movementSaveChain = Promise.resolve();
let movementLastSaveError = null;

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

const pageList = document.getElementById("pageList");
const itemList = document.getElementById("itemList");
const pageMeta = document.getElementById("pageMeta");
const saveStatus = document.getElementById("saveStatus");
const dirtyStatus = document.getElementById("dirtyStatus");
const selectionMeta = document.getElementById("selectionMeta");

const saveBtn = document.getElementById("saveBtn");
const panModeBtn = document.getElementById("panModeBtn");
const fitPageBtn = document.getElementById("fitPageBtn");
const previousPageBtn = document.getElementById("previousPageBtn");
const nextPageBtn = document.getElementById("nextPageBtn");
const previewNumbersBtn = document.getElementById("previewNumbersBtn");
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
const movementAfterBtn = document.getElementById("movementAfterBtn");
const movementTargetMeta = document.getElementById("movementTargetMeta");
const movementPageStatus = document.getElementById("movementPageStatus");
const reasonRow = document.getElementById("reasonRow");
const reasonInput = document.getElementById("reasonInput");

const showMeasuresToggle = document.getElementById("showMeasuresToggle");
const showBarlinesToggle = document.getElementById("showBarlinesToggle");
const showBarlineNumbersToggle = document.getElementById("showBarlineNumbersToggle");
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
let panMode = false;
let provisionalNumbering = new Map();
let provisionalNumberingVisible = false;
let provisionalNumberingRevision = 0;
let numberingPreviewRequestId = 0;
let movementAfterSource = null;
let movementAfterPageJump = null;

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

let OPS = window.ReviewStrings.operations;
function reviewerCopy(key, values = {}) {
  const template =
    key.split(".").reduce((entry, part) => entry && entry[part], window.ReviewStrings) ||
    window.ReviewStrings.feedback[key] ||
    key;
  return Object.entries(values).reduce((message, [name, value]) => message.replaceAll(`{${name}}`, String(value)), template);
}

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
  return reviewerCopy("ui.measureOverlay", {system: displayIndex(measure.system), measure: displayIndex(measure.measure)});
}

function operationLabel(correctionType, op) {
  const match = (OPS[correctionType] || []).find(([value]) => value === op);
  return match ? match[1] : op;
}

function manualItemSummary(item, index, correctionType) {
  const copy = window.ReviewStrings.ui;
  const parts = [
    reviewerCopy("ui.selectedCount", {number: index + 1}),
    operationLabel(correctionType, item.op),
    `${copy.page} ${displayIndex(item.page)}`,
  ];
  if (item.system !== undefined) parts.push(`${copy.system} ${displayIndex(item.system)}`);
  if (item.measure !== undefined) parts.push(`${copy.measure} ${displayIndex(item.measure)}`);
  if (item.interval !== undefined) parts.push(`${copy.measure} ${displayIndex(item.interval)}`);
  if (item.measure_span !== undefined) parts.push(reviewerCopy("ui.measureSpanLabel", {span: item.measure_span}));
  if (Array.isArray(item.bbox)) parts.push(`${copy.bbox}=[${item.bbox.join(", ")}]`);
  return parts.join(" · ");
}

function measureKey(page, system, measure) {
  return `${page}:${system}:${measure}`;
}

function selectedMeasureKey() {
  if (!selectedMeasure) return null;
  return measureKey(pageValue(), selectedMeasure.system, selectedMeasure.measure);
}

function invalidateProvisionalNumbering() {
  provisionalNumberingRevision += 1;
  provisionalNumberingVisible = false;
  previewNumbersBtn.setAttribute("aria-pressed", "false");
}

function setDirty(correctionType, isDirty) {
  if (isDirty) dirtyTypes.add(correctionType);
  else dirtyTypes.delete(correctionType);
  if (isDirty) invalidateProvisionalNumbering();
  updateDirtyStatus();
}

function updateDirtyStatus() {
  dirtyStatus.textContent = dirtyTypes.size
    ? reviewerCopy("ui.unsavedTypes", {types: Array.from(dirtyTypes).map(type => window.ReviewStrings.types[type] || type).join(", ")})
    : "";
}

function updateOps(preserveSelection = false) {
  OPS = window.ReviewStrings.operations;
  const selectedOperation = preserveSelection ? currentOp() : null;
  opSelect.innerHTML = "";
  OPS[currentType()].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    opSelect.appendChild(option);
  });
  if (selectedOperation && OPS[currentType()].some(([value]) => value === selectedOperation)) {
    opSelect.value = selectedOperation;
  }
  if (!preserveSelection) selectedItemIndex = null;
  updateControlState();
}

function updateControlState() {
  const type = currentType();
  const op = currentOp();
  const movementMode = type === "movement_boundary";
  const barlineMode = type === "barline_construction";
  document.getElementById("taskHelp").textContent = window.ReviewStrings.taskSummary[type];
  document.getElementById("taskHelpDetails").textContent = window.ReviewStrings.taskHelp[type];
  document.getElementById("restReviewGuide").hidden = type !== "mmr_measure_span";
  document.getElementById("restReviewInstructions").hidden = type !== "mmr_measure_span";
  document.getElementById("operationRow").hidden =
    type === "measure_construction" || (movementMode && !currentPage?.movement_boundary_evidence);
  selectionMeta.hidden = movementMode;
  movementPageStatus.hidden = !movementMode;

  measureSpanRow.style.display =
    type === "mmr_measure_span" && op === "set_measure_span" ? "flex" : "none";
  movementBoundaryPanel.style.display = movementMode ? "" : "none";

  // Only barline editing has two interaction modes. Other correction surfaces
  // select their target directly on the score.
  selectModeBtn.style.display = barlineMode ? "" : "none";
  drawModeBtn.style.display = barlineMode ? "" : "none";
  drawModeBtn.disabled = !barlineMode;
  if (!barlineMode && mode === "draw") setMode("select");

  // Other correction types on this page may still have pending edits.
  saveBtn.style.display = "";
  exportMovementBtn.style.display =
    movementMode && currentPage && currentPage.movement_boundary_evidence ? "" : "none";
  movementAfterBtn.style.display = movementMode ? "" : "none";
  reasonRow.style.display = movementMode ? "none" : "";

  if (movementMode && selectedMeasure && selectedMovementSystem === null) {
    selectedMovementSystem = selectedMeasure.system;
    movementSystemInput.value = String(displayIndex(selectedMovementSystem));
  }

  if (movementMode) {
    addItemBtn.textContent =
      op === "boundary" ? window.ReviewStrings.ui.confirmBoundary : window.ReviewStrings.ui.confirmNoBoundary;
  } else {
    addItemBtn.textContent = window.ReviewStrings.stage;
  }

  const noBoundaryOption = opSelect.querySelector("option[value=no_boundary]");
  if (noBoundaryOption) noBoundaryOption.hidden = !currentPage?.movement_boundary_evidence;
  renderItems();
  updateSelectionMeta();
  draw();
}

function setMode(nextMode) {
  mode = nextMode;
  selectModeBtn.classList.toggle("active", mode === "select");
  drawModeBtn.classList.toggle("active", mode === "draw");
  if (mode === "draw") panMode = false;
  updatePanControl();
}

function resetView() {
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width));
  canvas.height = Math.max(1, Math.round(rect.height));
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

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * canvas.width / rect.width,
    y: (event.clientY - rect.top) * canvas.height / rect.height,
  };
}

function updatePanControl() {
  panModeBtn.classList.toggle("active", panMode);
  panModeBtn.setAttribute("aria-pressed", String(panMode));
  canvas.style.cursor = panMode ? "grab" : mode === "draw" ? "crosshair" : "default";
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

function drawBarlineCorrection(item) {
  if (!Array.isArray(item.bbox) || item.bbox.length !== 4) return;
  const [x1, y1, x2, y2] = item.bbox;
  const start = imgToCanvas({ x: x1, y: y1 });
  const end = imgToCanvas({ x: x2, y: y2 });
  const vertical = Math.abs(end.y - start.y) >= Math.abs(end.x - start.x);
  const center = vertical
    ? { from: { x: (start.x + end.x) / 2, y: start.y }, to: { x: (start.x + end.x) / 2, y: end.y } }
    : { from: { x: start.x, y: (start.y + end.y) / 2 }, to: { x: end.x, y: (start.y + end.y) / 2 } };
  const removed = item.op === "remove_barline";
  const color = removed ? COLOR_SUPPRESSED : COLOR_MANUAL;
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(center.from.x, center.from.y);
  ctx.lineTo(center.to.x, center.to.y);
  if (removed) {
    ctx.strokeStyle = "rgba(255,255,255,.94)";
    ctx.lineWidth = Math.max(4, viewScale * 5);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(center.from.x, center.from.y);
    ctx.lineTo(center.to.x, center.to.y);
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
  } else {
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
  }
  ctx.stroke();
  ctx.restore();
  drawBox(item.bbox, color, 2, !removed);
  const label = removed
    ? window.ReviewStrings.ui.removedBarline
    : window.ReviewStrings.ui.addedBarline;
  drawLabel(item.bbox, label, color);
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
  const copy = window.ReviewStrings.ui;
  const review = movementReviewAt(system);
  const candidate = movementCandidateAt(system);
  const resolved = resolvedMovementAt(system);
  if (review) {
    if (review.op === "boundary") {
      return {
        kind: candidate ? "reviewed_candidate_boundary" : "manual_boundary",
        label: candidate ? copy.confirmedBoundary : copy.manualBoundary,
        color: COLOR_MOVEMENT_BOUNDARY,
        dashed: false,
      };
    }
    return {
      kind: "reviewed_no_boundary",
      label: copy.checkedNoBoundary,
      color: COLOR_MOVEMENT_REJECTED,
      dashed: true,
    };
  }
  if (resolved) {
    return {
      kind: "existing_resolved_boundary",
      label: window.ReviewStrings.ui.currentNumberingBoundary,
      color: COLOR_MOVEMENT_EXISTING,
      dashed: false,
    };
  }
  if (candidate) {
    return {
      kind: "unresolved_candidate",
      label: copy.suggestedBoundary,
      color: COLOR_MOVEMENT_CANDIDATE,
      dashed: true,
    };
  }
  return null;
}

function movementSystemsOnPage() {
  const systems = new Set();
  measures.forEach((measure) => systems.add(String(measure.system)));
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
    reviewerCopy("ui.movementCanvas", {label: selected ? window.ReviewStrings.ui.target : state.label, system: displayIndex(system)}),
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
    movementTargetMeta.textContent = window.ReviewStrings.ui.noSystem;
  } else {
    const bounds = systemBounds(system);
    const state = movementStateAt(system);
    const status = state ? ` ${reviewerCopy("ui.currentState", {state: state.label})}` : "";
    movementTargetMeta.textContent = bounds
      ? `${system > 0 ? reviewerCopy("ui.afterAndBeforeSystem", {previous: displayIndex(system - 1), system: displayIndex(system)}) : reviewerCopy("ui.targetBefore", {system: displayIndex(system)})}${status}`
      : reviewerCopy("ui.missingSystem", {system: displayIndex(system)});
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
  movementPageStatus.textContent = reviewerCopy("ui.movementCounts", {existing: counts.existing, confirmed: counts.reviewed, checked: counts.rejected, suggestions: counts.candidates});
  updateMovementFinishButton();
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
    const restReview = effective.baseSpan > 1 || effective.effectiveSpan > 1 || effective.manualOp;
    if ((baseVisible || manualVisible) && restReview) {
      label += ` b${effective.baseSpan}->e${effective.effectiveSpan}`;
    }
    drawBox(measure.bbox, color, thickness, fill);
    if (showLabels) drawLabel(measure.bbox, label, color);
    if (restReview) {
      const unit = effective.effectiveSpan === 1
        ? window.ReviewStrings.ui.oneMeasure
        : window.ReviewStrings.ui.manyMeasures;
      drawLabel(measure.bbox, reviewerCopy("ui.restMeasures", {count: effective.effectiveSpan, unit}), color);
    }
  });

  if (showBarlines) {
    barlines.forEach((barline, index) => {
      drawBox(barline.bbox, COLOR_BARLINE, 1.2);
      if (showBarlineNumbersToggle.checked) drawLabel(barline.bbox, `B${index + 1}`, COLOR_BARLINE);
    });
  }

  if (showManual) {
    itemsForCurrentPage("barline_construction").forEach(drawBarlineCorrection);

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

  if (provisionalNumberingVisible) {
    const pagePreview = provisionalNumbering.get(String(pageValue())) || new Map();
    pagePreview.forEach((preview, system) => {
      const bounds = systemBounds(system);
      if (!bounds) return;
      const baseline = measures
        .filter((measure) => String(measure.system) === String(system))
        .sort((a, b) => a.measure - b.measure)[0]?.number;
      const label = baseline === undefined
        ? reviewerCopy("ui.previewNumber", {number: preview.first_measure_number})
        : `${reviewerCopy("ui.previewBase", {number: baseline})} → ${reviewerCopy("ui.previewNumber", {number: preview.first_measure_number})}`;
      drawLabel(bounds, label, "#ff8a00");
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
        label: window.ReviewStrings.ui.targetLabel,
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
      barlineIndex >= 0 ? reviewerCopy("ui.barlineIndex", {number: barlineIndex + 1}) : window.ReviewStrings.ui.selectedBarline,
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
    drawLabel(draftBBox, window.ReviewStrings.ui.draftLabel, COLOR_DRAFT);
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
    const source = selectedMeasure && String(selectedMeasure.system) === String(selectedMovementSystem)
      ? ` · ${window.ReviewStrings.ui.measure} ${displayIndex(selectedMeasure.measure)}` : "";
    parts.push(reviewerCopy("ui.movementSelection", {page: displayPageNumber(), system: displayIndex(selectedMovementSystem), source}));
  } else if (selectedMeasure) {
    const state = effectiveMmrState(selectedMeasure);
    parts.push(reviewerCopy("ui.measureSelection", {page: displayPageNumber(), system: displayIndex(selectedMeasure.system), measure: displayIndex(selectedMeasure.measure), base: state.baseSpan, effective: state.effectiveSpan}));
  }
  if (selectedBarline) {
    const barlineIndex = barlines.indexOf(selectedBarline);
    const label = barlineIndex >= 0 ? reviewerCopy("ui.barlineIndex", {number: barlineIndex + 1}) : window.ReviewStrings.ui.selectedBarline;
    parts.push(`${label} | ${window.ReviewStrings.ui.bbox}=[${selectedBarline.bbox.join(", ")}]`);
  }
  if (draftBBox) parts.push(`${window.ReviewStrings.ui.draft} ${window.ReviewStrings.ui.bbox}=[${draftBBox.join(", ")}]`);
  if (selectedItemIndex !== null && currentType() !== "mmr_measure_span") {
    const item = itemsForCurrentPage(currentType())[selectedItemIndex];
    if (item) parts.push(manualItemSummary(item, selectedItemIndex, currentType()));
  }
  selectionMeta.textContent = parts.length ? parts.join(" | ") : window.ReviewStrings.noSelection;
  updateMovementTargetMeta();
}

function movementReviewKey(page, system) {
  return `${page}:${system}`;
}

function unresolvedMovementSuggestionCount() {
  const decided = new Set(
    (correctionsByType.movement_boundary || [])
      .filter((item) => item && item.evidence_candidate_id)
      .map((item) => movementReviewKey(item.page, item.system))
  );
  return allMovementEvidenceCandidates.filter(
    (candidate) =>
      candidate &&
      candidate.state === "ambiguous_review_required" &&
      !decided.has(movementReviewKey(candidate.page, candidate.system))
  ).length;
}

function updateMovementFinishButton() {
  if (!exportMovementBtn) return;
  const remaining = unresolvedMovementSuggestionCount();
  exportMovementBtn.disabled = remaining > 0;
  exportMovementBtn.textContent =
    remaining > 0
      ? reviewerCopy("ui.finishMovementRemaining", {count: remaining})
      : window.ReviewStrings.ui.finishMovement;
  exportMovementBtn.title =
    remaining > 0
      ? window.ReviewStrings.ui.finishMovementHint
      : window.ReviewStrings.ui.finishMovementDoneHint;
}

function renderPageList() {
  pageList.innerHTML = "";
  pages.forEach((page, index) => {
    const div = document.createElement("button");
    div.type = "button";
    div.className = "list-item page-choice" + (index === currentIndex ? " active" : "");
    if (index === currentIndex) div.setAttribute("aria-current", "page");
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
    if (unresolvedCandidates) movementParts.push(reviewerCopy("ui.suggested", {count: unresolvedCandidates}));
    if (reviewedBoundaries) movementParts.push(reviewerCopy("ui.confirmed", {count: reviewedBoundaries}));
    if (reviewedNoBoundary) movementParts.push(reviewerCopy("ui.checked", {count: reviewedNoBoundary}));
    const movementSummary = movementParts.length ? ` · ${window.ReviewStrings.ui.movement}: ${movementParts.join(", ")}` : "";
    div.textContent =
      reviewerCopy("ui.pageName", {page: pageNumber, name: page.name ? ` · ${page.name}` : ""}) + movementSummary;
    div.onclick = () => switchPage(index);
    pageList.appendChild(div);
  });
  updatePageNavigation();
  updateMovementFinishButton();
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
    const div = document.createElement("button");
    div.type = "button";
    const key = measureKey(pageValue(), measure.system, measure.measure);
    div.className = "list-item score-choice" + (key === selectedKey ? " active" : "");
    div.setAttribute("aria-pressed", String(key === selectedKey));
    let status = window.ReviewStrings.ui.normal;
    if (state.baseSpan > 1) status = window.ReviewStrings.ui.baseMmr;
    if (state.manualOp === "set_measure_span") status = window.ReviewStrings.feedback.stagedSpan;
    if (state.manualOp === "suppress") status = window.ReviewStrings.feedback.stagedSuppression;
    div.textContent = reviewerCopy("ui.mmrRow", {system: displayIndex(measure.system), measure: displayIndex(measure.measure), base: state.baseSpan, effective: state.effectiveSpan, status});
    div.onclick = () => selectMeasure(measure);
    itemList.appendChild(div);
  });
  if (!measures.length) {
    const div = document.createElement("div");
    div.className = "small";
    div.textContent = window.ReviewStrings.ui.noMeasures;
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
  guide.textContent = window.ReviewStrings.ui.movementGuide;
  itemList.appendChild(guide);

  systems.forEach((system) => {
    const review = bySystem.get(String(system));
    const candidate = movementCandidateAt(system);
    const resolved = resolvedMovementAt(system);
    const state = movementStateAt(system) || {
      label: window.ReviewStrings.ui.noBoundaryState,
      color: COLOR_MOVEMENT_REJECTED,
      dashed: true,
    };

    const div = document.createElement("div");
    div.className = "movement-row";

    const title = document.createElement("button");
    title.type = "button";
    title.className = "list-item score-choice" +
      (selectedMovementSystem !== null && String(selectedMovementSystem) === String(system) ? " active" : "");
    title.setAttribute(
      "aria-pressed",
      String(selectedMovementSystem !== null && String(selectedMovementSystem) === String(system))
    );
    let suffix = state.label;
    if (review && review.op === "boundary" && candidate) suffix = window.ReviewStrings.ui.confirmedBoundary;
    else if (review && review.op === "boundary") suffix = window.ReviewStrings.ui.manualBoundary;
    else if (review && review.op === "no_boundary") suffix = window.ReviewStrings.ui.checkedNoBoundary;
    else if (resolved) suffix = reviewerCopy("ui.resolvedBoundary", {reset: resolved.reset_number ?? 1});
    else if (candidate) suffix = window.ReviewStrings.ui.suggestedBoundary;
    const afterPreviousPage = review?.item?.reason?.match(
      /^Manual boundary after page (\d+) system (\d+)$/
    );
    title.textContent = afterPreviousPage
      ? reviewerCopy("ui.boundaryAfterLocation", {page: afterPreviousPage[1], system: afterPreviousPage[2], nextPage: displayPageNumber(), next: displayIndex(system), state: suffix})
      : system > 0
        ? reviewerCopy("ui.afterAndBeforeSystemState", {previous: displayIndex(system - 1), system: displayIndex(system), state: suffix})
        : reviewerCopy("ui.beforeSystem", {system: displayIndex(system), state: suffix});
    div.appendChild(title);

    if (candidate) {
      const details = document.createElement("details");
      details.className = "small";
      const summary = document.createElement("summary");
      summary.textContent = window.ReviewStrings.ui.detectionDetails;
      const raw = document.createElement("code");
      raw.textContent = movementEvidenceText(candidate);
      details.appendChild(summary);
      details.appendChild(raw);
      div.appendChild(details);
    }

    title.onclick = () => {
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
    div.textContent = window.ReviewStrings.ui.noBoundaryRows;
    itemList.appendChild(div);
  }
}

function renderManualItems() {
  const type = currentType();
  const items = itemsForCurrentPage(type);
  items.forEach((item, index) => {
    const div = document.createElement("button");
    div.type = "button";
    div.className = "list-item score-choice" + (index === selectedItemIndex ? " active" : "");
    div.setAttribute("aria-pressed", String(index === selectedItemIndex));
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
    div.textContent = window.ReviewStrings.noPageChanges;
    itemList.appendChild(div);
  }
}

function updateActionButtons() {
  const type = currentType();
  if (type === "mmr_measure_span") {
    const canClear = Boolean(selectedMeasure && manualMmrMap().get(selectedMeasureKey()));
    deleteItemBtn.style.display = canClear ? "" : "none";
    deleteItemBtn.textContent = window.ReviewStrings.remove;
    deleteItemBtn.disabled = !canClear;
    return;
  }
  const items = itemsForCurrentPage(type);
  const canRemove = selectedItemIndex !== null && Boolean(items[selectedItemIndex]);
  if (type === "movement_boundary") {
    deleteItemBtn.style.display = canRemove ? "" : "none";
    deleteItemBtn.textContent = window.ReviewStrings.clearDecision;
    deleteItemBtn.disabled = !canRemove;
    return;
  }
  deleteItemBtn.style.display = canRemove ? "" : "none";
  deleteItemBtn.textContent = window.ReviewStrings.remove;
  deleteItemBtn.disabled = !canRemove;
}

function renderItems() {
  itemList.innerHTML = "";
  document.getElementById("itemListHeading").textContent =
    window.ReviewStrings.listHeadings[currentType()];
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

function addMovementBoundaryAfterSelected() {
  const sourceSystem = selectedMovementSystem;
  if (sourceSystem === null || !Number.isFinite(sourceSystem) || !systemBounds(sourceSystem)) {
    saveStatus.textContent = reviewerCopy("ui.selectSystemForAfter");
    return;
  }
  const nextSystem = sourceSystem + 1;
  const sourcePageNumber = displayPageNumber();
  if (systemBounds(nextSystem)) {
    movementAfterSource = { page: sourcePageNumber, system: displayIndex(sourceSystem) };
    selectedMovementSystem = nextSystem;
    movementSystemInput.value = String(displayIndex(nextSystem));
    opSelect.value = "boundary";
    updateControlState();
    addCorrectionItem();
    return;
  }
  if (currentIndex + 1 >= pages.length) {
    saveStatus.textContent = reviewerCopy("ui.noFollowingSystem");
    return;
  }
  movementAfterPageJump = {
    sourcePage: sourcePageNumber,
    sourceSystem: displayIndex(sourceSystem),
    targetIndex: currentIndex + 1,
  };
  switchPage(currentIndex + 1);
}

function addCorrectionItem() {
  const type = currentType();
  const op = currentOp();
  const page = pageValue();
  let item = null;

  if (type === "mmr_measure_span") {
    if (!selectedMeasure) {
      saveStatus.textContent = reviewerCopy("selectMeasure");
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
        saveStatus.textContent = reviewerCopy("invalidSpan");
        return;
      }
      item.measure_span = span;
    }
    replaceItemsForCurrentPage(type, removeManualMmrForSelected(itemsForCurrentPage(type)).concat([item]));
    setDirty(type, true);
    renderItems();
    updateSelectionMeta();
    draw();
    saveStatus.textContent = reviewerCopy("draftAdded");
    return;
  }

  if (type === "movement_boundary") {
    const visibleSystem = parseInt(movementSystemInput.value, 10);
    if (!Number.isFinite(visibleSystem) || visibleSystem < 1) {
      saveStatus.textContent = reviewerCopy("invalidSystem");
      return;
    }
    const system = visibleSystem - 1;
    selectedMovementSystem = system;
    if (!systemBounds(system)) {
      saveStatus.textContent = reviewerCopy("missingSystem", {system: visibleSystem});
      updateSelectionMeta();
      draw();
      return;
    }
    const candidate = movementCandidateAt(system);
    if (op === "no_boundary" && !candidate) {
      saveStatus.textContent =
        reviewerCopy("noSuggestion");
      return;
    }
    item = {
      op,
      page,
      system,
      reason: movementAfterSource
        ? `Manual boundary after page ${movementAfterSource.page} system ${movementAfterSource.system}`
        : candidate ? "movement boundary review" : "manual movement boundary",
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
    invalidateProvisionalNumbering();
    replaceItemsForCurrentPage(type, pageItems);
    selectedItemIndex = pageItems.length - 1;
    renderItems();
    updateSelectionMeta();
    draw();
    saveStatus.textContent = movementAfterSource
      ? reviewerCopy("ui.savingAfterBoundary", {page: movementAfterSource.page, system: movementAfterSource.system, next: displayIndex(system)})
      : item.op === "boundary"
        ? reviewerCopy("savingBoundary", {system: displayIndex(visibleSystem - 1)})
        : reviewerCopy("savingNoBoundary", {system: displayIndex(visibleSystem - 1)});

    queueMovementSave(page, pageItems)
      .then(() => {
        renderItems();
        renderPageList();
        updateSelectionMeta();
        draw();
        saveStatus.textContent = movementAfterSource
          ? reviewerCopy("ui.savedAfterBoundary", {page: movementAfterSource.page, system: movementAfterSource.system, next: displayIndex(system)})
          : item.op === "boundary"
            ? reviewerCopy("savedBoundary", {system: displayIndex(visibleSystem - 1)})
            : reviewerCopy("savedNoBoundary", {system: displayIndex(visibleSystem - 1)});
        movementAfterSource = null;
      })
      .catch((error) => {
        movementAfterSource = null;
        saveStatus.textContent = reviewerCopy("movementSaveFailed", {error: error.message});
      });
    return;
  }

  if (type === "barline_construction") {
    const bbox = op === "remove_barline" && selectedBarline ? selectedBarline.bbox : draftBBox;
    if (!bbox) {
      saveStatus.textContent = reviewerCopy("selectBarline");
      return;
    }
    item = { op, page, bbox: bbox.map((value) => Math.round(value)), reason: currentReason() };
  }

  if (type === "measure_construction") {
    if (!selectedMeasure) {
      saveStatus.textContent = reviewerCopy("selectInterval");
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
  saveStatus.textContent = reviewerCopy("draftAdded");
}

function deleteSelectedItem() {
  const type = currentType();
  if (type === "mmr_measure_span" && selectedMeasure) {
    replaceItemsForCurrentPage(type, removeManualMmrForSelected(itemsForCurrentPage(type)));
    setDirty(type, true);
    renderItems();
    updateSelectionMeta();
    draw();
    saveStatus.textContent = window.ReviewStrings.ui.removedMmr;
    return;
  }
  const pageItems = itemsForCurrentPage(type);
  if (selectedItemIndex === null || !pageItems[selectedItemIndex]) return;
  pageItems.splice(selectedItemIndex, 1);
  invalidateProvisionalNumbering();
  selectedItemIndex = null;
  replaceItemsForCurrentPage(type, pageItems);
  if (type !== "movement_boundary") setDirty(type, true);
  updateSelectionMeta();
  renderItems();
  draw();

  if (type === "movement_boundary") {
    const page = pageValue();
    saveStatus.textContent = reviewerCopy("removingDecision");
    queueMovementSave(page, pageItems)
      .then(() => {
        renderItems();
        renderPageList();
        updateSelectionMeta();
        draw();
        saveStatus.textContent = reviewerCopy("clearedDecision");
      })
      .catch((error) => {
        saveStatus.textContent = reviewerCopy("movementSaveFailed", {error: error.message});
      });
    return;
  }

  saveStatus.textContent = reviewerCopy("removedDraft");
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
      saveStatus.textContent = reviewerCopy("ui.baseLoadFailed", {error: error.message});
    });
}

function barlinePathFromPage(page) {
  return page.barlines || page.barline_candidates || page.detected_barlines || null;
}

function movementEvidenceCandidateId(candidate) {
  if (candidate && typeof candidate.id === "string" && candidate.id) return candidate.id;
  return `page:${candidate.page}:system:${candidate.system}`;
}

function loadMovementEvidence(path) {
  movementEvidenceCandidates = [];
  allMovementEvidenceCandidates = [];
  if (!path) return Promise.resolve();
  return fetchJSON(`/api/template?path=${encodeURIComponent(path)}`)
    .then((data) => {
      const candidates = Array.isArray(data.candidates) ? data.candidates : [];
      allMovementEvidenceCandidates = candidates.map((candidate) => ({
        ...candidate,
        id: movementEvidenceCandidateId(candidate),
      }));
      movementEvidenceCandidates = allMovementEvidenceCandidates.filter(
        (candidate) => String(candidate.page) === String(pageValue())
      );
    })
    .catch((error) => {
      movementEvidenceCandidates = [];
      allMovementEvidenceCandidates = [];
      saveStatus.textContent = reviewerCopy("ui.movementLoadFailed", {error: error.message});
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
  pageMeta.textContent = reviewerCopy("ui.pageName", {page: displayPageNumber(), name: currentPage.name ? ` · ${currentPage.name}` : ""});

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
    updateControlState();
    renderPageList();
    if (movementAfterPageJump && movementAfterPageJump.targetIndex === currentIndex) {
      const after = movementAfterPageJump;
      const firstSystem = movementSystemsOnPage()[0];
      if (firstSystem === undefined) {
        const nextIndex = currentIndex + 1;
        if (nextIndex < pages.length) {
          movementAfterPageJump = {...after, targetIndex: nextIndex};
          switchPage(nextIndex);
        } else {
          movementAfterPageJump = null;
          saveStatus.textContent = reviewerCopy("ui.noFollowingSystem");
        }
      } else {
        movementAfterPageJump = null;
        movementAfterSource = { page: after.sourcePage, system: after.sourceSystem };
        typeSelect.value = "movement_boundary";
        updateOps();
        opSelect.value = "boundary";
        selectedMovementSystem = firstSystem;
        movementSystemInput.value = String(displayIndex(firstSystem));
        updateControlState();
        addCorrectionItem();
      }
    }
  });
}

function saveCorrectionPage(type, page, items) {
  const payload = {
    page,
    correction_type: type,
    items,
  };
  return fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((response) => {
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  });
}

function saveCorrectionType(type) {
  if (!currentPage) return Promise.resolve(null);
  return saveCorrectionPage(type, pageValue(), itemsForCurrentPage(type)).then((data) => {
    setDirty(type, false);
    return { type, output: data.output };
  });
}

function queueMovementSave(page, items) {
  const capturedItems = items.map((item) => ({ ...item }));
  const operation = movementSaveChain.then(() =>
    saveCorrectionPage("movement_boundary", page, capturedItems)
  );
  movementSaveChain = operation.then(
    () => {
      movementLastSaveError = null;
    },
    (error) => {
      movementLastSaveError = error;
    }
  );
  return operation;
}

function waitForMovementSaves() {
  return movementSaveChain.then(() => {
    if (movementLastSaveError) throw movementLastSaveError;
  });
}

function saveCorrectionTypes(types) {
  const uniqueTypes = Array.from(new Set(types));
  if (!currentPage || !uniqueTypes.length) return Promise.resolve([]);
  return Promise.all(uniqueTypes.map((type) => saveCorrectionType(type)))
    .then((saved) => {
      if (saved.length === 1) {
        saveStatus.textContent = window.ReviewStrings.saved;
      } else {
        saveStatus.textContent = window.ReviewStrings.saved;
      }
      return saved;
    })
    .catch((error) => {
      saveStatus.textContent = reviewerCopy("saveFailed", {error: error.message});
      throw error;
    });
}

function saveDirtyTypes() {
  const types = Array.from(dirtyTypes);
  if (!types.length) {
    saveStatus.textContent = window.ReviewStrings.noChanges;
    return Promise.resolve([]);
  }
  return saveCorrectionTypes(types);
}

function releaseTransientInteraction() {
  isPanning = false;
  isDrawing = false;
  drawStart = null;
  spaceDown = false;
}

function blurActiveControl() {
  const active = document.activeElement;
  if (active && typeof active.blur === "function") active.blur();
}

function startRestCountReview() {
  releaseTransientInteraction();
  typeSelect.value = "mmr_measure_span";
  updateOps();
  document.getElementById("resultDetails").open = true;
}

function switchPage(nextIndex) {
  if (nextIndex === currentIndex || nextIndex < 0 || nextIndex >= pages.length) return;
  waitForMovementSaves()
    .then(() => saveCorrectionTypes(Array.from(dirtyTypes)))
    .then(() => {
      currentIndex = nextIndex;
      loadPage();
    })
    .catch((error) => {
      saveStatus.textContent = reviewerCopy("pageSaveFailed", {error: error.message});
      console.error("Page switch aborted due to save failure:", error);
    });
}

function updatePageNavigation() {
  previousPageBtn.disabled = currentIndex <= 0;
  nextPageBtn.disabled = currentIndex >= pages.length - 1;
}

function navigateScoreTarget(direction) {
  if (!currentPage) return;
  if (currentType() === "movement_boundary") {
    const targets = movementSystemsOnPage();
    if (!targets.length) return;
    const current = targets.indexOf(selectedMovementSystem);
    selectedMovementSystem = targets[Math.max(0, Math.min(targets.length - 1, current + direction))];
    selectedMeasure = null;
    selectedBarline = null;
    selectedItemIndex = null;
    movementSystemInput.value = String(displayIndex(selectedMovementSystem));
  } else if (currentType() === "barline_construction" && barlines.length) {
    const current = barlines.indexOf(selectedBarline);
    selectedBarline = barlines[Math.max(0, Math.min(barlines.length - 1, current + direction))];
    selectedMeasure = null;
    selectedItemIndex = null;
  } else if (measures.length) {
    const current = measures.indexOf(selectedMeasure);
    selectedMeasure = measures[Math.max(0, Math.min(measures.length - 1, current + direction))];
    selectedBarline = null;
    selectedItemIndex = null;
    const state = effectiveMmrState(selectedMeasure);
    measureSpanInput.value = String(state.effectiveSpan || state.baseSpan || 1);
  }
  updateSelectionMeta();
  renderItems();
  draw();
}

selectModeBtn.onclick = (event) => {
  event.currentTarget.blur();
  setMode("select");
};
drawModeBtn.onclick = (event) => {
  event.currentTarget.blur();
  setMode("draw");
};
addItemBtn.onclick = (event) => {
  event.currentTarget.blur();
  releaseTransientInteraction();
  addCorrectionItem();
};
deleteItemBtn.onclick = (event) => {
  event.currentTarget.blur();
  releaseTransientInteraction();
  deleteSelectedItem();
};
saveBtn.onclick = (event) => {
  event.currentTarget.blur();
  releaseTransientInteraction();
  saveDirtyTypes().catch(() => {});
};
exportMovementBtn.onclick = (event) => {
  event.currentTarget.blur();
  releaseTransientInteraction();
  const remaining = unresolvedMovementSuggestionCount();
  if (remaining > 0) {
    saveStatus.textContent =
      reviewerCopy("finishBlocked", {count: remaining});
    return;
  }
  waitForMovementSaves()
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
        reviewerCopy("finishMovement", {count: data.count});
    })
    .catch((error) => {
      saveStatus.textContent = reviewerCopy("finishMovementFailed", {error: error.message});
    });
};
helpBtn.onclick = () => {
  helpPanel.open = true;
  helpPanel.scrollIntoView({ behavior: "smooth", block: "start" });
};
movementAfterBtn.onclick = (event) => {
  event.currentTarget.blur();
  addMovementBoundaryAfterSelected();
};

document.getElementById("reviewRestCountsBtn").onclick = (event) => {
  event.currentTarget.blur();
  startRestCountReview();
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
  showBarlineNumbersToggle,
  showLabelsToggle,
  showBaseToggle,
  showManualToggle,
  showMovementToggle,
].forEach((toggle) => {
  toggle.onchange = draw;
});

window.addEventListener("review-language-changed", () => {
  OPS = window.ReviewStrings.operations;
  updateOps(true);
  if (!currentPage) return;
  pageMeta.textContent = reviewerCopy("ui.pageName", {page: displayPageNumber(), name: currentPage.name ? ` · ${currentPage.name}` : ""});
  renderItems();
  updateSelectionMeta();
  updateMovementTargetMeta();
  updateMovementFinishButton();
  updateDirtyStatus();
  renderPageList();
  window.reviewCorrectionState?.refresh().catch(() => {});
  window.reviewApplyResult?.refresh();
});

panModeBtn.onclick = () => {
  releaseTransientInteraction();
  panMode = !panMode;
  if (panMode) setMode("select");
  updatePanControl();
};
fitPageBtn.onclick = () => {
  releaseTransientInteraction();
  resetView();
  draw();
};
previousPageBtn.onclick = () => switchPage(Math.max(0, currentIndex - 1));
nextPageBtn.onclick = () => switchPage(Math.min(pages.length - 1, currentIndex + 1));
previewNumbersBtn.onclick = async () => {
  if (provisionalNumberingVisible) {
    invalidateProvisionalNumbering();
    draw();
    return;
  }
  const requestId = ++numberingPreviewRequestId;
  const revision = provisionalNumberingRevision;
  const isCurrentRequest = () =>
    requestId === numberingPreviewRequestId && revision === provisionalNumberingRevision;
  try {
    await waitForMovementSaves();
    if (!isCurrentRequest()) return;
    await saveDirtyTypes();
    if (!isCurrentRequest()) return;
    saveStatus.textContent = reviewerCopy("ui.previewLoading");
    const response = await fetch("/api/preview_numbering", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!isCurrentRequest()) return;
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const result = await response.json();
    if (!isCurrentRequest()) return;
    provisionalNumbering.clear();
    (result.pages || []).forEach((page) => {
      provisionalNumbering.set(
        String(page.page),
        new Map((page.systems || []).map((system) => [String(system.system), system]))
      );
    });
    provisionalNumberingVisible = true;
    previewNumbersBtn.setAttribute("aria-pressed", "true");
    saveStatus.textContent = reviewerCopy("ui.previewReady");
    draw();
  } catch (error) {
    if (!isCurrentRequest()) return;
    saveStatus.textContent = reviewerCopy("ui.previewFailed", { error: error.message });
  }
};

canvas.addEventListener("mousedown", (event) => {
  if (event.button === 0) canvas.focus({ preventScroll: true });
  const pt = canvasPoint(event);

  if (event.button === 1 || (event.button === 0 && (spaceDown || panMode || event.ctrlKey))) {
    event.preventDefault();
    isPanning = true;
    panStart = pt;
    panOrigin = { ...viewOffset };
    return;
  }
  if (event.button !== 0) return;

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

window.addEventListener("mousemove", (event) => {
  const pt = canvasPoint(event);

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

window.addEventListener("mouseup", (event) => {
  if (isDrawing && drawStart) {
    const end = canvasPoint(event);
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
    const pt = canvasPoint(event);
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
  if (event.key === " ") {
    if (tag === "button" || tag === "a") return;
    event.preventDefault();
    spaceDown = true;
  }
  const scoreFocused = event.target === canvas || tag === "body";
  if (scoreFocused && event.ctrlKey && event.key === "ArrowLeft") {
    event.preventDefault();
    switchPage(Math.max(0, currentIndex - 1));
  }
  if (scoreFocused && event.ctrlKey && event.key === "ArrowRight") {
    event.preventDefault();
    switchPage(Math.min(pages.length - 1, currentIndex + 1));
  }
  if (scoreFocused && !event.ctrlKey && event.key === "ArrowLeft") {
    event.preventDefault();
    navigateScoreTarget(-1);
  }
  if (scoreFocused && !event.ctrlKey && event.key === "ArrowRight") {
    event.preventDefault();
    navigateScoreTarget(1);
  }
  if (event.key === "Delete" || event.key === "Backspace") deleteSelectedItem();
});

window.addEventListener("keyup", (event) => {
  if (event.key === " ") spaceDown = false;
});

window.addEventListener("mouseup", () => {
  isPanning = false;
});

window.addEventListener("blur", releaseTransientInteraction);

window.addEventListener("resize", () => {
  if (!image.complete) return;
  resetView();
  draw();
});

// Header feedback and translated controls can change the available height
// without a window resize. Keep the bitmap aligned without losing the zoom.
if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(() => {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    if (canvas.width === width && canvas.height === height) return;
    canvas.width = width;
    canvas.height = height;
    if (image.complete && image.width) draw();
  }).observe(canvas);
}

updateOps();

fetchJSON("/api/pages").then((data) => {
  pages = data.pages || [];
  if (!pages.length) {
    pageMeta.textContent = window.ReviewStrings.ui.noPages;
    return;
  }
  loadPage();
});

// Optional annotation context stays under details, away from the primary actions.
document.getElementById("helpPanel").appendChild(reasonRow);
