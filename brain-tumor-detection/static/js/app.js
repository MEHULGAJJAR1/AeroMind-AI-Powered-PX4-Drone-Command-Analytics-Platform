/* ==========================================================================
   BrainScan AI — frontend logic
   Vanilla JS (no build step). Talks to the Flask JSON API with relative URLs
   so it works behind any proxy/host.
   ========================================================================== */
(() => {
  "use strict";

  const CONFIG = JSON.parse(document.getElementById("btd-config").textContent || "{}");
  const MAX_BYTES = (CONFIG.max_upload_mb || 10) * 1024 * 1024;
  const ALLOWED_EXTENSIONS = new Set((CONFIG.allowed_extensions || []).map((e) => e.toLowerCase()));
  const RING_CIRCUMFERENCE = 2 * Math.PI * 52;

  const el = (id) => document.getElementById(id);
  const dom = {
    modelStatus: el("model-status"),
    modelStatusText: el("model-status-text"),
    themeToggle: el("theme-toggle"),
    dropzone: el("dropzone"),
    fileInput: el("file-input"),
    maxSize: el("max-size"),
    preview: el("preview"),
    previewImage: el("preview-image"),
    removeFile: el("remove-file"),
    metaName: el("meta-name"),
    metaType: el("meta-type"),
    metaDimensions: el("meta-dimensions"),
    metaSize: el("meta-size"),
    showPreprocessed: el("show-preprocessed"),
    predictButton: el("predict-button"),
    clearButton: el("clear-button"),
    loader: el("loader"),
    loaderSteps: el("loader-steps"),
    cancelButton: el("cancel-button"),
    resultCard: el("result"),
    resultTimestamp: el("result-timestamp"),
    resultBadge: el("result-badge"),
    resultTitle: el("result-title"),
    resultExplanation: el("result-explanation"),
    resultUncertain: el("result-uncertain"),
    ringValue: el("ring-value"),
    ring: el("confidence-ring"),
    confidenceValue: el("confidence-value"),
    probabilities: el("probabilities"),
    inputThumb: el("input-thumb"),
    inputDetails: el("input-details"),
    preprocessedThumb: el("preprocessed-thumb"),
    preprocessDetails: el("preprocess-details"),
    inferenceDetails: el("inference-details"),
    downloadReport: el("download-report"),
    newScan: el("new-scan"),
    stats: { total: el("stat-total"), tumor: el("stat-tumor"), rate: el("stat-rate") },
    historyList: el("history-list"),
    loadMore: el("load-more"),
    clearHistory: el("clear-history"),
    modelDetails: el("model-details"),
    toastStack: el("toast-stack"),
  };

  const state = {
    file: null,
    previewUrl: null,
    result: null,
    busy: false,
    controller: null,
    historyOffset: 0,
    historyTotal: 0,
    newIds: new Set(),
  };

  /* ---------------------------------------------------------------- utils */
  const formatBytes = (bytes) => {
    if (bytes === null || bytes === undefined) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatPercent = (value, digits = 1) =>
    value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;

  const timeAgo = (iso) => {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 45) return "just now";
    const units = [
      ["minute", 60],
      ["hour", 3600],
      ["day", 86400],
      ["week", 604800],
    ];
    for (let i = units.length - 1; i >= 0; i -= 1) {
      const [name, size] = units[i];
      if (seconds >= size) {
        const value = Math.round(seconds / size);
        return `${value} ${name}${value > 1 ? "s" : ""} ago`;
      }
    }
    return `${seconds}s ago`;
  };

  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  const labelName = (label) => (label === "tumor" ? "Tumor" : label === "no_tumor" ? "No tumor" : String(label || "—"));

  const detailRow = (key, value) =>
    `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value ?? "—")}</dd></div>`;

  const toast = (title, body = "", kind = "info", timeout = 5200) => {
    const node = document.createElement("div");
    node.className = `toast toast--${kind}`;
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.innerHTML = `<div><div class="toast__title">${escapeHtml(title)}</div>${
      body ? `<div class="toast__body">${escapeHtml(body)}</div>` : ""
    }</div>`;
    dom.toastStack.appendChild(node);
    const close = () => {
      node.classList.add("is-leaving");
      setTimeout(() => node.remove(), 260);
    };
    node.addEventListener("click", close);
    setTimeout(close, timeout);
  };

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      /* non-JSON response (proxy error page, empty body) */
    }
    if (!response.ok) {
      const error = (payload && payload.error) || {};
      const err = new Error(error.message || `Request failed with HTTP ${response.status}`);
      err.code = error.code || `http_${response.status}`;
      err.details = error.details;
      err.status = response.status;
      throw err;
    }
    return payload ? payload.data : null;
  }

  /* ---------------------------------------------------------------- theme */
  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("btd-theme", theme); } catch { /* storage disabled */ }
  };

  const initTheme = () => {
    let saved = null;
    try { saved = localStorage.getItem("btd-theme"); } catch { /* ignore */ }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(saved || (prefersDark ? "dark" : "light"));
    dom.themeToggle.addEventListener("click", () => {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    });
  };

  /* ------------------------------------------------------------ file input */
  const extensionOf = (name) => {
    const index = String(name || "").lastIndexOf(".");
    return index === -1 ? "" : name.slice(index).toLowerCase();
  };

  function validateFile(file) {
    if (!file) return "No file was provided.";
    const extension = extensionOf(file.name);
    if (ALLOWED_EXTENSIONS.size && !ALLOWED_EXTENSIONS.has(extension)) {
      return `Unsupported file type "${extension || "unknown"}". Allowed: ${[...ALLOWED_EXTENSIONS].join(", ")}.`;
    }
    if (file.type && !file.type.startsWith("image/")) {
      return `"${file.type}" is not an image type.`;
    }
    if (file.size === 0) return "The file is empty.";
    if (file.size > MAX_BYTES) {
      return `The file is ${formatBytes(file.size)} — the limit is ${formatBytes(MAX_BYTES)}.`;
    }
    return null;
  }

  function resetPreview() {
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
    state.file = null;
    dom.fileInput.value = "";
    dom.preview.hidden = true;
    dom.dropzone.hidden = false;
    dom.predictButton.disabled = false;
  }

  async function acceptFile(file) {
    const problem = validateFile(file);
    if (problem) {
      toast("File rejected", problem, "error", 7000);
      return;
    }
    resetPreview();
    state.file = file;
    state.previewUrl = URL.createObjectURL(file);
    dom.previewImage.src = state.previewUrl;
    dom.previewImage.alt = `Preview of ${file.name}`;
    dom.metaName.textContent = file.name;
    dom.metaType.textContent = file.type || "image";
    dom.metaSize.textContent = formatBytes(file.size);
    dom.metaDimensions.textContent = "reading…";
    dom.preview.hidden = false;
    dom.dropzone.hidden = true;

    const dimensions = await new Promise((resolve) => {
      const probe = new Image();
      probe.onload = () => resolve({ width: probe.naturalWidth, height: probe.naturalHeight });
      probe.onerror = () => resolve(null);
      probe.src = state.previewUrl;
    });
    dom.metaDimensions.textContent = dimensions
      ? `${dimensions.width} × ${dimensions.height} px`
      : "unreadable";
    if (!dimensions) toast("Could not decode image", "The browser cannot read this file — the server will reject it too.", "error");
    dom.predictButton.focus();
  }

  function bindDropzone() {
    dom.maxSize.textContent = CONFIG.max_upload_mb || 10;

    const openPicker = () => dom.fileInput.click();
    dom.dropzone.addEventListener("click", openPicker);
    dom.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPicker();
      }
    });

    dom.fileInput.addEventListener("change", () => {
      const [file] = dom.fileInput.files || [];
      if (file) acceptFile(file);
    });

    ["dragenter", "dragover"].forEach((type) =>
      dom.dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dom.dropzone.classList.add("is-dragover");
      })
    );
    ["dragleave", "drop"].forEach((type) =>
      dom.dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dom.dropzone.classList.remove("is-dragover");
      })
    );
    dom.dropzone.addEventListener("drop", (event) => {
      const [file] = event.dataTransfer?.files || [];
      if (file) acceptFile(file);
    });

    window.addEventListener("paste", (event) => {
      const items = event.clipboardData?.items || [];
      for (const item of items) {
        if (item.kind === "file" && item.type.startsWith("image/")) {
          const file = item.getAsFile();
          if (file) {
            const named = file.name ? file : new File([file], `pasted-${Date.now()}.png`, { type: file.type });
            acceptFile(named);
            toast("Image pasted", named.name, "info", 3000);
          }
          return;
        }
      }
    });

    dom.removeFile.addEventListener("click", resetPreview);
    dom.clearButton.addEventListener("click", () => {
      resetPreview();
      dom.resultCard.hidden = true;
      state.result = null;
    });
    dom.newScan.addEventListener("click", () => {
      resetPreview();
      dom.resultCard.hidden = true;
      dom.dropzone.focus();
      document.getElementById("analyze").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    dom.cancelButton.addEventListener("click", () => {
      if (state.controller) state.controller.abort();
    });
  }

  /* --------------------------------------------------------------- loading */
  let stepTimers = [];
  const loaderStepNames = ["upload", "preprocess", "inference", "done"];

  function startLoader() {
    stepTimers.forEach(clearTimeout);
    stepTimers = [];
    [...dom.loaderSteps.children].forEach((node) => node.classList.remove("is-active", "is-done"));
    dom.loader.hidden = false;
    dom.preview.hidden = true;
    dom.resultCard.hidden = true;
    setStep(0);
    // Server-side phases are fast; advance the checklist so the wait feels explained.
    stepTimers.push(setTimeout(() => setStep(1), 450));
    stepTimers.push(setTimeout(() => setStep(2), 1100));
  }

  function setStep(index) {
    [...dom.loaderSteps.children].forEach((node, i) => {
      node.classList.toggle("is-done", i < index);
      node.classList.toggle("is-active", i === index);
    });
  }

  function stopLoader() {
    stepTimers.forEach(clearTimeout);
    stepTimers = [];
    dom.loader.hidden = true;
    if (state.file) dom.preview.hidden = false;
  }

  /* -------------------------------------------------------------- predict */
  async function predict() {
    if (!state.file) {
      toast("No image selected", "Choose or drop an MRI scan first.", "error");
      return;
    }
    if (state.busy) return;

    state.busy = true;
    dom.predictButton.disabled = true;
    state.controller = new AbortController();
    startLoader();

    const form = new FormData();
    form.append("image", state.file, state.file.name);
    form.append("include_preprocessed", dom.showPreprocessed.checked ? "1" : "0");
    form.append("save_history", "1");

    try {
      const data = await api("/api/predict", { method: "POST", body: form, signal: state.controller.signal });
      setStep(3);
      state.result = data;
      renderResult(data);
      state.newIds.add(data.history_id);
      await refreshHistory({ reset: true });
      toast(
        data.prediction.is_tumor ? "Tumor detected" : "No tumor detected",
        `Confidence ${formatPercent(data.prediction.confidence)} · ${data.timing.total_ms} ms`,
        data.prediction.is_tumor ? "error" : "success"
      );
    } catch (error) {
      if (error.name === "AbortError") {
        toast("Prediction cancelled", "", "info", 2600);
      } else {
        toast("Prediction failed", error.message, "error", 8000);
      }
    } finally {
      state.busy = false;
      state.controller = null;
      dom.predictButton.disabled = false;
      stopLoader();
    }
  }

  function renderResult(data) {
    const prediction = data.prediction || {};
    const positive = Boolean(prediction.is_tumor);
    const confidence = Number(prediction.confidence || 0);

    dom.resultCard.hidden = false;
    dom.resultTimestamp.textContent = new Date().toLocaleString();
    dom.resultBadge.textContent = positive ? "Tumor suspected" : "No tumor";
    dom.resultBadge.className = `badge badge--${positive ? "positive" : "negative"}`;
    dom.resultTitle.textContent = prediction.display_name || (positive ? "Tumor detected" : "No tumor detected");
    dom.resultExplanation.textContent =
      prediction.recommendation ||
      (positive
        ? "The classifier found patterns consistent with a mass. A radiologist must confirm."
        : "No tumor-like features were found by the classifier.");

    dom.resultUncertain.hidden = !prediction.uncertain;
    dom.ringValue.style.stroke = positive ? "var(--rose-500)" : "var(--emerald-500)";
    dom.ring.setAttribute("aria-label", `Confidence ${formatPercent(confidence, 0)}`);
    dom.confidenceValue.textContent = formatPercent(confidence, 0);
    requestAnimationFrame(() => {
      dom.ringValue.style.strokeDashoffset = String(RING_CIRCUMFERENCE * (1 - confidence));
    });

    const probabilities = prediction.probabilities || {};
    dom.probabilities.innerHTML = Object.entries(probabilities)
      .map(([label, value]) => `
        <div class="prob">
          <span class="prob__name">${escapeHtml(labelName(label))}</span>
          <span class="prob__track"><span class="prob__fill prob__fill--${escapeHtml(label)}" style="width:0"></span></span>
          <span class="prob__value">${formatPercent(value)}</span>
        </div>`)
      .join("");
    requestAnimationFrame(() => {
      [...dom.probabilities.querySelectorAll(".prob")].forEach((row, index) => {
        const values = Object.values(probabilities);
        const fill = row.querySelector(".prob__fill");
        if (fill) fill.style.width = `${(Number(values[index]) * 100).toFixed(2)}%`;
      });
    });

    const image = data.image || {};
    const preprocess = data.preprocess || {};
    const timing = data.timing || {};
    const model = data.model || {};

    dom.inputDetails.innerHTML = [
      detailRow("Name", image.filename),
      detailRow("Dimensions", image.width && image.height ? `${image.width} × ${image.height}` : "—"),
      detailRow("Size", formatBytes(image.size_bytes)),
      detailRow("SHA-256", image.sha256 ? `${String(image.sha256).slice(0, 12)}…` : "—"),
    ].join("");

    dom.preprocessDetails.innerHTML = [
      detailRow("Input size", preprocess.input_size ? `${preprocess.input_size.width}px` : "—"),
      detailRow("Channels", preprocess.channels),
      detailRow("Brain crop", preprocess.brain_extraction ? "yes" : "no"),
      detailRow("Crop box", preprocess.brain_bbox ? preprocess.brain_bbox.join(", ") : "full frame"),
    ].join("");

    dom.inferenceDetails.innerHTML = [
      detailRow("Model", model.name),
      detailRow("Architecture", model.architecture),
      detailRow("Device", model.device),
      detailRow("Preprocess", `${timing.preprocess_ms} ms`),
      detailRow("Inference", `${timing.inference_ms} ms`),
      detailRow("Total", `${timing.total_ms} ms`),
    ].join("");

    if (data.preprocessed_image) {
      dom.preprocessedThumb.src = data.preprocessed_image;
      dom.preprocessedThumb.hidden = false;
    } else {
      dom.preprocessedThumb.hidden = true;
    }
    if (state.previewUrl) {
      dom.inputThumb.src = state.previewUrl;
      dom.inputThumb.hidden = false;
    }

    dom.resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function downloadReport() {
    if (!state.result) return;
    const blob = new Blob([JSON.stringify(state.result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `brainscan-report-${Date.now()}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  /* -------------------------------------------------------------- history */
  const historyRow = (item) => {
    const prediction = item.prediction || {};
    const positive = Boolean(prediction.is_tumor);
    const isNew = state.newIds.has(item.id);
    return `
      <article class="history-item${isNew ? " is-new" : ""}" data-id="${escapeHtml(item.id)}">
        <img class="history-item__thumb" src="${item.thumbnail ? escapeHtml(item.thumbnail) : ""}"
             alt="" ${item.thumbnail ? "" : 'style="visibility:hidden"'} />
        <div class="history-item__body">
          <div class="history-item__title">${escapeHtml(item.filename)}</div>
          <div class="history-item__meta">
            <span class="chip chip--${positive ? "tumor" : "no_tumor"}">${positive ? "Tumor" : "No tumor"}</span>
            <span>${formatPercent(prediction.confidence, 0)}</span>
            <span>${escapeHtml(timeAgo(item.created_at))}</span>
            <span>${item.latency_ms ? `${Math.round(item.latency_ms)} ms` : ""}</span>
          </div>
        </div>
        <div class="history-item__actions">
          <button class="mini-icon" type="button" data-action="delete" aria-label="Delete prediction" title="Delete">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14" />
            </svg>
          </button>
        </div>
      </article>`;
  };

  async function refreshHistory({ reset = false } = {}) {
    if (reset) state.historyOffset = 0;
    let data;
    try {
      data = await api(`/api/predictions?limit=20&offset=${state.historyOffset}`);
    } catch (error) {
      toast("History unavailable", error.message, "error");
      return;
    }

    const items = (data && data.items) || [];
    if (reset) dom.historyList.innerHTML = "";
    if (!items.length && reset) {
      dom.historyList.innerHTML =
        '<p class="empty-state">No predictions yet. Analyze a scan to start building history.</p>';
    } else {
      dom.historyList.insertAdjacentHTML("beforeend", items.map(historyRow).join(""));
    }

    state.historyTotal = data ? data.total : 0;
    state.historyOffset += items.length;
    dom.loadMore.hidden = !(data && data.has_more);
    dom.clearHistory.disabled = state.historyTotal === 0;
    renderStats();
  }

  async function renderStats() {
    try {
      const stats = await api("/api/stats");
      dom.stats.total.textContent = stats.total ?? 0;
      dom.stats.tumor.textContent = stats.tumor_detected ?? 0;
      dom.stats.rate.textContent =
        stats.average_confidence === null || stats.average_confidence === undefined
          ? "—"
          : formatPercent(stats.average_confidence, 0);
    } catch {
      /* stats are decorative — ignore failures */
    }
  }

  function bindHistory() {
    dom.historyList.addEventListener("click", async (event) => {
      const button = event.target.closest('[data-action="delete"]');
      if (!button) return;
      const row = button.closest(".history-item");
      const id = row && row.dataset.id;
      if (!id) return;
      if (!window.confirm("Delete this prediction from history?")) return;
      try {
        await api(`/api/predictions/${encodeURIComponent(id)}`, { method: "DELETE" });
        row.remove();
        state.historyTotal = Math.max(0, state.historyTotal - 1);
        dom.clearHistory.disabled = state.historyTotal === 0;
        renderStats();
        toast("Deleted", "Prediction removed from history.", "success", 2600);
      } catch (error) {
        toast("Delete failed", error.message, "error");
      }
    });

    dom.loadMore.addEventListener("click", () => refreshHistory());

    dom.clearHistory.addEventListener("click", async () => {
      if (!window.confirm("Clear the entire prediction history?")) return;
      try {
        const data = await api("/api/predictions", { method: "DELETE" });
        dom.historyList.innerHTML =
          '<p class="empty-state">No predictions yet. Analyze a scan to start building history.</p>';
        state.historyOffset = 0;
        state.historyTotal = 0;
        dom.loadMore.hidden = true;
        dom.clearHistory.disabled = true;
        renderStats();
        toast("History cleared", `${data && data.deleted ? data.deleted : 0} entries removed.`, "success", 2600);
      } catch (error) {
        toast("Clear failed", error.message, "error");
      }
    });
  }

  /* ----------------------------------------------------------- model card */
  async function refreshModelStatus() {
    let health;
    try {
      health = await api("/api/health");
    } catch (error) {
      dom.modelStatus.className = "pill pill--error";
      dom.modelStatusText.textContent = "API unreachable";
      dom.modelDetails.innerHTML = detailRow("Status", "unreachable");
      toast("Server unreachable", error.message, "error", 8000);
      return;
    }

    const ready = Boolean(health.model_available);
    dom.modelStatus.className = `pill ${ready ? "pill--ok" : "pill--warn"}`;
    dom.modelStatusText.textContent = ready ? "Model ready" : "No model loaded";

    const model = (health.model && health.model.model) || {};
    const input = model.input || {};
    const metrics = model.metrics || {};
    dom.modelDetails.innerHTML = [
      detailRow("Status", ready ? "loaded" : "not loaded"),
      detailRow("Name", model.name || "—"),
      detailRow("Architecture", model.architecture || "—"),
      detailRow("Framework", model.framework || "—"),
      detailRow("Device", model.device || "—"),
      detailRow("Input", input.size ? `${input.size}px · ${input.channels}ch` : "—"),
      detailRow("Classes", (model.class_labels || []).join(", ") || "—"),
      detailRow("Parameters", model.parameters ? Number(model.parameters).toLocaleString() : "—"),
      detailRow("Val accuracy", metrics.val_accuracy !== undefined ? formatPercent(metrics.val_accuracy) : "—"),
      detailRow("Trained", model.trained_at ? new Date(model.trained_at).toLocaleDateString() : "—"),
      detailRow("Checkpoint", model.checkpoint || "—"),
    ].join("");

    if (!ready) {
      toast(
        "No model loaded",
        "Train one: python -m training.train --data-dir <dataset> (or run scripts/train-demo-model.sh), then restart.",
        "error",
        12000
      );
    }
  }

  /* ----------------------------------------------------------------- init */
  function init() {
    initTheme();
    bindDropzone();
    bindHistory();
    dom.predictButton.addEventListener("click", predict);
    dom.downloadReport.addEventListener("click", downloadReport);
    dom.ringValue.style.strokeDasharray = String(RING_CIRCUMFERENCE);
    dom.ringValue.style.strokeDashoffset = String(RING_CIRCUMFERENCE);

    refreshModelStatus();
    refreshHistory({ reset: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
