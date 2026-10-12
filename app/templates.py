"""Jinja2 templates setup."""
from __future__ import annotations

import os

from fastapi.templating import Jinja2Templates

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(_TEMPLATE_DIR, exist_ok=True)
templates = Jinja2Templates(directory=_TEMPLATE_DIR)
