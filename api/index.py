"""Vercel entrypoint: serves the FastAPI app as a Python function.

vercel.json rewrites every /api/* request here; FastAPI still sees the original path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401
