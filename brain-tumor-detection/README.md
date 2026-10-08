# 🧠 BrainScan AI — Brain Tumor Detection (End-to-End)

An end-to-end deep-learning web application: upload a brain MRI, and a **PyTorch CNN**
served by a **Flask** API classifies it as *tumor* / *no tumor* with a confidence score,
full preprocessing transparency, prediction history and a modern healthcare-style UI.

> ⚠️ **Not a medical device.** This project is for research and education. It does not
> provide a diagnosis. Every result must be reviewed by a qualified radiologist or physician.

---

## Table of contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Project structure](#project-structure)
4. [Quick start](#quick-start)
5. [Getting a dataset & training](#getting-a-dataset--training)
6. [Using the web application](#using-the-web-application)
7. [REST API reference](#rest-api-reference)
8. [Configuration](#configuration)
9. [How the model works](#how-the-model-works)
10. [Docker / production deployment](#docker--production-deployment)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)

---

## Features

**Backend (Flask)**
- Application-factory pattern, blueprints, centralised JSON error handling with
  machine-readable error codes (`validation_error`, `invalid_image`, `file_too_large`,
  `model_unavailable`, `rate_limited`, …).
- Layered upload validation: extension → MIME type → size → magic bytes → full decode →
  dimension limits → decompression-bomb guard → EXIF orientation.
- Thread-safe singleton `Predictor` with lazy loading, warm-up and hot reload
  (`POST /api/model/reload`). A missing or corrupt checkpoint degrades the service
  (`/api/health` reports `"status": "degraded"`, predictions return **503**) instead of
  crashing the server.
- Preprocessing pipeline with **automatic brain extraction** (Otsu threshold → morphological
  cleanup → largest connected component → padded crop), returned to the client so you can
  see exactly what the model saw.
- SQLite prediction history (stdlib `sqlite3`, WAL mode) with thumbnails, statistics,
  pagination, per-record delete and clear-all; automatic pruning at `BTD_HISTORY_LIMIT`.
- Per-IP sliding-window rate limiting, security headers, request ids (`X-Request-Id`) and
  response timing (`X-Response-Time-Ms`), optional CORS allow-list.

**Frontend (vanilla HTML/CSS/JS — no build step)**
- Drag & drop, file picker **and** clipboard paste (`Ctrl`+`V`), with client-side validation
  that mirrors the server rules.
- Image preview with file metadata, staged loading indicator, cancellable request.
- Animated confidence ring, per-class probability bars, uncertainty warning,
  input-vs-preprocessed comparison, timing breakdown, JSON report download.
- Prediction history with thumbnails, aggregate stats, delete/clear, dark mode,
  responsive layout (320 px → widescreen), keyboard accessible, `aria-live` announcements.

**Model / training**
- Custom 4-block CNN (~1.2 M parameters) or torchvision backbones
  (`resnet18`, `resnet50`, `efficientnet_b0`, optionally ImageNet-pretrained).
- Dataset discovery for both common layouts (`no/yes` **and** `Train/no`, `Train/yes`),
  with folder-name normalisation for the public Kaggle / Br35H naming schemes.
- Stratified split, inverse-frequency class weights, augmentation matched to the serving
  pipeline, cosine/plateau schedulers, AMP on CUDA, early stopping.
- Artifacts: `model.pt`, `metadata.json`, optional `model_scripted.pt` (TorchScript),
  `training_report.json`, `training_curves.png`, `confusion_matrix.png`,
  `classification_report.txt`.
- `training/synthetic.py` generates MRI-like phantoms so you can validate the entire
  pipeline without downloading a dataset.

---

## Architecture

```text
Browser (static HTML/CSS/JS)
   │  multipart/form-data  →  POST /api/predict
   ▼
Flask app factory
   ├─ rate limit ─ upload validation ─ image decode ─┐
   │                                                 ▼
   │                                    preprocessing (brain extraction,
   │                                    resize, normalise → 1×C×H×W tensor)
   │                                                 ▼
   │                                Predictor (PyTorch, eval + no_grad,
   │                                thread-safe, softmax)
   │                                                 ▼
   └─ SQLite history (thumbnail + metrics)  ←  JSON envelope
                                                 ▼
                                        Result card / history UI
```

Training is a separate offline path (`training/`) that writes `data/models/model.pt`,
which the Flask `Predictor` loads at boot.

---

## Project structure

```text
brain-tumor-detection/
├── app/                          # Flask application
│   ├── __init__.py               # package + lazy create_app()
│   ├── factory.py                # app factory: config, logging, CORS, rate limit, blueprints
│   ├── config.py                 # env-driven Config dataclass (+ tiny .env loader)
│   ├── version.py
│   ├── api/
│   │   └── routes.py             # /api/* endpoints
│   ├── core/
│   │   ├── errors.py             # JSON error handlers
│   │   ├── exceptions.py         # ApiError hierarchy
│   │   ├── logging.py            # logging + request id / timing hooks
│   │   ├── ratelimit.py          # sliding-window limiter
│   │   └── responses.py          # {"status": "ok", "data": ...} envelopes
│   ├── ml/
│   │   ├── cnn.py                # BrainTumorCNN + build_model()
│   │   ├── preprocess.py         # decode, brain extraction, tensor pipeline
│   │   └── predictor.py          # checkpoint loading + thread-safe inference
│   └── services/
│       ├── analysis.py           # upload → validate → predict → history
│       ├── history.py            # SQLite history store
│       └── validation.py         # upload validation rules
├── training/
│   ├── dataset.py                # discovery, splitting, augmentation, Dataset
│   ├── train.py                  # CLI training loop + artifacts
│   ├── evaluate.py               # checkpoint evaluation report
│   └── synthetic.py              # MRI phantom generator (pipeline testing)
├── static/                       # css/app.css, js/app.js, img/favicon.svg
├── templates/                    # index.html, 404.html
├── tests/                        # 127 pytest tests (API, model, preprocessing, …)
├── scripts/                      # setup.sh, run-dev.sh, train-demo-model.sh, smoke-test.sh
├── data/                         # runtime: models/, uploads/, history.db (git-ignored)
├── run.py                        # dev entry point
├── wsgi.py                       # gunicorn entry point
├── requirements.txt              # runtime + training deps
├── requirements-prod.txt         # gunicorn
├── Dockerfile / docker-compose.yml
├── .env.example
└── README.md
```

---

## Quick start

### 1. Requirements

- Python **3.10 – 3.13**
- ~2 GB disk for dependencies (CPU-only PyTorch: ~1 GB)
- A trained model in `data/models/` (see step 3)

### 2. Install

```bash
cd brain-tumor-detection

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Or use the helper script:

```bash
./scripts/setup.sh                   # add TORCH_VARIANT=cpu for the smaller CPU-only build
```

<details>
<summary><strong>CPU-only PyTorch</strong> (recommended when you have no NVIDIA GPU)</summary>

The default PyPI `torch` wheel for Linux pulls CUDA runtime packages. For a much smaller
CPU-only install:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```
</details>

### 3. Get a model

**Option A — train on a real dataset** (see [Getting a dataset & training](#getting-a-dataset--training)):

```bash
python -m training.train --data-dir data/brain-tumor --epochs 25
```

**Option B — demo model on synthetic phantoms** (no download, ~5 minutes on CPU).
It validates the whole pipeline but is **not** medically meaningful:

```bash
./scripts/train-demo-model.sh
```

### 4. Run the server

```bash
python run.py                        # or: ./scripts/run-dev.sh
```

Open **http://localhost:5000**. The API health check is at
**http://localhost:5000/api/health**.

### 5. Verify end-to-end

```bash
./scripts/smoke-test.sh              # health → predict → invalid file → history → stats
```

### Production

```bash
pip install -r requirements-prod.txt
gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 wsgi:app
```

---

## Getting a dataset & training

### Dataset layout

Both common layouts are auto-detected:

```text
data/brain-tumor/            data/brain-tumor/
├── no/    *.jpg             ├── Train/
└── yes/   *.jpg             │   ├── no/   *.jpg
                             │   └── yes/  *.jpg
                             └── Test/
                                 ├── no/   *.jpg
                                 └── yes/  *.jpg
```

Folder names are normalised to `no_tumor` / `tumor`:

| maps to `no_tumor` | maps to `tumor` |
| --- | --- |
| `no`, `notumor`, `negative`, `healthy`, `normal`, `0` | `yes`, `tumor`, `tumour`, `positive`, `1`, `glioma`, `meningioma`, `pituitary` |

Suitable public datasets (bring your own — nothing is bundled):
[Kaggle “Brain Tumor MRI Dataset”](https://www.kaggle.com/datasets/navoneel/brain-tumor-mri-dataset),
[Br35H](https://www.kaggle.com/datasets/ahmedhamada0/brain-tumor-detection), or
[Figshare brain MRI](https://figshare.com/articles/dataset/brain_tumor_dataset/1512427).
Extract it so the class folders sit under `data/brain-tumor/`.

### Train

```bash
# sensible defaults (GPU strongly recommended)
python -m training.train --data-dir data/brain-tumor --epochs 25 --batch-size 32

# common variations
python -m training.train --data-dir data/brain-tumor --architecture efficientnet_b0 --pretrained
python -m training.train --data-dir data/brain-tumor --channels 1 --img-size 192 --device cpu
python -m training.train --data-dir data/brain-tumor --monitor val_f1 --patience 8 --export-torchscript

# all options
python -m training.train --help
```

| flag | default | meaning |
| --- | --- | --- |
| `--data-dir` | `data/brain-tumor` | dataset root |
| `--output-dir` | `data/models` | where checkpoints/reports are written |
| `--architecture` | `cnn` | `cnn`, `resnet18`, `resnet50`, `efficientnet_b0` |
| `--pretrained` | off | ImageNet weights (torchvision backbones, needs internet) |
| `--epochs` / `--batch-size` | 25 / 32 | training schedule |
| `--img-size` / `--channels` | 224 / 3 | model input |
| `--lr` / `--weight-decay` | 1e-3 / 1e-4 | AdamW |
| `--val-fraction` | 0.15 | used when the dataset has no explicit test split |
| `--patience` | 6 | early stopping (0 disables) |
| `--monitor` | `val_accuracy` | `val_accuracy`, `val_f1`, `val_loss` |
| `--scheduler` | `cosine` | `cosine`, `plateau`, `none` |
| `--no-augment` / `--no-brain-extraction` / `--no-class-weights` / `--no-amp` | off | ablations |
| `--export-torchscript` | off | also write `model_scripted.pt` |
| `--limit-batches N` | 0 | smoke-test mode (N batches per epoch) |

### Evaluate an existing checkpoint

```bash
python -m training.evaluate --data-dir data/brain-tumor --model-dir data/models
```

### Serve the trained model

Drop the folder in `data/models/` (or point `BTD_MODEL_DIR` at it) and restart the server —
or hot-reload a running server with `POST /api/model/reload`.

---

## Using the web application

1. Open http://localhost:5000. The header pill shows **Model ready** (green) or
   **No model loaded** (amber).
2. Drag an MRI onto the dropzone, click to browse, or paste from the clipboard.
   The preview shows filename, type, dimensions and size; unsupported or oversized files
   are rejected in the browser *and* on the server.
3. Click **Predict**. The staged loader shows upload → preprocessing → inference → report.
4. Read the result: verdict badge, animated confidence ring, per-class probability bars,
   the preprocessed model input next to your original, and the timing breakdown.
   Low-confidence results (< 0.6) display an explicit uncertainty warning.
5. Use **Download JSON report** for the raw payload, and manage **Prediction history**
   on the right (view, delete one, clear all).

---

## REST API reference

Base URL: `http://localhost:5000`. All responses use a uniform envelope:

```jsonc
// success
{ "status": "ok", "data": { /* … */ } }

// error
{ "status": "error", "error": { "code": "invalid_image", "message": "…", "details": { } } }
```

### `GET /api/health`
Liveness + model readiness. `data.status` is `healthy` or `degraded`.

### `GET /api/model`
Loaded model metadata: architecture, parameter count, input spec, class labels,
checkpoint name, validation metrics, provenance. **503** when no model is loaded.

### `POST /api/predict`
`multipart/form-data`:

| field | required | description |
| --- | --- | --- |
| `image` | yes | the MRI file (aliases accepted: `file`, `mri`, `scan`, `upload`) |
| `notes` | no | free text (≤ 500 chars) stored with the history entry |
| `include_preprocessed` | no | `1`/`0` — return the preprocessed input as a base64 PNG (default `1`) |
| `save_history` | no | `1`/`0` — persist to history (default `1`) |

Returns **201** with prediction, probabilities, image metadata, preprocessing metadata,
timing and `history_id`:

```jsonc
{
  "status": "ok",
  "data": {
    "prediction": {
      "label": "tumor",
      "display_name": "Tumor detected",
      "is_tumor": true,
      "confidence": 0.9731,
      "probabilities": { "no_tumor": 0.0269, "tumor": 0.9731 },
      "uncertain": false,
      "recommendation": "Possible tumor — radiologist review recommended"
    },
    "model":    { "name": "BrainScan CNN", "architecture": "cnn", "device": "cpu", "input": { "size": 224, "channels": 3 } },
    "timing":   { "preprocess_ms": 41.2, "inference_ms": 88.7, "total_ms": 129.9 },
    "preprocess": { "original_size": { "width": 512, "height": 512 }, "brain_bbox": [72, 64, 448, 452], "brain_extraction": true },
    "image":    { "filename": "scan.png", "width": 512, "height": 512, "size_bytes": 154321, "sha256": "…" },
    "history_id": "9f1c…",
    "preprocessed_image": "data:image/png;base64,…"
  }
}
```

Example:

```bash
curl -X POST http://localhost:5000/api/predict \
     -F "image=@/path/to/mri.png" -F "notes=baseline scan"
```

### `GET /api/predictions?limit=20&offset=0&thumbnails=1`
Paginated history (newest first) with `total` and `has_more`.

### `GET /api/predictions/<id>` · `DELETE /api/predictions/<id>` · `DELETE /api/predictions`
Single entry, delete one, clear all.

### `GET /api/stats`
`total`, `tumor_detected`, `no_tumor`, `tumor_rate`, `average_confidence`,
`average_latency_ms`, `by_label`, `last_prediction_at`, plus model health.

### `POST /api/model/reload`
Re-read the checkpoint directory (useful after retraining).

### Error codes

| HTTP | code | when |
| --- | --- | --- |
| 400 | `validation_error` | missing/empty field, bad query argument |
| 404 | `not_found` | unknown route or history id |
| 405 | `method_not_allowed` | wrong verb |
| 413 | `file_too_large` | over the upload/request limit |
| 422 | `invalid_image`, `unsupported_file_type`, `unsupported_content_type` | unusable payload |
| 429 | `rate_limited` | too many writes from one IP |
| 500 | `prediction_error`, `internal_error` | inference/unexpected failure |
| 503 | `model_unavailable` | no checkpoint loaded |

---

## Configuration

Copy `.env.example` to `.env` (values in the environment win over the file).

| variable | default | description |
| --- | --- | --- |
| `BTD_ENV` | `development` | `development` / `production` / `testing` |
| `BTD_SECRET_KEY` | random | **set a long random value in production** |
| `BTD_HOST` / `BTD_PORT` | `0.0.0.0` / `5000` | bind address |
| `BTD_DEBUG` | `1` in development | Werkzeug debugger |
| `BTD_CORS_ORIGINS` | empty | comma-separated browser origins |
| `BTD_MODEL_DIR` | `data/models` | checkpoint directory |
| `BTD_DEVICE` | `auto` | `auto` / `cpu` / `cuda` / `mps` |
| `BTD_REQUIRE_MODEL` | `0` | fail fast at boot when no checkpoint exists |
| `BTD_MAX_UPLOAD_MB` | `10` | upload limit |
| `BTD_MIN_IMAGE_DIMENSION` | `32` | shortest side in pixels |
| `BTD_MAX_IMAGE_PIXELS` | `89478485` | decompression-bomb guard |
| `BTD_DATA_DIR` / `BTD_DB_PATH` | `data` / `data/history.db` | storage |
| `BTD_KEEP_UPLOADS` | `1` | store originals + thumbnails |
| `BTD_HISTORY_LIMIT` | `500` | prune older rows (0 = keep all) |
| `BTD_RATE_LIMIT` / `BTD_RATE_WINDOW_SECONDS` | `60` / `60` | writes per IP per window (0 disables) |
| `BTD_LOG_LEVEL` / `BTD_LOG_FILE` | `INFO` / empty | logging |

---

## How the model works

**Architecture** — `BrainTumorCNN`: four `Conv3×3 → BN → ReLU → Conv3×3 → BN → ReLU →
MaxPool → Dropout2d` blocks with widths 32/64/128/256, then global average pooling and a
`Dropout → Linear(256→128) → ReLU → Dropout → Linear(128→2)` head. ~1.2 M parameters, which
trains on a laptop and is small enough to serve on CPU.

**Preprocessing (identical in training and serving)**
1. decode + integrity check (`PIL.Image.verify`), then EXIF orientation,
2. channel normalisation (RGBA is composited onto black, as MRI backgrounds are black),
3. **brain extraction**: Otsu threshold → binary closing → hole filling → largest connected
   component → bounding box padded by 8 %,
4. resize to the model input (Lanczos), scale to `[0, 1]`, normalise per channel
   (`mean=std=0.5` by default, stored in the checkpoint),
5. `HWC → CHW` + batch dimension.

**Inference** — `model.eval()` + `torch.no_grad()` under a lock (Flask is threaded),
softmax over the two logits, confidence = max probability. Results below
`uncertainty_threshold` (0.6) are flagged `uncertain: true`.

**Reproducibility** — seeds are set for `random`, `numpy` and `torch`; the checkpoint records
the full hyper-parameter set, dataset layout, metrics, Python/torch versions and timestamp in
`metadata.json`.

**Checkpoint format** — `model.pt` is a bundle:

```python
{
  "format_version": 1,
  "architecture": {"architecture": "cnn", "in_channels": 3, "num_classes": 2, ...},
  "state_dict": ...,
  "class_labels": ["no_tumor", "tumor"],
  "metadata": {"preprocess": {...}, "metrics": {...}, "dataset": {...}, "trained_at": ...},
}
```

`model_scripted.pt` (TorchScript, from `--export-torchscript`) is preferred when present;
`metadata.json` is an optional sidecar that overrides the embedded metadata.

---

## Docker / production deployment

```bash
docker build -t brainscan-ai .
docker run --rm -p 5000:5000 -v "$PWD/data:/app/data" brainscan-ai

# or
docker compose up --build
```

The image is CPU-only PyTorch + gunicorn, runs as a non-root user, has a `/api/health`
healthcheck and expects the checkpoint in the mounted `data/models`.

**Deployment checklist**
- Set `BTD_ENV=production` and a strong `BTD_SECRET_KEY` (≥ 32 chars).
- Put a reverse proxy (nginx/Traefik) in front for TLS, body-size limits and real client IPs
  (`X-Forwarded-For` is honoured by the rate limiter).
- One gunicorn worker per ~1–2 GB RAM (each worker loads its own copy of the model).
- Persist `data/` (uploads, history DB) on a real volume; the app also runs read-only with
  `BTD_KEEP_UPLOADS=0`.
- For multi-worker rate limiting or shared history, front the app with Redis-backed limiting;
  the SQLite store is fine for a single node.
- Never serve real patient data over plain HTTP, and check your local rules for storing
  medical images.

---

## Testing

```bash
pip install -r requirements.txt      # pytest is included
python -m pytest                     # 127 tests
python -m pytest tests/test_api.py -v
```

Coverage areas: preprocessing (Otsu, brain crop, EXIF, corrupt/truncated/oversized files),
upload validation (extensions, MIME sniffing, renamed executables, path traversal),
model architecture and checkpoint loading (including TorchScript, corrupt bundles,
weight/architecture mismatches, thread safety), history store (CRUD, pruning, stats,
corrupt rows), rate limiter, and the full HTTP API including degraded mode.

The suite writes a tiny random checkpoint into a temp directory, so it needs no trained
model and no dataset.

---

## Troubleshooting

**`503 model_unavailable`** — no checkpoint in `data/models`. Run
`./scripts/train-demo-model.sh` or train on a real dataset, then restart (or
`POST /api/model/reload`).

**Training is slow / out of memory on CPU** — reduce `--img-size` (128 or 96),
`--batch-size`, or `--base-channels`; or use `--device cuda` when available.

**`RuntimeError: CUDA out of memory`** — lower `--batch-size`, or add `--no-amp` off/on,
or train at a smaller `--img-size`.

**`ImportError: torchvision`** — only needed for `--architecture resnet18|resnet50|efficientnet_b0`;
`pip install torchvision` or use the default `cnn`.

**Pretrained weights fail to download** — `--pretrained` needs access to
`download.pytorch.org`; drop the flag to train from scratch.

**Upload rejected but the image looks fine** — check the JSON `error.code`:
`unsupported_file_type` (extension), `unsupported_content_type` (MIME),
`file_too_large` (size), `invalid_image` (corrupt/truncated/too small).

**History is empty after restart** — history lives in `data/history.db`; if you run the app
in Docker without mounting `data/`, it is discarded with the container.

**Port already in use** — `PORT=8080 ./scripts/run-dev.sh` or set `BTD_PORT`.

---

## License & attribution

Provided as-is for research and education. If you use public datasets, respect their
individual licenses and citation requirements. **No output of this software may be used to
make clinical decisions.**
