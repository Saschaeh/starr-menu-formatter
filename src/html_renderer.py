"""Render Restaurant model to self-contained HTML."""

from __future__ import annotations

import os

from jinja2 import Environment, FileSystemLoader

from .models import Restaurant, Tab

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


def render_tab_html(restaurant: Restaurant, tab: Tab) -> str:
    """Render a single tab as a self-contained HTML fragment for inline preview."""
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=False,
    )
    template = env.get_template("menu_tab_template.html")
    return template.render(
        tab=tab,
        accent_color=restaurant.accent_color,
        accent_light=restaurant.accent_light,
    )
