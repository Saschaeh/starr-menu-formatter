"""Render Restaurant model to self-contained HTML."""

from __future__ import annotations

import os

from jinja2 import Environment, FileSystemLoader

from .models import Restaurant

# Resolve template directory relative to this file
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def render_html(restaurant: Restaurant) -> str:
    """Render a Restaurant model into a complete, self-contained HTML string."""
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=False,
    )
    template = env.get_template("menu_template.html")
    return template.render(restaurant=restaurant)
