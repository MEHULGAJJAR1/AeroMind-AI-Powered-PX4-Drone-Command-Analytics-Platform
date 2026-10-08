"""WSGI entry point for production servers (gunicorn / uWSGI).

    gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 wsgi:app
"""

from app.factory import create_app

app = create_app()
