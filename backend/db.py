"""Compatibility entry point for database helpers.

The prototype started with `database.py`. Future phases can move toward `db.py`
without forcing existing imports to change immediately.
"""

from .database import *  # noqa: F401,F403
