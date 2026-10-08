#!/usr/bin/env python3
"""Development entry point.

    python run.py

Production deployments should use a WSGI server instead (see README.md):

    gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app
"""

from __future__ import annotations

import argparse

from app.config import Config
from app.factory import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="BrainScan AI — brain tumor detection server")
    parser.add_argument("--host", default=None, help="Bind address (default: BTD_HOST or 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Port (default: BTD_PORT or 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable the Werkzeug debugger")
    parser.add_argument("--no-model", action="store_true", help="Boot without loading a model")
    args = parser.parse_args()

    config = Config.from_env()
    app = create_app(config, load_model=not args.no_model)

    host = args.host or config.host
    port = args.port or config.port
    debug = args.debug or config.debug

    app.logger.info("Listening on http://%s:%d (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
