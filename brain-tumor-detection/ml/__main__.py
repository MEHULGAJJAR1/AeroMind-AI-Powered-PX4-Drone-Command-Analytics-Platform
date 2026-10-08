"""Allow ``python -m ml`` to print the available commands."""

import sys

USAGE = """Usage:
  python -m ml.train     --data-dir data/raw [--epochs 20]   train and save models/brain_tumor_cnn.pt
  python -m ml.evaluate  --data-dir data/raw                 evaluate on the Testing split
  python -m ml.predict   path/to/scan.jpg                    classify one image
"""

if __name__ == "__main__":
    sys.stdout.write(USAGE)
