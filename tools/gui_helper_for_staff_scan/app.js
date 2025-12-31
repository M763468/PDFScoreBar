let pages = [];
let displayScale = 0.25;
let currentPage = null;
let scanLog = [];
let predBands = [];
let offsetX = 0;
let offsetY = 0;
let isPanning = false;
let spaceDown = false;
let panStart = { x: 0, y: 0 };

const pageSelect = document.getElementById("pageSelect");
const rowBandLink = document.getElementById("rowBandLink");
const scaleSelect = document.getElementById("scaleSelect");
const fitWidthBtn = document.getElementById("fitWidthBtn");
const scanSlider = document.getElementById("scanSlider");
const bandHeightInput = document.getElementById("bandHeight");
const inkThresholdInput = document.getElementById("inkThreshold");
const saveScanBtn = document.getElementById("saveScanBtn");
const scanInfo = document.getElementById("scanInfo");

const imageCanvas = document.getElementById("imageCanvas");
const imageCtx = imageCanvas.getContext("2d");
const profileCanvas = document.getElementById("profileCanvas");
const profileCtx = profileCanvas.getContext("2d");
const recordInfo = document.getElementById("recordInfo");
const canvasWrap = document.getElementById("canvasWrap");

const image = new Image();
let lastImagePath = null;

function fetchJSON(url) {
  return fetch(url).then((r) => r.json());
}

function setScale(value) {
  displayScale = value;
  drawImage();
}

function setupEvents() {
  pageSelect.addEventListener("change", () => {
    const page = pages.find((p) => p.name === pageSelect.value);
    if (page) {
      loadPage(page);
    }
  });
  scaleSelect.addEventListener("change", (e) => setScale(parseFloat(e.target.value)));
  fitWidthBtn.addEventListener("click", () => fitToWidth());
  canvasWrap.addEventListener("wheel", handleWheel, { passive: false });
  canvasWrap.addEventListener("mousedown", startPan);
  window.addEventListener("mouseup", stopPan);
  window.addEventListener("mousemove", movePan);
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space") {
      spaceDown = true;
      canvasWrap.classList.add("grab");
    }
  });
  window.addEventListener("keyup", (e) => {
    if (e.code === "Space") {
      spaceDown = false;
      canvasWrap.classList.remove("grab");
      stopPan();
    }
  });
  scanSlider.addEventListener("input", () => {
    drawImage();
    updateScanInfo();
  });
  bandHeightInput.addEventListener("change", () => {
    drawImage();
    updateScanInfo();
  });
  inkThresholdInput.addEventListener("change", () => {
    drawImage();
    updateScanInfo();
  });
  saveScanBtn.addEventListener("click", saveScanLog);
}

function drawImage() {
  if (!image.complete || !image.naturalWidth || !image.naturalHeight) return;
  const width = canvasWrap.clientWidth;
  const height = canvasWrap.clientHeight;
  imageCanvas.width = Math.max(1, width);
  imageCanvas.height = Math.max(1, height);
  imageCtx.setTransform(1, 0, 0, 1, 0, 0);
  imageCtx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
  imageCtx.setTransform(displayScale, 0, 0, displayScale, offsetX, offsetY);
  imageCtx.drawImage(image, 0, 0);
  drawPredBands();
  drawScanBand();
  imageCtx.setTransform(1, 0, 0, 1, 0, 0);
}

function fitToWidth() {
  if (!image.complete || !image.naturalWidth) return;
  const wrap = document.getElementById("canvasWrap");
  const targetWidth = Math.max(100, wrap.clientWidth - 10);
  const scale = targetWidth / image.naturalWidth;
  displayScale = Math.max(0.1, Math.min(2.0, scale));
  const match = Array.from(scaleSelect.options).find((opt) => Math.abs(parseFloat(opt.value) - displayScale) < 0.02);
  if (match) {
    scaleSelect.value = match.value;
  } else {
    scaleSelect.value = displayScale.toFixed(2);
  }
  offsetX = Math.round((wrap.clientWidth - image.naturalWidth * displayScale) / 2);
  offsetY = Math.round((wrap.clientHeight - image.naturalHeight * displayScale) / 2);
  drawImage();
}

function drawScanBand() {
  const bandHeight = Math.max(1, parseInt(bandHeightInput.value, 10) || 1);
  const y = parseInt(scanSlider.value, 10) || 0;
  imageCtx.fillStyle = "rgba(255, 165, 0, 0.35)";
  imageCtx.fillRect(0, y, image.naturalWidth, bandHeight);
  imageCtx.strokeStyle = "#ff6f00";
  imageCtx.lineWidth = 1 / displayScale;
  imageCtx.strokeRect(0, y, image.naturalWidth, bandHeight);
}

function drawImageError(message) {
  imageCanvas.width = 800;
  imageCanvas.height = 400;
  imageCanvas.style.width = "800px";
  imageCanvas.style.height = "400px";
  imageCtx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
  imageCtx.fillStyle = "#1b1b1b";
  imageCtx.fillRect(0, 0, imageCanvas.width, imageCanvas.height);
  imageCtx.fillStyle = "#ff6f00";
  imageCtx.font = "16px Arial";
  imageCtx.fillText("Image load failed.", 20, 40);
  if (message) {
    imageCtx.fillStyle = "#ccc";
    imageCtx.font = "12px Arial";
    imageCtx.fillText(message, 20, 70);
  }
}

function loadImage(path) {
  if (!path) return;
  lastImagePath = path;
  image.onload = () => {
    offsetX = 0;
    offsetY = 0;
    drawImage();
    scanSlider.max = String(Math.max(0, image.naturalHeight - 1));
    scanSlider.value = "0";
    updateScanInfo();
  };
  image.onerror = () => {
    drawImageError(`Failed to load: ${path}`);
  };
  image.src = `/file?path=${encodeURIComponent(path)}`;
}

function drawProfile(record) {
  profileCtx.clearRect(0, 0, profileCanvas.width, profileCanvas.height);
  const profile = record.scan_row_profile || [];
  if (!profile.length) {
    profileCtx.fillStyle = "#333";
    profileCtx.fillText("scan_row_profile not available.", 10, 20);
    return;
  }

  const maxVal = Math.max(...profile, 0.0001);
  const meanVal = record.scan_row_ratio_mean ?? null;
  const maxRatio = record.scan_row_ratio_max ?? null;

  profileCtx.strokeStyle = "#2b78c5";
  profileCtx.lineWidth = 2;
  profileCtx.beginPath();
  profile.forEach((value, idx) => {
    const x = (idx / Math.max(profile.length - 1, 1)) * (profileCanvas.width - 20) + 10;
    const y = profileCanvas.height - 10 - (value / maxVal) * (profileCanvas.height - 20);
    if (idx === 0) {
      profileCtx.moveTo(x, y);
    } else {
      profileCtx.lineTo(x, y);
    }
  });
  profileCtx.stroke();

  profileCtx.strokeStyle = "#ff6f00";
  profileCtx.setLineDash([4, 4]);
  if (meanVal !== null) {
    const y = profileCanvas.height - 10 - (meanVal / maxVal) * (profileCanvas.height - 20);
    profileCtx.beginPath();
    profileCtx.moveTo(10, y);
    profileCtx.lineTo(profileCanvas.width - 10, y);
    profileCtx.stroke();
  }
  if (maxRatio !== null) {
    const y = profileCanvas.height - 10 - (maxRatio / maxVal) * (profileCanvas.height - 20);
    profileCtx.beginPath();
    profileCtx.moveTo(10, y);
    profileCtx.lineTo(profileCanvas.width - 10, y);
    profileCtx.stroke();
  }
  profileCtx.setLineDash([]);

  profileCtx.fillStyle = "#333";
  profileCtx.fillText(`profile max=${maxVal.toFixed(2)}`, 10, 14);
  if (meanVal !== null) {
    profileCtx.fillText(`mean=${meanVal.toFixed(2)}`, 10, 28);
  }
  if (maxRatio !== null) {
    profileCtx.fillText(`row max=${maxRatio.toFixed(2)}`, 10, 42);
  }
}

function updateScanInfo() {
  if (!image.complete || !image.naturalWidth || !image.naturalHeight) return;
  const bandHeight = Math.max(1, parseInt(bandHeightInput.value, 10) || 1);
  scanSlider.max = String(Math.max(0, image.naturalHeight - bandHeight));
  const y = Math.max(0, Math.min(image.naturalHeight - bandHeight, parseInt(scanSlider.value, 10) || 0));
  const threshold = Math.max(0, Math.min(255, parseInt(inkThresholdInput.value, 10) || 0));
  const ratio = computeInkRatio(y, bandHeight, threshold);
  scanInfo.textContent = `y=${y} h=${bandHeight} ink_threshold=${threshold} ratio=${ratio.toFixed(4)}`;
  recordInfo.textContent = JSON.stringify(
    {
      page: currentPage ? currentPage.name : null,
      image_path: lastImagePath,
      y,
      band_height: bandHeight,
      ink_threshold: threshold,
      ratio,
    },
    null,
    2
  );
}

function computeInkRatio(y, bandHeight, threshold) {
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  if (!width || !height) return 0;
  const safeY = Math.max(0, Math.min(height - 1, y));
  const safeH = Math.max(1, Math.min(height - safeY, bandHeight));
  const tempCanvas = document.createElement("canvas");
  tempCanvas.width = width;
  tempCanvas.height = height;
  const tempCtx = tempCanvas.getContext("2d");
  tempCtx.drawImage(image, 0, 0, width, height);
  const imageData = tempCtx.getImageData(0, safeY, width, safeH);
  const data = imageData.data;
  let ink = 0;
  const total = width * safeH;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const gray = 0.299 * r + 0.587 * g + 0.114 * b;
    if (gray < threshold) {
      ink += 1;
    }
  }
  return total > 0 ? ink / total : 0;
}

function saveScanLog() {
  if (!currentPage) return;
  const bandHeight = Math.max(1, parseInt(bandHeightInput.value, 10) || 1);
  const threshold = Math.max(0, Math.min(255, parseInt(inkThresholdInput.value, 10) || 0));
  const y = Math.max(0, Math.min(image.naturalHeight - bandHeight, parseInt(scanSlider.value, 10) || 0));
  const ratio = computeInkRatio(y, bandHeight, threshold);
  const payload = {
    page: currentPage.name,
    image_path: lastImagePath,
    y,
    band_height: bandHeight,
    ink_threshold: threshold,
    ratio,
    timestamp: new Date().toISOString(),
  };
  fetch("/api/save_scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((data) => {
      scanInfo.textContent = `saved to ${data.path} (count=${data.count})`;
      scanLog = data.items || scanLog;
    })
    .catch(() => {
      scanInfo.textContent = "save failed";
    });
}

async function loadPage(page) {
  currentPage = page;
  predBands = [];
  try {
    const debug = await fetchJSON(`/api/debug?path=${encodeURIComponent(page.debug_json)}`);
    if (Array.isArray(debug.records)) {
      const bandSet = new Set();
      debug.records.forEach((rec) => {
        if (rec.pred_band && rec.pred_band.length === 2) {
          bandSet.add(`${rec.pred_band[0]}-${rec.pred_band[1]}`);
        }
      });
      predBands = Array.from(bandSet).map((key) => key.split("-").map((v) => parseInt(v, 10)));
    }
  } catch (err) {
    predBands = [];
  }
  scanLog = [];
  const rowBandUrl = page.row_band_debug
    ? `<a class="small" href="/file?path=${encodeURIComponent(page.row_band_debug)}" target="_blank">open</a>`
    : "-";
  rowBandLink.innerHTML = rowBandUrl;
  const imagePath = page.row_band_debug || page.debug_image;
  if (imagePath) {
    loadImage(imagePath);
  } else {
    drawImageError("No row_band_debug image found.");
  }
  scanSlider.min = "0";
}

async function init() {
  setupEvents();
  const response = await fetchJSON("/api/pages");
  pages = response.pages || [];
  pageSelect.innerHTML = "";
  pages.forEach((page) => {
    const option = document.createElement("option");
    option.value = page.name;
    option.textContent = page.name;
    pageSelect.appendChild(option);
  });
  if (pages.length) {
    pageSelect.value = pages[0].name;
    loadPage(pages[0]);
  } else {
    recordInfo.textContent = [
      "No pages found in run root.",
      `root=${response.root || "unknown"}`,
      `per_page=${response.per_page || "unknown"}`,
    ].join("\n");
    drawImageError("No pages found. Check --root path.");
  }
}

init();

function drawPredBands() {
  if (!predBands.length) return;
  imageCtx.strokeStyle = "rgba(0, 128, 255, 0.8)";
  imageCtx.lineWidth = 1 / displayScale;
  predBands.forEach(([y1, y2]) => {
    imageCtx.beginPath();
    imageCtx.moveTo(0, y1);
    imageCtx.lineTo(image.naturalWidth, y1);
    imageCtx.stroke();
    imageCtx.beginPath();
    imageCtx.moveTo(0, y2);
    imageCtx.lineTo(image.naturalWidth, y2);
    imageCtx.stroke();
  });
}

function handleWheel(e) {
  e.preventDefault();
  if (!image.complete || !image.naturalWidth) return;
  const delta = e.deltaY > 0 ? -0.1 : 0.1;
  const nextScale = Math.max(0.1, Math.min(3.0, displayScale + delta));
  const rect = imageCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const imgX = (mx - offsetX) / displayScale;
  const imgY = (my - offsetY) / displayScale;
  displayScale = nextScale;
  offsetX = mx - imgX * displayScale;
  offsetY = my - imgY * displayScale;
  drawImage();
}

function startPan(e) {
  if (!spaceDown) return;
  isPanning = true;
  panStart = { x: e.clientX - offsetX, y: e.clientY - offsetY };
  canvasWrap.classList.add("grabbing");
}

function movePan(e) {
  if (!isPanning) return;
  offsetX = e.clientX - panStart.x;
  offsetY = e.clientY - panStart.y;
  drawImage();
}

function stopPan() {
  if (!isPanning) return;
  isPanning = false;
  canvasWrap.classList.remove("grabbing");
}
