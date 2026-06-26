/**
 * DocExtract — Frontend Application Logic
 *
 * Manages the UI state machine:
 *   UPLOAD → PROCESSING → RESULTS
 *
 * Communicates with the FastAPI backend for:
 *   - Image upload & OCR processing
 *   - Gemini Vision retry (fallback)
 *   - Excel download
 */

// ── State ────────────────────────────────────────────────────────────────────
let currentJobId = null;
let selectedFile = null;
let cameraStream = null;

// ── DOM Elements ─────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const stateUpload = $("#state-upload");
const stateProcessing = $("#state-processing");
const stateResults = $("#state-results");

const uploadZone = $("#upload-zone");
const fileInput = $("#file-input");
const cameraInput = $("#camera-input");
const btnChooseFile = $("#btn-choose-file");
const btnCamera = $("#btn-camera");
const btnProcess = $("#btn-process");
const imagePreview = $("#image-preview");
const previewImg = $("#preview-img");
const previewInfo = $("#preview-info");
const btnRemovePreview = $("#btn-remove-preview");

const processingStep = $("#processing-step");
const stepUpload = $("#step-upload");
const stepAi = $("#step-ai");
const stepExcel = $("#step-excel");

const resultsTbody = $("#results-tbody");
const badgeType = $("#badge-type");
const badgeLang = $("#badge-lang");
const badgeCount = $("#badge-count");
const retryBanner = $("#retry-banner");
const btnRetry = $("#btn-retry");
const btnDownload = $("#btn-download");
const btnNew = $("#btn-new");

const toastContainer = $("#toast-container");

// ── State Machine ────────────────────────────────────────────────────────────
function showState(state) {
    stateUpload.classList.add("hidden");
    stateProcessing.classList.add("hidden");
    stateResults.classList.add("hidden");

    if (state === "upload") stateUpload.classList.remove("hidden");
    else if (state === "processing") stateProcessing.classList.remove("hidden");
    else if (state === "results") stateResults.classList.remove("hidden");
}

// ── Toast Notifications ─────────────────────────────────────────────────────
function showToast(message, type = "info") {
    const icons = { error: "❌", success: "✅", info: "ℹ️" };
    const toast = document.createElement("div");
    toast.className = `toast toast--${type}`;
    toast.innerHTML = `
        <span class="toast__icon">${icons[type] || icons.info}</span>
        <span class="toast__message">${message}</span>
    `;
    toastContainer.appendChild(toast);

    // Auto-remove after 5s
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(100px)";
        toast.style.transition = "all 0.3s ease-in";
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// ── File Selection ───────────────────────────────────────────────────────────
function handleFileSelected(file) {
    if (!file) return;

    const validTypes = [
        "image/jpeg", "image/png", "image/tiff",
        "image/bmp", "image/webp",
    ];
    if (!validTypes.includes(file.type)) {
        showToast("Unsupported file type. Please upload JPG, PNG, TIFF, BMP, or WebP.", "error");
        return;
    }

    if (file.size > 20 * 1024 * 1024) {
        showToast("File too large. Maximum size is 20 MB.", "error");
        return;
    }

    selectedFile = file;

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
        imagePreview.classList.remove("hidden");
        btnProcess.classList.remove("hidden");
    };
    reader.readAsDataURL(file);

    const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
    previewInfo.textContent = `${file.name} — ${sizeMB} MB`;
}

// File input change
fileInput.addEventListener("change", (e) => {
    handleFileSelected(e.target.files[0]);
});

// Camera input change
cameraInput.addEventListener("change", (e) => {
    handleFileSelected(e.target.files[0]);
});

// Choose file button
btnChooseFile.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
});

// Remove preview
btnRemovePreview.addEventListener("click", (e) => {
    e.stopPropagation();
    selectedFile = null;
    imagePreview.classList.add("hidden");
    btnProcess.classList.add("hidden");
    fileInput.value = "";
});

// ── Drag & Drop ──────────────────────────────────────────────────────────────
uploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadZone.classList.add("drag-over");
});

uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("drag-over");
});

uploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadZone.classList.remove("drag-over");
    if (e.dataTransfer.files.length) {
        handleFileSelected(e.dataTransfer.files[0]);
    }
});

// Click the upload zone itself (but not children buttons)
uploadZone.addEventListener("click", (e) => {
    if (e.target === uploadZone || e.target.classList.contains("upload-zone__icon") ||
        e.target.classList.contains("upload-zone__title") || e.target.classList.contains("upload-zone__desc")) {
        fileInput.click();
    }
});

// ── Camera ───────────────────────────────────────────────────────────────────
btnCamera.addEventListener("click", (e) => {
    e.stopPropagation();
    cameraInput.click();
});

// ── Processing Pipeline ──────────────────────────────────────────────────────
function updateProcessingStep(stepId, text) {
    // Mark all steps
    [stepUpload, stepAi, stepExcel].forEach((s) => {
        if (s) s.classList.remove("active", "done");
    });

    const order = [stepUpload, stepAi, stepExcel];
    const idx = order.indexOf(document.getElementById(stepId));

    for (let i = 0; i < idx; i++) {
        order[i].classList.add("done");
    }
    if (idx >= 0) order[idx].classList.add("active");

    processingStep.textContent = text;
}

btnProcess.addEventListener("click", async () => {
    if (!selectedFile) return;

    showState("processing");
    updateProcessingStep("step-upload", "Uploading image…");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        // Simulate step delays for visual feedback
        await delay(400);
        updateProcessingStep("step-ai", "AI analyzing document…");

        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Upload failed");
        }

        updateProcessingStep("step-excel", "Building Excel file…");
        await delay(500);

        const data = await response.json();
        currentJobId = data.job_id;

        renderResults(data);
        showState("results");
        showToast("Document extracted successfully!", "success");

    } catch (err) {
        showState("upload");
        showToast(err.message || "An error occurred during processing.", "error");
        console.error("Processing error:", err);
    }
});

// ── Render Results ───────────────────────────────────────────────────────────
function renderResults(data) {
    // Badges
    badgeType.textContent = `📋 ${data.document_type.replace(/_/g, " ").toUpperCase()}`;
    badgeLang.textContent = `🌐 ${data.language}`;
    badgeCount.textContent = `📊 ${data.fields.length} fields`;

    // Table
    resultsTbody.innerHTML = "";
    data.fields.forEach((field, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="color: var(--text-muted); font-size: 0.8rem; width: 40px;">${idx + 1}</td>
            <td class="key-cell">${escapeHtml(field.key)}</td>
            <td class="value-cell">${escapeHtml(field.value)}</td>
        `;
        resultsTbody.appendChild(tr);
    });

    // Reset retry banner
    if (data.method === "gemini_vision_fallback") {
        retryBanner.classList.remove("hidden");
    } else {
        retryBanner.classList.add("hidden");
    }
}

// ── Retry (Vision Fallback) ──────────────────────────────────────────────────
btnRetry.addEventListener("click", async () => {
    if (!currentJobId) return;

    btnRetry.disabled = true;
    btnRetry.textContent = "⏳ Retrying with AI Vision…";

    try {
        const response = await fetch(`/api/retry/${currentJobId}`, {
            method: "POST",
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Retry failed");
        }

        const data = await response.json();
        renderResults(data);
        showToast("Re-extracted using Gemini Vision — check the updated results.", "success");

    } catch (err) {
        showToast(err.message || "Vision fallback failed.", "error");
        console.error("Retry error:", err);
    } finally {
        btnRetry.disabled = false;
        btnRetry.textContent = "🔄 Not Right — Retry";
    }
});

// ── Download ─────────────────────────────────────────────────────────────────
btnDownload.addEventListener("click", () => {
    if (!currentJobId) return;
    window.location.href = `/api/download/${currentJobId}`;
});

// ── New Document ─────────────────────────────────────────────────────────────
btnNew.addEventListener("click", () => {
    currentJobId = null;
    selectedFile = null;
    fileInput.value = "";
    imagePreview.classList.add("hidden");
    btnProcess.classList.add("hidden");
    retryBanner.classList.add("hidden");
    showState("upload");
});

// ── Utilities ────────────────────────────────────────────────────────────────
function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
