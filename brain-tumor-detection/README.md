# Brain Tumor Detection — end-to-end MRI screening web app

A production-ready reference implementation that classifies brain MRI slices with a **PyTorch convolutional neural network** and serves the model through a **Flask REST API** and a **responsive, healthcare-style web UI**.

Upload (or drag and drop) an MRI image → preview it → click **Analyze scan** → receive a verdict (*tumor detected* / *no tumor detected*), the most likely tumor type, a confidence score, and the full class-probability breakdown. Every result is kept in a searchable history with thumbnails.

> **Medical disclaimer.** This software is for **research and education only**. It is not a medical device, has not been clinically validated, and must not be used for diagnosis or treatment decisions. Always involve a qualified radiologist or clinician.

---

## Contents

1. [Features](#features)
2. [How it works](#how-it-works)
3. [Project structure](#project-structure)
4. [Quick start](#quick-start)
5. [Install dependencies](#1-install-dependencies)
6. [Get the dataset](#2-get-the-dataset)
7. [Train the model](#3-train-the-model)
8. [Evaluate and try the CLI](#4-evaluate-and-try-the-cli)
9. [Run the web application](#5-run-the-web-application)
10. [Using the web app](#6-using-the-web-app)
11. [REST API reference](#rest-api-reference)
12. [Configuration](#configuration)
13. [Testing](#testing)
14. [Security and privacy](#security-and-privacy)
15. [Model details and results](#model-details-and-results)
16. [Limitations and responsible use](#limitations-and-responsible-use)
17. [Troubleshooting](#troubleshooting)

---

## Features

**Machine learning**
- Custom PyTorch CNN (`ml/model.py`, about 1.0 M parameters) trained from scratch; no external pretrained weights required.
- Four classes: `glioma`, `meningioma`, `pituitary` and `no_tumor`. The headline verdict is *tumor* whenever the top class is not `no_tumor`.
- Stratified train/validation split, class-weighted loss for imbalanced data, label smoothing, MRI-oriented augmentation (intensity, resolution and occlusion), OneCycle learning-rate schedule, early stopping on validation accuracy.
- Per-image intensity standardisation, so the network does not rely on scanner brightness or contrast.
- Held-out test evaluation with accuracy, macro-F1, per-class precision/recall/F1 and a confusion matrix, saved next to the model.
- A single preprocessing module (`ml/preprocessing.py`) is used by training, evaluation, the CLI and the server, so there is no train/serve skew.
- Checkpoints are self-describing (class order, input size, preprocessing version, metrics, timestamps), are loaded with `weights_only=True`, and are rejected if their preprocessing version does not match the code.

**Backend (Flask)**
- Application factory (`backend/__init__.py`), typed configuration from `BTD_*` environment variables.
- Layered upload validation: extension allow-list, byte-size limit, **real format detection** with Pillow (the extension is not trusted), decompression-bomb guard, dimension limits, corrupt-file detection, EXIF orientation and 16-bit/alpha normalisation.
- Two-step API: `POST /api/uploads` validates and stores a temporary copy and returns an `upload_id`; `POST /api/predictions` runs inference and persists the result.
- Structured JSON errors (`{"error": {"code", "message", "details"}}`) for every failure mode, including 413/415/422/503.
- Model is loaded once at start-up. If the checkpoint is missing or incompatible the server still starts, reports why in `/api/health`, and returns `503` for predictions.
- Inference is serialised with a lock; the model runs in `inference_mode` on CPU or CUDA.
- Prediction history in SQLite (WAL mode) with JPEG thumbnails; pagination; per-item and bulk delete.
- Uploads expire after an hour and are deleted as soon as they are analyzed. Only derived data is retained.
- Security headers: strict Content-Security-Policy, `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, `no-store` on API responses.

**Frontend (no build step)**
- Vanilla HTML/CSS/JavaScript ES modules served by Flask. No Node toolchain.
- Drag-and-drop and click-to-browse upload zone, keyboard accessible, with client-side pre-validation that mirrors the server.
- Image preview with file name, size and dimensions; one-click removal.
- Loading states with step messages and skeleton placeholders, inline and result-panel error states, and a live model-status indicator.
- Result view: colour-coded verdict, confidence meter, per-class probability bars, low-confidence warning, inference time and model version.
- Responsive layout (two columns on desktop, one column on tablet and mobile), reduced-motion support, visible focus rings, ARIA live regions.
- History panel with thumbnails, open-to-review, delete, refresh, clear-all and "load more".

---

## How it works

```
 Browser (vanilla JS)                       Flask backend (backend/)                ML package (ml/)
 ────────────────────                       ──────────────────────────               ────────────────
 drop / choose MRI  ──POST /api/uploads──▶  validate_upload()  ──────────────────▶  to_rgb()          (ml/preprocessing.py)
                                            (type, size, format, pixels, decode)     │
                                            UploadStore (temp PNG + sidecar)         ▼
 Analyze scan  ──POST /api/predictions──▶   ModelService.predict()  ──────────────▶ Predictor.predict() (ml/inference.py)
                                            ├─ load upload                            resize → normalise → CNN → softmax
                                            ├─ thumbnail (JPEG)                       │
                                            ├─ SQLite history row  ◀──────────────────┘
                                            └─ delete temp upload
 result panel  ◀────── 201 JSON ──────────  { predicted_class, confidence, probabilities, ... }
```

---

## Project structure

```
brain-tumor-detection/
├── backend/                      Flask application
│   ├── __init__.py               create_app(): wiring, error handlers, security headers
│   ├── config.py                 Config dataclass + BTD_* environment variables
│   ├── errors.py                 ApiError (structured HTTP errors)
│   ├── routes.py                 REST endpoints under /api
│   └── services/
│       ├── validation.py         upload validation and decoding
│       ├── uploads.py            temporary upload storage with expiry
│       ├── inference.py          model lifecycle, locking, low-confidence flag
│       └── history.py            SQLite prediction history and thumbnails
├── ml/                           PyTorch code (shared by training and serving)
│   ├── constants.py              class names, folder mapping, image size, normalisation
│   ├── preprocessing.py          to_rgb(), train/eval transforms, preprocess_image()
│   ├── dataset.py                dataset discovery, stratified split, Dataset class
│   ├── model.py                  BrainTumorCNN architecture
│   ├── engine.py                 train/evaluate loops
│   ├── metrics.py                accuracy, macro-F1, confusion matrix (NumPy only)
│   ├── checkpoint.py             save/load checkpoints with metadata
│   ├── inference.py              Predictor: PIL image -> Prediction
│   ├── train.py                  python -m ml.train
│   ├── evaluate.py               python -m ml.evaluate
│   └── predict.py                python -m ml.predict <image>
├── frontend/                     static UI served by Flask
│   ├── index.html
│   ├── css/styles.css
│   ├── js/api.js                 fetch wrapper for the REST API
│   ├── js/ui.js                  DOM helpers and renderers (no innerHTML with data)
│   ├── js/app.js                 controller: upload, predict, history
│   └── favicon.svg
├── tests/                        pytest suite (43 tests, runs in seconds)
├── models/                       trained checkpoint is written here (git-ignored)
├── data/                         put the dataset here (git-ignored)
├── wsgi.py                       entry point for `python wsgi.py` and gunicorn
├── requirements.txt              runtime + training dependencies
├── requirements-dev.txt          adds pytest
├── pytest.ini
└── README.md
```

---

## Quick start

```bash
cd brain-tumor-detection
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Put the dataset in data/raw/ (see "Get the dataset"), then:
python -m ml.train --data-dir data/raw --epochs 25         # writes models/brain_tumor_cnn.pt

python wsgi.py                                             # open http://127.0.0.1:5000
```

---

## 1. Install dependencies

Requirements: **Python 3.10+**, about 2 GB of free disk space for PyTorch, and 4 GB of RAM. A GPU is optional.

```bash
python -m venv .venv
source .venv/bin/activate                 # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt           # add -r requirements-dev.txt to run the tests too
```

**CPU-only machines** (recommended, much smaller download) — install PyTorch from the CPU index first:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

Check the install:

```bash
python -c "import torch, torchvision, flask; print(torch.__version__, torchvision.__version__, flask.__version__)"
```

## 2. Get the dataset

The model is trained on a publicly available **Brain Tumor MRI Dataset** with four classes (glioma, meningioma, pituitary and no tumor), organised into `Training/` and `Testing/` folders. The commonly used Kaggle version is the reference layout. The dataset is **not** included in this repository.

1. Download the dataset from Kaggle (search for *“Brain Tumor MRI Dataset”*). Check its licence and citation requirements before use.
2. Extract it so the folder layout looks exactly like this:

```text
data/raw/
├── Training/
│   ├── glioma_tumor/        *.jpg
│   ├── meningioma_tumor/    *.jpg
│   ├── no_tumor/            *.jpg
│   └── pituitary_tumor/     *.jpg
└── Testing/
    ├── glioma_tumor/        ...
    ├── meningioma_tumor/    ...
    ├── no_tumor/            ...
    └── pituitary_tumor/     ...
```

Any other folder layout can be used as long as it follows this structure: the `Training` folder is split into train and validation sets, and the `Testing` folder is kept as a held-out test set.

## 3. Train the model

```bash
python -m ml.train --data-dir data/raw
```

Common options:

| Option | Default | Purpose |
|---|---|---|
| `--epochs` | `20` | Maximum epochs (early stopping may finish sooner) |
| `--img-size` | `128` | Input resolution. Larger is slower and needs more memory (`160` or `224` for higher detail) |
| `--batch-size` | `32` | Mini-batch size |
| `--lr` | `1e-3` | Peak learning rate (OneCycle schedule) |
| `--patience` | `6` | Early-stopping patience in epochs |
| `--val-fraction` | `0.15` | Share of `Training/` held out for validation |
| `--limit-per-class` | none | Use at most N images per class (quick smoke test) |
| `--device` | `auto` | `auto`, `cpu` or `cuda` |
| `--threads` | torch default | CPU threads for PyTorch |
| `--output` | `models/brain_tumor_cnn.pt` | Checkpoint path |

Quick smoke test (about 1 minute):

```bash
python -m ml.train --data-dir data/raw --epochs 2 --limit-per-class 40 --output models/smoke.pt
```

What training produces:

- `models/brain_tumor_cnn.pt`: the checkpoint the server loads.
- `models/brain_tumor_cnn_metrics.json`: hyper-parameters, per-epoch history, validation and test metrics, and the confusion matrix.
- A console report with test accuracy, per-class precision/recall/F1 and the confusion matrix.

Expected run time: on a 2-core CPU, about **45 seconds per epoch** at 128 px. The 30-epoch run in the results table took about 22 minutes. On a CUDA GPU it takes a few minutes.

## 4. Evaluate and try the CLI

```bash
python -m ml.evaluate --data-dir data/raw                       # metrics on the Testing split
python -m ml.evaluate --data-dir data/raw --json                # machine-readable output
python -m ml.predict path/to/scan.jpg                           # classify one image
```

Example output (illustrative values):

```json
{
  "predicted_class": "glioma",
  "tumor_detected": true,
  "confidence": 0.9731,
  "probabilities": { "glioma": 0.9731, "meningioma": 0.0179, "no_tumor": 0.0021, "pituitary": 0.0069 }
}
```

## 5. Run the web application

Development server (localhost only by default):

```bash
python wsgi.py                          # http://127.0.0.1:5000
BTD_HOST=0.0.0.0 BTD_PORT=8000 python wsgi.py   # listen on all interfaces
```

Production-style server with gunicorn (Linux/macOS). Use **one worker**, so the model is loaded only once, and several threads for concurrent requests:

```bash
gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 --timeout 120 wsgi:app
```

On start-up the server logs whether the model loaded. Check it at any time:

```bash
curl http://127.0.0.1:5000/api/health
# {"status":"ok","model_loaded":true,"model_version":"BrainTumorCNN-128px-<checkpoint digest>"}
```

If `model_loaded` is `false`, train the model first (step 3). The UI shows a *Model not loaded* badge and the reason is available at `/api/model`.

## 6. Using the web app

1. **Upload.** Drag an MRI image onto the dashed area, or click it to browse. Accepted formats: JPEG, PNG and BMP, up to 10 MB.
2. **Preview.** The image appears with its file name, size and dimensions. Use *Remove image* to pick another file.
3. **Analyze.** Click **Analyze scan**. The result panel shows progress while the image is uploaded, validated and analyzed.
4. **Read the result.**
   - The verdict is either *Tumor detected* (with the most likely type) or *No tumor detected*.
   - The **confidence** is the model's probability for its top class.
   - **Class probabilities** show how the model distributed its belief across all four classes.
   - A **low-confidence** warning appears below 60 % confidence (configurable). Treat such results as inconclusive.
5. **History.** Every analysis is stored with a thumbnail. Click an item to review its result again, use the bin icon to delete it, or *Clear all* to wipe the history.

---

## REST API reference

Base URL: `http://<host>:<port>/api`. All responses are JSON, except thumbnails (`image/jpeg`). Errors use one shape:

```json
{ "error": { "code": "UNSUPPORTED_FILE_TYPE", "message": "Unsupported file type '.gif'. ...", "details": { } } }
```

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness and model status |
| `GET` | `/model` | Model metadata: classes, input size, test metrics, load error if any |
| `POST` | `/uploads` | Multipart form, field `file`. Validates and stores a temporary copy. Returns `201` with `upload_id` |
| `POST` | `/predictions` | JSON `{"upload_id": "..."}`. Runs inference and stores the result. Returns `201` |
| `GET` | `/predictions?limit=20&offset=0` | Paginated history, newest first (`limit` 1–100) |
| `GET` | `/predictions/{id}` | One stored prediction |
| `GET` | `/predictions/{id}/thumbnail` | JPEG thumbnail |
| `DELETE` | `/predictions/{id}` | Delete one prediction (`204`) |
| `DELETE` | `/predictions` | Delete all predictions. Returns `{"deleted": n}` |

Example session:

```bash
# 1. Upload
curl -F "file=@scan.jpg" http://127.0.0.1:5000/api/uploads
# {"upload_id":"4f1c…","filename":"scan.jpg","width":512,"height":512,"source_format":"JPEG",...}

# 2. Predict (response abbreviated; values illustrative)
curl -H "Content-Type: application/json" -d '{"upload_id":"4f1c…"}' http://127.0.0.1:5000/api/predictions
# {"id":"9a2e…","predicted_class":"meningioma","predicted_label":"Meningioma","tumor_detected":true,
#  "confidence":0.8812,"low_confidence":false,"probabilities":{...},"model_version":"BrainTumorCNN-128px-…",
#  "inference_ms":6.4,"thumbnail_url":"/api/predictions/9a2e…/thumbnail",...}

# 3. History
curl "http://127.0.0.1:5000/api/predictions?limit=5"
```

Error codes:

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `MISSING_FILE`, `EMPTY_FILE`, `INVALID_REQUEST`, `INVALID_QUERY` | Malformed request |
| 404 | `UPLOAD_NOT_FOUND`, `PREDICTION_NOT_FOUND`, `NOT_FOUND` | Unknown id or route |
| 410 | `UPLOAD_EXPIRED` | Upload older than `BTD_UPLOAD_TTL_SECONDS`. Upload again |
| 413 | `FILE_TOO_LARGE`, `IMAGE_TOO_LARGE` | Over the byte limit or pixel-count limit |
| 415 | `UNSUPPORTED_FILE_TYPE`, `INVALID_IMAGE` | Not a JPEG, PNG or BMP, or not an image |
| 422 | `CORRUPT_IMAGE`, `IMAGE_DIMENSIONS_OUT_OF_RANGE` | Truncated file, or sides outside 32–4096 px |
| 503 | `MODEL_UNAVAILABLE` | Checkpoint missing or invalid. Train the model and restart |
| 500 | `INTERNAL_ERROR` | Unexpected failure. Details are logged server-side only |

---

## Configuration

All settings are environment variables. Defaults work out of the box.

| Variable | Default | Description |
|---|---|---|
| `BTD_MODEL_PATH` | `models/brain_tumor_cnn.pt` | Checkpoint to load |
| `BTD_DATA_DIR` | `instance/` | Where the SQLite database, temporary uploads and thumbnails are stored |
| `BTD_DEVICE` | `cpu` | Inference device: `cpu` or `cuda` |
| `BTD_MAX_UPLOAD_MB` | `10` | Maximum upload size |
| `BTD_LOW_CONFIDENCE_THRESHOLD` | `0.60` | Confidence below which a result is flagged as inconclusive |
| `BTD_UPLOAD_TTL_SECONDS` | `3600` | How long an un-analyzed upload is kept |
| `BTD_LOG_LEVEL` | `INFO` | Python log level |
| `BTD_HOST` / `BTD_PORT` | `127.0.0.1` / `5000` | Only for `python wsgi.py` |

Example:

```bash
export BTD_MODEL_PATH=/srv/models/brain_tumor_cnn.pt
export BTD_DATA_DIR=/srv/brain-tumor/instance
export BTD_MAX_UPLOAD_MB=8
gunicorn -w 1 --threads 4 -b 0.0.0.0:8000 wsgi:app
```

---

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers the following, and runs in a few seconds using a tiny randomly initialised model:

- Preprocessing: greyscale, transparency, 16-bit data, output shape and range.
- Model and checkpoints: forward pass, save/load round-trip, rejection of corrupt or incompatible files.
- Dataset: folder mapping, missing-class detection, stratified split, class weights, metrics.
- Upload validation: each supported format, unsupported and spoofed types, empty, oversized, truncated and out-of-range images, filename sanitisation.
- API: full upload → predict → history → thumbnail → delete flow; pagination bounds; path-traversal ids; JSON errors; 413 limit; 503 when the model is missing; security headers; frontend served.

---

## Security and privacy

- **Input handling:** uploads are never trusted by extension. Each file is probed with Pillow, its real format checked, its pixel count and dimensions bounded, and it is decoded into a fresh RGB image. Filenames are reduced to their base name and length-limited.
- **No path injection:** upload and prediction ids must be 32-character hex strings before they are used in any file path.
- **Minimal retention:** the full-resolution upload is deleted after analysis, and un-analyzed uploads expire. The history keeps a small JPEG thumbnail, the result, and a SHA-256 of the original file, which is useful for audit without storing the original.
- **Model loading:** checkpoints are loaded with `weights_only=True`, so arbitrary pickled code is not executed.
- **Browser hardening:** a strict Content-Security-Policy (no inline scripts or third-party resources), `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, and `Cache-Control: no-store` on API responses.
- **Logs:** log lines contain prediction ids and classes, not file names or image content.
- **Deployment:** this app has **no authentication**. Place it behind your identity provider or reverse proxy (for example nginx with TLS and access control) before exposing it beyond a trusted network. Medical images may be protected health information under HIPAA, GDPR or local law. Confirm your obligations before collecting real patient data.

---

## Model details and results

| Item | Value |
|---|---|
| Architecture | `BrainTumorCNN`: strided 3×3 stem (32 channels), three conv–BN–ReLU–maxpool stages (64/128/256 channels), one refinement conv (256), global average pooling, dropout, 128-unit dense layer, 4-way output |
| Parameters | about 1.0 M |
| Input | RGB, resized to 128 × 128 (configurable), then standardised per image (zero mean, unit variance) |
| Loss | Cross-entropy with inverse-frequency class weights and label smoothing 0.05 |
| Optimiser | AdamW, weight decay 1e-4, OneCycle schedule with peak LR 1e-3 |
| Augmentation (training only) | Random resolution drop (p = 0.5, down to 35 % and back), horizontal flip, ±8° rotation, ±5 % translation, 0.9–1.1 scale, brightness/contrast ±30 %, random erasing (p = 0.25) |
| Split | 85 / 15 stratified train/validation from `Training/`; `Testing/` is used only for the final report |

**Measured results** (produced by the training run; the full report is in `models/brain_tumor_cnn_metrics.json`):

Held-out evaluation on the `Testing/` split (377 images, never used for training or model selection). Two training runs were made:

| Run | Preprocessing | Best validation accuracy (random 15 % of `Training/`) | **Test accuracy** | **Test macro-F1** |
|---|---|:-:|:-:|:-:|
| v1 | fixed mean/std, lighter augmentation, 25 epochs | 93.7 % | 67.9 % | 0.631 |
| **v2 (shipped)** | per-image standardisation, resolution + erasing augmentation, 30 epochs | 94.0 % | **64.7 %** | **0.608** |

v2 per-class results on the test split (the shipped `models/brain_tumor_cnn.pt`):

| Class | Precision | Recall | F1 | Support |
|---|:-:|:-:|:-:|:-:|
| Glioma | 0.818 | 0.314 | 0.454 | 86 |
| Meningioma | 0.669 | 0.798 | 0.728 | 114 |
| No tumor | 0.552 | 0.923 | 0.691 | 104 |
| Pituitary | 0.882 | 0.411 | 0.561 | 73 |

Confusion matrix (rows = true class, columns = predicted):

| true \ predicted | Glioma | Meningioma | No tumor | Pituitary |
|---|:-:|:-:|:-:|:-:|
| Glioma | 27 | 24 | 34 | 1 |
| Meningioma | 0 | 91 | 20 | 3 |
| No tumor | 6 | 2 | 96 | 0 |
| Pituitary | 0 | 19 | 24 | 30 |

**Read these numbers carefully.** The random validation split is drawn from the same images as training, so it overestimates performance (see the limitations below). The test split is a better guide, and it shows the model is **not reliable enough for real screening**. In particular, it misses many gliomas and pituitary tumours. The validation-to-test gap most likely comes from a difference between the two folders, documented below. Treat the shipped checkpoint as a working demonstration of the full pipeline, not as a validated classifier.

Reproduce: `python -m ml.train --data-dir data/raw --epochs 30 --patience 10` and `python -m ml.evaluate --data-dir data/raw`. The metrics are written to `models/brain_tumor_cnn_metrics.json`.

---

## Limitations and responsible use

- **Not a diagnostic device.** Results are estimates from a single 2-D slice. They do not replace imaging review by a clinician, and this tool should not inform clinical decisions.
- **The dataset is heterogeneous, and the test split is out of domain.** A spot-check of random images (during development) shows that the `Training/` and `Testing/` folders differ in modality, plane and image size. The training images are mostly sagittal or axial MRI at 512 px, and many test images are axial CT-like slices, coronal views or 225–236 px images. The model learns the training-source cues, and that does not transfer to the test split. This is the main reason test accuracy (64.7 %) is far below validation accuracy (94 %). Two fixes that targeted intensity and resolution (v1 → v2) did not close the gap, so the problem is the domain itself and not only the normalisation.
- **Validation is optimistic.** The validation split is a random split of slices, and slices from the same patient or scan can land on both sides. The dataset carries no patient identifiers, so a patient-level split was not possible.
- **Distribution shift in general.** Expect degraded performance on other scanners, field strengths, sequences, protocols, or patient populations, and do not assume that the training distribution represents your data. Images of other body parts or non-MRI pictures will still receive a prediction. The low-confidence flag helps, but it is not a reliable out-of-distribution detector. Add one, and validate on a prospective, patient-disjoint dataset from your own site before any real-world use.
- **Class-specific behaviour.** Gliomas are most often predicted as `no_tumor` on the test split, and pituitary tumours as `meningioma` or `no_tumor` (see the confusion matrix above). Do not rely on any single class without re-checking it on your own data.
- **Dataset provenance.** Check the dataset licence and citation requirements yourself. The images are not redistributed by this repository.
- **Training from scratch.** The model does not use ImageNet pretraining, because pretrained weights were not available in the development environment. Transfer learning from a pretrained backbone, a larger or more uniform dataset, patient-level splits, and resolution sweeps are the most likely routes to better test accuracy. Training on `Training/` and `Testing/` together would improve generalisation to the test-style images, but it would then no longer give an independent estimate, so keep a separate external set for evaluation.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Model checkpoint not found` at start-up | Run `python -m ml.train --data-dir data/raw`, or set `BTD_MODEL_PATH` to an existing checkpoint |
| `Expected folder '.../Training' does not exist` | Check the layout in [Get the dataset](#2-get-the-dataset) |
| `torch` install is very large (CUDA wheels) | Use the CPU index command in [Install dependencies](#1-install-dependencies) |
| Upload rejected with 415 | Use JPEG, PNG or BMP. Converting DICOM or NIfTI slices to PNG first is required |
| Upload rejected with 413 | Reduce the file size, or raise `BTD_MAX_UPLOAD_MB` |
| Browser shows *Server offline* | Make sure the server is running and you are on the same host and port |
| Training is slow | Use `--img-size 96` or `--limit-per-class`, or run on a GPU with `--device cuda` |
| `Address already in use` | Use another port: `BTD_PORT=5050 python wsgi.py` |
| Want a fresh history | `rm -rf instance/` while the server is stopped |
| `Checkpoint was trained with preprocessing v1` | The checkpoint predates the current preprocessing. Re-train with `python -m ml.train` |

---

## Licence

Source code: provided for education and research. Dataset: governed by its own licence on the original distribution site.
