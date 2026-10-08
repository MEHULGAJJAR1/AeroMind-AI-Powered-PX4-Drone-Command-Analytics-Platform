/**
 * Application controller: wires the upload zone, preview, prediction flow,
 * result panel and history together.
 */

import { ApiError, api } from "./api.js";
import {
  el,
  formatBytes,
  renderHistoryEmpty,
  renderHistoryItem,
  renderResult,
  renderResultError,
  renderResultLoading,
  renderResultPlaceholder,
} from "./ui.js";

const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp"];
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/bmp"];
const HISTORY_PAGE_SIZE = 8;
const MAX_UPLOAD_MB = 10;

const $ = (id) => document.getElementById(id);
const state = {
  file: null,
  previewUrl: null,
  busy: false,
  modelReady: false,
  history: { offset: 0, total: 0 },
};

const dom = {
  dropzone: $("dropzone"),
  fileInput: $("file-input"),
  preview: $("preview"),
  previewImage: $("preview-image"),
  metaName: $("meta-name"),
  metaSize: $("meta-size"),
  metaDims: $("meta-dims"),
  removeBtn: $("remove-btn"),
  uploadError: $("upload-error"),
  predictBtn: $("predict-btn"),
  predictLabel: document.querySelector("#predict-btn .btn__label"),
  result: $("result"),
  modelStatus: $("model-status"),
  historyList: $("history-list"),
  historyCount: $("history-count"),
  historyMore: $("history-more"),
  historyRefresh: $("history-refresh"),
  historyClear: $("history-clear"),
  maxSize: $("max-size"),
};

// ---------- validation -------------------------------------------------------

function validateFile(file) {
  const name = file.name.toLowerCase();
  const extOk = ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
  const typeOk = !file.type || ALLOWED_TYPES.includes(file.type);
  if (!extOk || !typeOk) {
    return "Unsupported file type. Please upload a JPEG, PNG or BMP image.";
  }
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `This file is ${formatBytes(file.size)}. The limit is ${MAX_UPLOAD_MB} MB.`;
  }
  return null;
}

function showUploadError(message) {
  dom.uploadError.textContent = message;
  dom.uploadError.hidden = !message;
}

// ---------- selection & preview ---------------------------------------------

function refreshPredictButton() {
  dom.predictBtn.disabled = state.busy || !state.file || !state.modelReady;
}

/** Select a file for analysis. Returns false (and shows the reason) when it is rejected. */
function setFile(file) {
  const problem = validateFile(file);
  if (problem) {
    showUploadError(problem);
    return false;
  }
  showUploadError("");
  clearPreviewUrl();
  state.file = file;
  state.previewUrl = URL.createObjectURL(file);
  dom.previewImage.src = state.previewUrl;
  dom.metaName.textContent = file.name;
  dom.metaSize.textContent = formatBytes(file.size);
  dom.metaDims.textContent = "Reading…";
  dom.preview.hidden = false;
  refreshPredictButton();

  const probe = new Image();
  probe.onload = () => {
    dom.metaDims.textContent = `${probe.naturalWidth} × ${probe.naturalHeight} px`;
  };
  probe.onerror = () => {
    dom.metaDims.textContent = "Unknown";
  };
  probe.src = state.previewUrl;
  return true;
}

function clearPreviewUrl() {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
}

function clearSelection() {
  state.file = null;
  clearPreviewUrl();
  dom.previewImage.removeAttribute("src");
  dom.preview.hidden = true;
  dom.fileInput.value = "";
  refreshPredictButton();
  showUploadError("");
}

function openFilePicker() {
  if (!state.busy) dom.fileInput.click();
}

function wireDropzone() {
  const zone = dom.dropzone;
  zone.addEventListener("click", openFilePicker);
  zone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openFilePicker();
    }
  });
  dom.fileInput.addEventListener("change", () => {
    if (dom.fileInput.files?.[0]) setFile(dom.fileInput.files[0]);
  });

  ["dragenter", "dragover"].forEach((type) =>
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragover");
    }),
  );
  ["dragleave", "dragend"].forEach((type) =>
    zone.addEventListener(type, () => zone.classList.remove("is-dragover")),
  );
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragover");
    const files = event.dataTransfer?.files;
    if (!files || files.length === 0) return;
    const accepted = setFile(files[0]);
    if (accepted && files.length > 1) {
      showUploadError("Only one scan can be analyzed at a time. The first file was used.");
    }
  });

  // Prevent the browser from opening a file dropped outside the zone.
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());
}

// ---------- prediction flow --------------------------------------------------

function setBusy(busy, step = "") {
  state.busy = busy;
  dom.predictBtn.classList.toggle("is-loading", busy);
  refreshPredictButton();
  dom.predictBtn.setAttribute("aria-busy", String(busy));
  dom.predictLabel.textContent = busy ? step || "Analyzing…" : "Analyze scan";
  dom.removeBtn.disabled = busy;
  dom.dropzone.setAttribute("aria-disabled", String(busy));
}

async function analyze() {
  if (!state.file || state.busy) return;
  showUploadError("");
  setBusy(true, "Uploading…");
  renderResultLoading(dom.result, "Uploading and validating the scan…");

  let prediction = null;
  try {
    const upload = await api.uploadScan(state.file);
    setBusy(true, "Running CNN…");
    const stepNode = document.getElementById("loading-step");
    if (stepNode) stepNode.textContent = "Preprocessing the image and running the neural network…";

    prediction = await api.createPrediction(upload.upload_id);
    renderResult(dom.result, prediction);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Unexpected error. Please try again.";
    renderResultError(dom.result, message);
    if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
      showUploadError(message);
    }
  } finally {
    setBusy(false);
  }
  // Refresh history after the button is usable again, so the UI never waits on a secondary request.
  if (prediction) await loadHistory({ reset: true });
}

// ---------- history ----------------------------------------------------------

async function loadHistory({ reset = false } = {}) {
  if (reset) {
    state.history.offset = 0;
    dom.historyList.replaceChildren(
      el("p", { class: "muted empty empty--row", role: "status" }, ["Loading history…"]),
    );
  }
  try {
    const page = await api.listPredictions({ limit: HISTORY_PAGE_SIZE, offset: state.history.offset });
    state.history.total = page.total;
    const items = page.items;

    if (reset) dom.historyList.replaceChildren();
    if (reset && items.length === 0) renderHistoryEmpty(dom.historyList);
    else dom.historyList.append(...items.map(renderHistoryNode));

    state.history.offset += items.length;
    dom.historyCount.textContent = page.total
      ? `Showing ${Math.min(state.history.offset, page.total)} of ${page.total} prediction${page.total === 1 ? "" : "s"}`
      : "";
    dom.historyMore.hidden = state.history.offset >= page.total;
  } catch (error) {
    dom.historyList.replaceChildren(
      el("p", { class: "alert alert--error", role: "alert" }, [
        error instanceof ApiError ? error.message : "Could not load prediction history.",
      ]),
    );
  }
}

function renderHistoryNode(prediction) {
  return renderHistoryItem(prediction, {
    onOpen: (item) => {
      renderResult(dom.result, item);
      dom.result.scrollIntoView({ behavior: "smooth", block: "nearest" });
    },
    onDelete: async (item) => {
      if (!window.confirm(`Delete the prediction for “${item.original_filename}”?`)) return;
      try {
        await api.deletePrediction(item.id);
        await loadHistory({ reset: true });
      } catch (error) {
        window.alert(error instanceof ApiError ? error.message : "Could not delete the prediction.");
      }
    },
  });
}

async function clearHistory() {
  if (!window.confirm("Clear the entire prediction history? This cannot be undone.")) return;
  try {
    await api.clearPredictions();
    await loadHistory({ reset: true });
  } catch (error) {
    window.alert(error instanceof ApiError ? error.message : "Could not clear the history.");
  }
}

// ---------- model status -----------------------------------------------------

async function loadModelStatus() {
  const pill = dom.modelStatus;
  const text = pill.querySelector(".status-pill__text");
  try {
    const health = await api.health();
    state.modelReady = Boolean(health.model_loaded);
    pill.dataset.state = state.modelReady ? "ready" : "unavailable";
    text.textContent = state.modelReady ? "Model ready" : "Model not loaded";
    pill.title = health.model_version || "";
    if (!state.modelReady) {
      showUploadError("The prediction model is not loaded. Train it with `python -m ml.train` and restart the server.");
    }
  } catch (error) {
    state.modelReady = false;
    pill.dataset.state = "offline";
    text.textContent = "Server offline";
    showUploadError(error instanceof ApiError ? error.message : "Server offline.");
  }
  refreshPredictButton();
}

// ---------- boot -------------------------------------------------------------

function init() {
  dom.maxSize.textContent = String(MAX_UPLOAD_MB);
  renderResultPlaceholder(dom.result);
  refreshPredictButton();
  wireDropzone();
  dom.removeBtn.addEventListener("click", clearSelection);
  dom.predictBtn.addEventListener("click", analyze);
  dom.historyRefresh.addEventListener("click", () => loadHistory({ reset: true }));
  dom.historyClear.addEventListener("click", clearHistory);
  dom.historyMore.addEventListener("click", () => loadHistory());
  loadModelStatus();
  loadHistory({ reset: true });
}

init();
