"""Uniform JSON response envelopes."""

from __future__ import annotations

from typing import Any

from flask import jsonify


def ok(data: Any = None, **extra: Any):
    """Success envelope: ``{"status": "ok", "data": ...}``."""
    payload: dict[str, Any] = {"status": "ok"}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    response = jsonify(payload)
    response.status_code = 200
    return response


def created(data: Any = None, **extra: Any):
    response = ok(data, **extra)
    response.status_code = 201
    return response


def no_content():
    return ("", 204)
