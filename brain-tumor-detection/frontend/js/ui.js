/**
 * DOM helpers and view renderers. Only `textContent` / attributes receive
 * server data, so nothing from the API can inject markup.
 */

export const CLASS_ORDER = ["glioma", "meningioma", "pituitary", "no_tumor"];
const CLASS_LABELS = {
  glioma: "Glioma",
  meningioma: "Meningioma",
  pituitary: "Pituitary tumor",
  no_tumor: "No tumor",
};

/** Create an element. `attrs` may contain `class`, `dataset`, `on<event>` handlers and plain attributes. */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of [].concat(children)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDateTime(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

export function classLabel(name) {
  return CLASS_LABELS[name] || name;
}

/** Badge describing the headline outcome. */
export function outcomeBadge(prediction) {
  const tumor = prediction.tumor_detected;
  return el("span", { class: `badge ${tumor ? "badge--danger" : "badge--ok"}` }, [
    tumor ? "Tumor detected" : "No tumor detected",
  ]);
}

/** Result panel content for one prediction (fresh or from history). */
export function renderResult(container, prediction) {
  const tumor = prediction.tumor_detected;
  const confidence = prediction.confidence;

  const headline = el("div", { class: `verdict verdict--${tumor ? "danger" : "ok"}` }, [
    el("div", { class: "verdict__icon", "aria-hidden": "true" }, [tumor ? "!" : "✓"]),
    el("div", {}, [
      el("p", { class: "verdict__label" }, [tumor ? "Possible tumor detected" : "No tumor detected"]),
      el("p", { class: "verdict__type" }, [
        tumor
          ? `Most likely type: ${prediction.predicted_label || classLabel(prediction.predicted_class)}`
          : "The model found no features consistent with a tumor.",
      ]),
    ]),
  ]);

  const confidenceBlock = el("div", { class: "confidence" }, [
    el("div", { class: "confidence__header" }, [
      el("span", {}, ["Model confidence"]),
      el("strong", { class: "confidence__value" }, [formatPercent(confidence)]),
    ]),
    el("div", {
      class: "meter",
      role: "meter",
      "aria-valuemin": 0,
      "aria-valuemax": 100,
      "aria-valuenow": Math.round(confidence * 100),
      "aria-label": "Model confidence",
    }, [el("div", { class: "meter__fill", style: `width:${(confidence * 100).toFixed(1)}%` })]),
  ]);

  const probabilityRows = CLASS_ORDER.filter((name) => name in (prediction.probabilities || {})).map((name) => {
    const value = prediction.probabilities[name];
    const isTop = name === prediction.predicted_class;
    return el("li", { class: `prob ${isTop ? "prob--top" : ""}` }, [
      el("div", { class: "prob__row" }, [
        el("span", { class: "prob__name" }, [classLabel(name)]),
        el("span", { class: "prob__value" }, [formatPercent(value)]),
      ]),
      el("div", { class: "prob__track", "aria-hidden": "true" }, [
        el("div", { class: "prob__fill", style: `width:${(value * 100).toFixed(1)}%` }),
      ]),
    ]);
  });

  const notices = [];
  if (prediction.low_confidence) {
    notices.push(el("p", { class: "alert alert--warn", role: "note" }, [
      "Low confidence: the model is unsure about this scan. Treat the result as inconclusive and review the image with a specialist.",
    ]));
  }

  const meta = el("dl", { class: "result-meta" }, [
    el("div", {}, [el("dt", {}, ["File"]), el("dd", {}, [prediction.original_filename || "—"])]),
    el("div", {}, [el("dt", {}, ["Analyzed"]), el("dd", {}, [formatDateTime(prediction.created_at)])]),
    el("div", {}, [el("dt", {}, ["Inference"]), el("dd", {}, [
      prediction.inference_ms !== undefined ? `${prediction.inference_ms.toFixed(1)} ms` : "—",
    ])]),
    el("div", {}, [el("dt", {}, ["Model"]), el("dd", { class: "mono" }, [prediction.model_version || "—"])]),
  ]);

  container.replaceChildren(
    el("div", { class: "result__content" }, [
      headline,
      ...notices,
      confidenceBlock,
      el("div", { class: "probabilities" }, [
        el("h4", {}, ["Class probabilities"]),
        el("ul", { class: "prob-list" }, probabilityRows),
      ]),
      meta,
      el("p", { class: "disclaimer" }, [
        prediction.disclaimer ||
          "For research and educational use only. Not a substitute for professional medical diagnosis.",
      ]),
    ]),
  );
}

export function renderResultPlaceholder(container) {
  container.replaceChildren(
    el("div", { class: "empty" }, [
      el("svg", { viewBox: "0 0 24 24", width: 56, height: 56, fill: "none", stroke: "currentColor", "stroke-width": 1.4, "aria-hidden": "true" }, [
        el("path", { d: "M3 12h4l2-6 4 12 2-6h6" }),
      ]),
      el("p", { class: "empty__title" }, ["No result yet"]),
      el("p", { class: "muted" }, ["Upload an MRI scan and select “Analyze scan” to see the prediction."]),
    ]),
  );
}

export function renderResultLoading(container, step) {
  container.replaceChildren(
    el("div", { class: "loading", role: "status" }, [
      el("span", { class: "spinner spinner--large", "aria-hidden": "true" }),
      el("p", { class: "loading__title" }, ["Analyzing scan…"]),
      el("p", { class: "muted", id: "loading-step" }, [step]),
      el("div", { class: "skeleton skeleton--wide" }),
      el("div", { class: "skeleton" }),
      el("div", { class: "skeleton skeleton--short" }),
    ]),
  );
}

export function renderResultError(container, message) {
  container.replaceChildren(
    el("div", { class: "alert alert--error", role: "alert" }, [
      el("p", { class: "alert__title" }, ["Analysis failed"]),
      el("p", {}, [message]),
    ]),
  );
}

export function renderHistoryItem(prediction, { onOpen, onDelete }) {
  const tumor = prediction.tumor_detected;
  return el("li", { class: "history-item" }, [
    el("button", {
      class: "history-item__open",
      type: "button",
      "aria-label": `Show result for ${prediction.original_filename}`,
      onclick: () => onOpen(prediction),
    }, [
      el("img", {
        class: "history-item__thumb",
        src: prediction.thumbnail_url,
        alt: "",
        loading: "lazy",
        width: 64,
        height: 64,
      }),
      el("div", { class: "history-item__body" }, [
        el("p", { class: "history-item__name" }, [prediction.original_filename]),
        el("p", { class: "muted small" }, [formatDateTime(prediction.created_at)]),
      ]),
      el("div", { class: "history-item__result" }, [
        outcomeBadge(prediction),
        el("p", { class: "small" }, [
          `${prediction.predicted_label || classLabel(prediction.predicted_class)} · ${formatPercent(prediction.confidence)}`,
        ]),
        prediction.low_confidence ? el("p", { class: "small warn-text" }, ["Low confidence"]) : null,
      ]),
    ]),
    el("button", {
      class: "icon-btn",
      type: "button",
      title: "Delete this prediction",
      "aria-label": `Delete prediction for ${prediction.original_filename}`,
      onclick: () => onDelete(prediction),
    }, [
      el("svg", { viewBox: "0 0 24 24", width: 18, height: 18, fill: "none", stroke: "currentColor", "stroke-width": 2, "aria-hidden": "true" }, [
        el("path", { d: "M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" }),
      ]),
    ]),
  ]);
}

export function renderHistoryEmpty(container) {
  container.replaceChildren(
    el("p", { class: "empty empty--row muted" }, ["No predictions yet. Completed analyses appear here."]),
  );
}
