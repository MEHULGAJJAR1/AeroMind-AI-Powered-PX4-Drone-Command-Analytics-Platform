"""Application package — BrainScan AI (Flask + PyTorch)."""

from app.version import __version__

__all__ = ["create_app", "__version__"]


def create_app(*args, **kwargs):
    """Create the Flask app. Imported lazily to keep ``import app`` cheap/cycle-free."""
    from app.factory import create_app as _create_app

    return _create_app(*args, **kwargs)
