let items = [];
let currentIndex = 0;
let currentItem = null;
let currentTemplate = null;
let currentStatus = "unchanged";
let rawBBox = null; // [x1,y1,x2,y2] in x4 coords
let displayScale = 0.5;

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const itemList = document.getElementById("itemList");
const itemMeta = document.getElementById("itemMeta");
const saveStatus = document.getElementById("saveStatus");
const showGreen = document.getElementById("showGreen");
const scaleSelect = document.getElementById("scaleSelect");
const debugToggle = document.getElementById("debugToggle");
const debugPanel = document.getElementById("debugPanel");
const debugCoords = document.getElementById("debugCoords");
const debugBbox = document.getElementById("debugBbox");
const debugLog = document.getElementById("debugLog");

const statusButtons = {
  unchanged: document.getElementById("statusUnchanged"),
  edited: document.getElementById("statusEdited"),
  invalid: document.getElementById("statusInvalid"),
};

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const saveBtn = document.getElementById("saveBtn");

const HANDLE_SIZE = 8;
let image = new Image();
let dragMode = null; // "move" or "resize"
let dragHandle = null; // 0..3 corner
let dragOffset = { x: 0, y: 0 };

function fetchJSON(url) {
  return fetch(url).then((r) => r.json());
}

function setStatus(status) {
  currentStatus = status;
  Object.entries(statusButtons).forEach(([key, btn]) => {
    btn.classList.toggle("active", key === status);
  });
}

function setScale(value) {
  displayScale = value;
  if (image.complete) {
    canvas.width = Math.round(image.width * displayScale);
    canvas.height = Math.round(image.height * displayScale);
    canvas.style.width = `${canvas.width}px`;
    canvas.style.height = `${canvas.height}px`;
    draw();
  }
}

function renderList() {
  itemList.innerHTML = "";
  items.forEach((item, idx) => {
    const div = document.createElement("div");
    div.className = "list-item" + (idx === currentIndex ? " active" : "");
    div.textContent = `${item.page} / fn_${String(item.gt_index).padStart(3, "0")}`;
    div.onclick = () => {
      currentIndex = idx;
      loadItem();
    };
    itemList.appendChild(div);
  });
}

function loadItem() {
  currentItem = items[currentIndex];
  renderList();
  itemMeta.textContent = `${currentItem.page} / fn_${String(currentItem.gt_index).padStart(3, "0")}`;
  saveStatus.textContent = "";
  image.onload = () => {
    canvas.width = Math.round(image.width * displayScale);
    canvas.height = Math.round(image.height * displayScale);
    canvas.style.width = `${canvas.width}px`;
    canvas.style.height = `${canvas.height}px`;
    draw();
  };
  image.src = `/file?path=${encodeURIComponent(currentItem.image)}`;

  fetchJSON(`/api/template?path=${encodeURIComponent(currentItem.template)}`).then((data) => {
    currentTemplate = data;
    const baseBox = data.edited_bbox || data.scaled_gt_bbox;
    rawBBox = [...baseBox];
    setStatus(data.status || "unchanged");
    draw();
  });
}

function rawToDisplay(box) {
  return box.map((v) => v * displayScale);
}

function displayToRaw(value) {
  return value / displayScale;
}

function draw() {
  if (!image.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  if (!rawBBox) return;

  const [x1, y1, x2, y2] = rawToDisplay(rawBBox);
  ctx.lineWidth = 2;
  ctx.strokeStyle = currentStatus === "invalid" ? "#ff8a80" : "#ff00ff";
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

  if (showGreen.checked && currentTemplate && currentTemplate.nearby_detections) {
    ctx.strokeStyle = "#00ff66";
    ctx.lineWidth = 1;
    currentTemplate.nearby_detections.forEach((det) => {
      const [dx1, dy1, dx2, dy2] = rawToDisplay(det);
      ctx.strokeRect(dx1, dy1, dx2 - dx1, dy2 - dy1);
    });
  }

  if (currentStatus !== "invalid") {
    drawHandles();
  }
  if (debugToggle.checked) {
    updateDebug();
  }
}

function drawHandles() {
  const [x1, y1, x2, y2] = rawToDisplay(rawBBox);
  const handles = [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
  ctx.fillStyle = "#00e5ff";
  const size = HANDLE_SIZE;
  handles.forEach(([hx, hy]) => {
    ctx.fillRect(hx - size / 2, hy - size / 2, size, size);
  });
}

function hitHandle(x, y) {
  const [x1, y1, x2, y2] = rawToDisplay(rawBBox);
  const handles = [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
  const size = HANDLE_SIZE;
  for (let i = 0; i < handles.length; i++) {
    const [hx, hy] = handles[i];
    if (Math.abs(x - hx) <= size && Math.abs(y - hy) <= size) {
      return i;
    }
  }
  return null;
}

function pointInBox(x, y) {
  const [x1, y1, x2, y2] = rawToDisplay(rawBBox);
  return x >= x1 && x <= x2 && y >= y1 && y <= y2;
}

canvas.addEventListener("mousedown", (e) => {
  if (!rawBBox || currentStatus === "invalid") return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const handle = hitHandle(x, y);
  if (handle !== null) {
    dragMode = "resize";
    dragHandle = handle;
    logDebug(`mousedown: handle ${handle}`);
  } else if (pointInBox(x, y)) {
    dragMode = "move";
    const [x1, y1] = rawToDisplay(rawBBox);
    dragOffset = { x: x - x1, y: y - y1 };
    logDebug("mousedown: inside bbox");
  } else {
    logDebug("mousedown: miss");
  }
});

canvas.addEventListener("mousemove", (e) => {
  if (!dragMode) return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  if (dragMode === "move") {
    const width = rawBBox[2] - rawBBox[0];
    const height = rawBBox[3] - rawBBox[1];
    let nx1 = displayToRaw(x - dragOffset.x);
    let ny1 = displayToRaw(y - dragOffset.y);
    rawBBox = [nx1, ny1, nx1 + width, ny1 + height];
  } else if (dragMode === "resize") {
    let [x1, y1, x2, y2] = rawBBox;
    const ix = displayToRaw(x);
    const iy = displayToRaw(y);
    if (dragHandle === 0) {
      x1 = ix; y1 = iy;
    } else if (dragHandle === 1) {
      x2 = ix; y1 = iy;
    } else if (dragHandle === 2) {
      x2 = ix; y2 = iy;
    } else if (dragHandle === 3) {
      x1 = ix; y2 = iy;
    }
    rawBBox = [x1, y1, x2, y2];
  }
  normalizeBBox();
  draw();
});

canvas.addEventListener("mouseup", () => {
  if (dragMode) {
    dragMode = null;
    dragHandle = null;
    if (currentStatus === "unchanged") {
      setStatus("edited");
    }
  }
});

function normalizeBBox() {
  let [x1, y1, x2, y2] = rawBBox;
  if (x2 < x1) [x1, x2] = [x2, x1];
  if (y2 < y1) [y1, y2] = [y2, y1];
  rawBBox = [x1, y1, x2, y2].map((v) => Math.max(0, Math.round(v)));
}

function save() {
  if (!currentItem || !rawBBox) return;
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: currentItem.template,
      status: currentStatus,
      edited_bbox: rawBBox,
    }),
  }).then(() => {
    saveStatus.textContent = "Saved";
  });
}

prevBtn.onclick = () => {
  currentIndex = Math.max(0, currentIndex - 1);
  loadItem();
};

nextBtn.onclick = () => {
  currentIndex = Math.min(items.length - 1, currentIndex + 1);
  loadItem();
};

saveBtn.onclick = save;
showGreen.onchange = draw;
scaleSelect.onchange = () => {
  setScale(parseFloat(scaleSelect.value));
};
debugToggle.onchange = () => {
  debugPanel.style.display = debugToggle.checked ? "block" : "none";
  draw();
};

function logDebug(message) {
  if (!debugToggle.checked) return;
  const line = document.createElement("div");
  line.textContent = message;
  debugLog.prepend(line);
  while (debugLog.childElementCount > 12) {
    debugLog.removeChild(debugLog.lastChild);
  }
}

function updateDebug() {
  if (!rawBBox) return;
  const [x1, y1, x2, y2] = rawBBox;
  debugBbox.textContent = `bbox raw=[${x1},${y1},${x2},${y2}] display=[${Math.round(x1 * displayScale)},${Math.round(y1 * displayScale)},${Math.round(x2 * displayScale)},${Math.round(y2 * displayScale)}]`;
}

canvas.addEventListener("mousemove", (e) => {
  if (!debugToggle.checked) return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const rx = Math.round(displayToRaw(x));
  const ry = Math.round(displayToRaw(y));
  debugCoords.textContent = `mouse display=[${Math.round(x)},${Math.round(y)}] raw=[${rx},${ry}]`;
});

statusButtons.unchanged.onclick = () => setStatus("unchanged");
statusButtons.edited.onclick = () => setStatus("edited");
statusButtons.invalid.onclick = () => setStatus("invalid");

window.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") prevBtn.click();
  if (e.key === "ArrowRight") nextBtn.click();
  if (e.key.toLowerCase() === "u") setStatus("unchanged");
  if (e.key.toLowerCase() === "e") setStatus("edited");
  if (e.key.toLowerCase() === "i") setStatus("invalid");
  if (e.key.toLowerCase() === "s") save();
});

fetchJSON("/api/items").then((data) => {
  items = data.items;
  if (!items.length) {
    itemMeta.textContent = "No items found.";
    return;
  }
  renderList();
  setScale(parseFloat(scaleSelect.value));
  loadItem();
});
