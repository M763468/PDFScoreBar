/**
 * main.js
 * Handles the visualization of barline overlays.
 */

// Wait for the entire window (including images) to fully load
// before running our logic. This ensures accurate dimensions if needed later.
// Global reference to the image and container
let imgElement = null;
let containerElement = null;

window.onload = function () {
    console.log("Window loaded. Initializing visualization...");

    imgElement = document.getElementById("score-image");
    containerElement = document.getElementById("image-container");

    if (!imgElement || !containerElement) {
        console.error("Could not find image container or image element!");
        return;
    }

    // Initial Render
    renderOverlays();

    // Re-render on window resize to maintain alignment
    window.addEventListener('resize', () => {
        renderOverlays();
    });

    // Also attach save button listener
    setupSaveButton();
};

/**
 * Renders (or re-renders) the overlay boxes based on current image scale.
 */
function renderOverlays() {
    // 1. Clear existing boxes to avoid duplicates on resize
    //    (We keep the image, just remove .barline-box elements)
    const existingBoxes = containerElement.querySelectorAll('.barline-box');
    existingBoxes.forEach(box => box.remove());

    // 2. Calculate Scale Factors
    //    Natural: Real pixel size of the PNG
    //    Client:  Pixels currently displayed in browser
    const naturalWidth = imgElement.naturalWidth;
    const naturalHeight = imgElement.naturalHeight;
    const clientWidth = imgElement.clientWidth;
    const clientHeight = imgElement.clientHeight;

    // Guard against division by zero if image hasn't loaded yet
    if (naturalWidth === 0 || naturalHeight === 0) {
        console.warn("Image natural size is 0. Waiting for load...");
        return;
    }

    const scaleX = clientWidth / naturalWidth;
    const scaleY = clientHeight / naturalHeight;

    console.log(`Scaling: Nat=${naturalWidth}x${naturalHeight}, Client=${clientWidth}x${clientHeight}, Scale=${scaleX.toFixed(3)},${scaleY.toFixed(3)}`);

    // 3. Render each barline with scaling
    BARLINES.forEach(function (barline, index) {
        createOverlayBox(barline, index, scaleX, scaleY);
    });
}

/**
 * Creates a single overlay div with scaled coordinates.
 */
/**
 * Creates a single overlay div with scaled coordinates.
 */
function createOverlayBox(barline, index, scaleX, scaleY) {
    // FIX: Use 'orig_bbox' instead of 'pred_bbox'.
    // 'pred_bbox' is in the resized model input space (approx 2.5x larger).
    // 'orig_bbox' is in the original image coordinate space (matching naturalWidth/Height).
    const bbox = barline.orig_bbox; // [x1, y1, x2, y2]
    const x1 = bbox[0];
    const y1 = bbox[1];
    const x2 = bbox[2];
    const y2 = bbox[3];

    // Debugging first element
    if (index === 0) {
        console.log("--- Coordinate Debug (ID 0) ---");
        console.log(`Raw bbox (orig): [${x1}, ${y1}, ${x2}, ${y2}]`);
        console.log(`Scale Factors: X=${scaleX}, Y=${scaleY}`);
        console.log(`Transformed: Left=${x1 * scaleX}, Top=${y1 * scaleY}`);
    }

    // Apply Scaling
    const left = x1 * scaleX;
    const top = y1 * scaleY;
    const width = (x2 - x1) * scaleX;
    const height = (y2 - y1) * scaleY;

    // Create Element
    const box = document.createElement("div");
    box.classList.add("barline-box");
    box.id = "barline-" + index;
    box.setAttribute('data-pred-id', index);

    // Apply Styles
    box.style.left = left + "px";
    box.style.top = top + "px";
    box.style.width = width + "px";
    box.style.height = height + "px";
    box.title = `ID: ${index}`;

    // Restore "ignored" state if previously marked?
    // For this simple version, we lose state on resize unless we track it.
    // OPTIONAL IMPROVEMENT: Check a global set of ignored IDs here.
    // For now, let's just make sure click toggling works.

    box.addEventListener('click', function () {
        this.classList.toggle('ignored');
    });

    containerElement.appendChild(box);
}

function setupSaveButton() {
    const saveBtn = document.getElementById("save-button");
    if (!saveBtn) return;

    saveBtn.addEventListener('click', function () {
        saveDecisions();
    });
}

/**
 * Collects all ignored barline IDs and sends them to the server.
 */
function saveDecisions() {
    // 1. Find all elements that have both 'barline-box' and 'ignored' classes.
    const ignoredElements = document.querySelectorAll('.barline-box.ignored');

    // 2. Extract the IDs from the data attribute.
    const ignoredIds = [];
    ignoredElements.forEach(function (el) {
        // We parse it as an integer just to be clean
        const id = parseInt(el.getAttribute('data-pred-id'));
        if (!isNaN(id)) {
            ignoredIds.push(id);
        }
    });

    console.log("Saving " + ignoredIds.length + " ignored items:", ignoredIds);

    // 3. Send to the backend.
    fetch('/save_decisions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ignored_ids: ignoredIds })
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok') {
                alert("Success! Saved " + data.count + " ignored barlines.");
            } else {
                alert("Error saving: " + data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert("Network error occurred while saving.");
        });
}
