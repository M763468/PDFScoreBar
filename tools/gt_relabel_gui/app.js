let items = [];
let currentIndex = 0;
let currentItem = null;
let currentTemplate = null;
let currentStatus = "unchanged";
let bbox = null; // [x1,y1,x2,y2] in image coords

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const itemList = document.getElementById("itemList");
const itemMeta = document.getElementById("itemMeta");
const saveStatus = document.getElementById("saveStatus");

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
    canvas.width = image.width;
    canvas.height = image.height;
    draw();
  };
  image.src = `/file?path=${encodeURIComponent(currentItem.image)}`;

  fetchJSON(`/api/template?path=${encodeURIComponent(currentItem.template)}`).then((data) => {
    currentTemplate = data;
    const baseBox = data.edited_bbox || data.scaled_gt_bbox;
    bbox = [...baseBox];
    setStatus(data.status || "unchanged");
    draw();
  });
}

function draw() {
  if (!image.complete) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0);
  if (!bbox) return;

  const [x1, y1, x2, y2] = bbox;
  ctx.lineWidth = 2;
  ctx.strokeStyle = currentStatus === "invalid" ? "#ff8a80" : "#ff00ff";
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

  if (currentStatus !== "invalid") {
    drawHandles();
  }
}

function drawHandles() {
  const [x1, y1, x2, y2] = bbox;
  const handles = [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
  ctx.fillStyle = "#00e5ff";
  handles.forEach(([hx, hy]) => {
    ctx.fillRect(hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
  });
}

function hitHandle(x, y) {
  const [x1, y1, x2, y2] = bbox;
  const handles = [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
  for (let i = 0; i < handles.length; i++) {
    const [hx, hy] = handles[i];
    if (Math.abs(x - hx) <= HANDLE_SIZE && Math.abs(y - hy) <= HANDLE_SIZE) {
      return i;
    }
  }
  return null;
}

function pointInBox(x, y) {
  const [x1, y1, x2, y2] = bbox;
  return x >= x1 && x <= x2 && y >= y1 && y <= y2;
}

canvas.addEventListener("mousedown", (e) => {
  if (!bbox || currentStatus === "invalid") return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const handle = hitHandle(x, y);
  if (handle !== null) {
    dragMode = "resize";
    dragHandle = handle;
  } else if (pointInBox(x, y)) {
    dragMode = "move";
    dragOffset = { x: x - bbox[0], y: y - bbox[1] };
  }
});

canvas.addEventListener("mousemove", (e) => {
  if (!dragMode) return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  if (dragMode === "move") {
    const width = bbox[2] - bbox[0];
    const height = bbox[3] - bbox[1];
    let nx1 = x - dragOffset.x;
    let ny1 = y - dragOffset.y;
    bbox = [nx1, ny1, nx1 + width, ny1 + height];
  } else if (dragMode === "resize") {
    let [x1, y1, x2, y2] = bbox;
    if (dragHandle === 0) {
      x1 = x; y1 = y;
    } else if (dragHandle === 1) {
      x2 = x; y1 = y;
    } else if (dragHandle === 2) {
      x2 = x; y2 = y;
    } else if (dragHandle === 3) {
      x1 = x; y2 = y;
    }
    bbox = [x1, y1, x2, y2];
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
  let [x1, y1, x2, y2] = bbox;
  if (x2 < x1) [x1, x2] = [x2, x1];
  if (y2 < y1) [y1, y2] = [y2, y1];
  bbox = [x1, y1, x2, y2].map((v) => Math.max(0, Math.round(v)));
}

function save() {
  if (!currentItem || !bbox) return;
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: currentItem.template,
      status: currentStatus,
      edited_bbox: bbox,
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
  loadItem();
});
