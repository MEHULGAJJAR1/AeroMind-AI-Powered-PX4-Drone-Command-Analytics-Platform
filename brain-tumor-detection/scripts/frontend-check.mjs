// Frontend smoke test — drives the REAL UI against a REAL running server.
//
// Loads the actual index.html and app.js served by Flask into jsdom and performs
// the full user flow (select file -> Predict -> read result -> history -> delete),
// hitting the live /api/predict endpoint. Only browser primitives jsdom lacks are
// stubbed (image decoding, object URLs, scrollIntoView, confirm).
//
//   npm install jsdom                                  # once
//   python run.py &                                    # in another terminal
//   node scripts/frontend-check.mjs
//   BASE_URL=http://host:5000 IMAGE=samples/no_tumor_sample_01.png node scripts/frontend-check.mjs
//
// Exit code 0 = every check passed.

import { JSDOM, VirtualConsole } from "jsdom";
import fs from "node:fs";

const BASE = process.env.BASE_URL || "http://127.0.0.1:5000";
const IMAGE = process.env.IMAGE || "samples/tumor_sample_01.png";
const REJECT_IMAGE = process.env.REJECT_IMAGE || "samples/not-an-image.txt";

const html = await (await fetch(`${BASE}/`)).text();
const appJs = await (await fetch(`${BASE}/static/js/app.js`)).text();
const css = await (await fetch(`${BASE}/static/css/app.css`)).text();
const imageBytes = fs.readFileSync(IMAGE);
const rejectBytes = fs.readFileSync(REJECT_IMAGE);

const virtualConsole = new VirtualConsole();
const consoleErrors = [];
virtualConsole.on("jsdomError", (e) => consoleErrors.push(String(e.message)));
virtualConsole.on("error", (...a) => consoleErrors.push(a.join(" ")));

const dom = new JSDOM(html, { url: `${BASE}/`, runScripts: "outside-only", pretendToBeVisual: true, virtualConsole });
const win = dom.window;
const doc = win.document;

// --- browser primitives jsdom does not implement ---------------------------
win.URL.createObjectURL = () => "blob:fake-object-url";
win.URL.revokeObjectURL = () => {};
win.Image = class {
  set src(_value) {
    this.naturalWidth = 320;
    this.naturalHeight = 320;
    setTimeout(() => this.onload && this.onload(), 0);
  }
};
win.Element.prototype.scrollIntoView = () => {};
win.confirm = () => true;
win.alert = () => {};
win.matchMedia = win.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));

// --- fetch bridge: jsdom FormData/Blob -> real node fetch -------------------
const calls = [];
win.fetch = async (url, options = {}) => {
  const path = String(url);
  calls.push(`${options.method || "GET"} ${path.split("?")[0]}`);
  const init = { method: options.method || "GET" };

  if (options.body instanceof win.FormData) {
    const form = new FormData();
    for (const [key, value] of options.body.entries()) {
      if (key === "image") {
        form.append("image", new Blob([Buffer.from(await value.arrayBuffer())], { type: value.type }), value.name);
      } else {
        form.append(key, value);
      }
    }
    init.body = form;
  }
  if (options.signal) init.signal = options.signal;

  const response = await fetch(new URL(path, BASE), init);
  const text = await response.text();
  return {
    ok: response.ok,
    status: response.status,
    headers: { get: (h) => response.headers.get(h) },
    json: async () => JSON.parse(text),
    text: async () => text,
  };
};

win.eval(appJs);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
await wait(700);

// --- assertions --------------------------------------------------------------
const results = [];
const check = (name, condition, detail = "") => results.push({ name, pass: Boolean(condition), detail });

check("CSS served and non-trivial", css.length > 5000, `${css.length} bytes`);
check("health pill reflects /api/health", /Model ready|No model loaded/.test(doc.getElementById("model-status-text").textContent),
  doc.getElementById("model-status-text").textContent);
check("model card populated from /api/model data", doc.getElementById("model-details").textContent.includes("BrainScan"));
check("history fetched on load", calls.some((c) => c === "GET /api/predictions"));

const historyBefore = doc.querySelectorAll(".history-item").length;

// 1. select a valid image
const input = doc.getElementById("file-input");
const file = new win.File([imageBytes], IMAGE.split("/").pop(), { type: "image/png" });
Object.defineProperty(input, "files", { value: [file], configurable: true });
input.dispatchEvent(new win.Event("change", { bubbles: true }));
await wait(300);

check("preview shown", doc.getElementById("preview").hidden === false);
check("dropzone hidden while previewing", doc.getElementById("dropzone").hidden === true);
check("filename rendered", doc.getElementById("meta-name").textContent === IMAGE.split("/").pop(),
  doc.getElementById("meta-name").textContent);
check("dimensions rendered", /\d+ × \d+ px/.test(doc.getElementById("meta-dimensions").textContent),
  doc.getElementById("meta-dimensions").textContent);
check("file size rendered", /\d/.test(doc.getElementById("meta-size").textContent), doc.getElementById("meta-size").textContent);

// 2. predict
doc.getElementById("predict-button").dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
check("loader shown synchronously", doc.getElementById("loader").hidden === false);
check("predict button disabled during request", doc.getElementById("predict-button").disabled === true);
await wait(4000);

check("loader hidden after completion", doc.getElementById("loader").hidden === true);
check("predict button re-enabled", doc.getElementById("predict-button").disabled === false);
check("result card visible", doc.getElementById("result").hidden === false);
check("POST /api/predict was made", calls.includes("POST /api/predict"), calls.join(" | "));

const title = doc.getElementById("result-title").textContent;
check("verdict rendered", /Tumor detected|No tumor detected/.test(title), title);
check("badge rendered", /Tumor suspected|No tumor/.test(doc.getElementById("result-badge").textContent),
  doc.getElementById("result-badge").textContent);
check("confidence percentage rendered", /^\d+%$/.test(doc.getElementById("confidence-value").textContent),
  doc.getElementById("confidence-value").textContent);
check("two probability bars", doc.querySelectorAll(".prob").length === 2);
const widths = [...doc.querySelectorAll(".prob__fill")].map((n) => n.style.width);
check("probability widths set", widths.every((w) => w && w !== "0"), widths.join(","));
check("ring animated", doc.getElementById("ring-value").style.strokeDashoffset !== "",
  doc.getElementById("ring-value").style.strokeDashoffset);
check("preprocessed preview shown", doc.getElementById("preprocessed-thumb").hidden === false &&
  doc.getElementById("preprocessed-thumb").src.startsWith("data:image/png"));
check("inference timing rendered", doc.getElementById("inference-details").textContent.includes("ms"));
check("preprocessing metadata rendered", doc.getElementById("preprocess-details").textContent.includes("Brain crop"));

await wait(700);
const historyAfter = doc.querySelectorAll(".history-item").length;
check("history grew by one", historyAfter === historyBefore + 1, `${historyBefore} -> ${historyAfter}`);
check("history thumbnail rendered",
  Boolean(doc.querySelector(".history-item img")?.src.startsWith("data:image/jpeg")));

// 3. delete the entry we just created
doc.querySelector('[data-action="delete"]').dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
await wait(700);
check("history entry deleted", doc.querySelectorAll(".history-item").length === historyBefore);

// 4. invalid file is rejected in the browser, without a network call
const postsBefore = calls.filter((c) => c.startsWith("POST")).length;
const bad = new win.File([rejectBytes], REJECT_IMAGE.split("/").pop(), { type: "text/plain" });
Object.defineProperty(input, "files", { value: [bad], configurable: true });
input.dispatchEvent(new win.Event("change", { bubbles: true }));
await wait(300);
check("invalid file rejected client-side",
  [...doc.querySelectorAll(".toast")].some((t) => t.textContent.includes("File rejected")));
check("no POST for rejected file", calls.filter((c) => c.startsWith("POST")).length === postsBefore);

check("no jsdom console errors", consoleErrors.length === 0, consoleErrors.join(" | ").slice(0, 300));

// --- report -------------------------------------------------------------------
let failed = 0;
for (const r of results) {
  if (!r.pass) failed += 1;
  console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.detail ? `   [${r.detail}]` : ""}`);
}
console.log(`\n${results.length - failed}/${results.length} frontend checks passed against ${BASE}`);
console.log(`network calls: ${calls.join(" | ")}`);
process.exit(failed === 0 ? 0 : 1);
