# Sample images

**These are procedurally generated MRI-like phantoms, not real patient scans.**
They are produced by `training/synthetic.py` and exist so you can exercise the
full upload → preprocess → inference → history workflow immediately after
installing, without downloading a medical dataset.

| File | Expected behaviour |
| --- | --- |
| `tumor_sample_01.png` … `03.png` | Phantom containing a mass with surrounding edema — the demo model returns `tumor` (verified: 0.97 / 0.91 / 0.95) |
| `no_tumor_sample_01.png` … `03.png` | Phantom with normal tissue only — the demo model returns `no_tumor` (verified: 0.66 / 0.86 / 0.82) |
| `not-an-image.txt` | Rejected by the **extension** check → HTTP 422 `unsupported_file_type` |
| `fake-scan.png` | Text bytes with a `.png` extension; rejected by **content sniffing** → HTTP 422 `invalid_image` |

## Use them from the UI

Drag any PNG onto the dropzone at http://localhost:5000 and press **Predict**.

## Use them from the API

```bash
curl -X POST http://localhost:5000/api/predict -F "image=@samples/tumor_sample_01.png"

# must fail with 422
curl -i -X POST http://localhost:5000/api/predict -F "image=@samples/not-an-image.txt"
```

## Generate more

```bash
python -c "from training.synthetic import make_phantom; \
make_phantom(320, tumor=True, seed=42).convert('RGB').save('my_sample.png')"

# or a whole dataset of phantoms
python -m training.synthetic --out data/synthetic --per-class 150 --size 192
```

> ⚠️ A model trained on these phantoms validates the *pipeline* only. It carries no
> clinical meaning and must never be used to inform a diagnosis. Train on a real
> dataset (see the main README) for any meaningful evaluation.
