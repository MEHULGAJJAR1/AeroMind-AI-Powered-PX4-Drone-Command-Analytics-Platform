"""Entry point.

Development:  python wsgi.py            (http://localhost:5000)
Production:   gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 wsgi:app

One worker process keeps the model in memory once; threads serve concurrent
requests (inference itself is serialised by a lock).
"""

import os

from backend import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("BTD_HOST", "127.0.0.1"),
        port=int(os.environ.get("BTD_PORT", "5000")),
        debug=False,
        threaded=True,
    )
