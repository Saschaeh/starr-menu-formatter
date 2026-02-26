"""Restaurant metadata and auto-detection."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RestaurantConfig:
    name: str
    slug: str
    accent_color: str
    accent_light: str


# Known Starr Restaurant configs
RESTAURANTS: dict[str, RestaurantConfig] = {
    "makoto": RestaurantConfig(
        name="Makoto",
        slug="makoto",
        accent_color="#c8102e",
        accent_light="#fef2f2",
    ),
    "barclay prime": RestaurantConfig(
        name="Barclay Prime",
        slug="barclay-prime",
        accent_color="#1a1a2e",
        accent_light="#f0f0f5",
    ),
    "buddakan nyc": RestaurantConfig(
        name="Buddakan NYC",
        slug="buddakan-nyc",
        accent_color="#8b0000",
        accent_light="#fdf2f2",
    ),
    "le coucou": RestaurantConfig(
        name="Le Coucou",
        slug="le-coucou",
        accent_color="#2c5f2d",
        accent_light="#f2f7f2",
    ),
    "clocktower": RestaurantConfig(
        name="The Clocktower",
        slug="clocktower",
        accent_color="#6b4226",
        accent_light="#faf5f0",
    ),
    "el vez fl": RestaurantConfig(
        name="El Vez FL",
        slug="el-vez-fl",
        accent_color="#d4a017",
        accent_light="#fefbf0",
    ),
    "el vez": RestaurantConfig(
        name="El Vez",
        slug="el-vez",
        accent_color="#d4a017",
        accent_light="#fefbf0",
    ),
}


def detect_restaurant(filename: str, text: str) -> RestaurantConfig:
    """Detect restaurant from filename or document content.

    The restaurant name always matches the document filename (minus extension).
    Accent colours come from known configs if matched, otherwise use defaults.
    """
    # Clean filename (remove extension) — this IS the restaurant name
    name_base = re.sub(r"\.(docx?|pdf)$", "", filename, flags=re.IGNORECASE).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", name_base.lower()).strip("-")

    # Try to find a matching config for colours
    key = name_base.lower()
    matched: RestaurantConfig | None = None

    if key in RESTAURANTS:
        matched = RESTAURANTS[key]
    else:
        for rkey, config in RESTAURANTS.items():
            if rkey in key or key in rkey:
                matched = config
                break
        if not matched:
            text_lower = text[:500].lower()
            for rkey, config in RESTAURANTS.items():
                if rkey in text_lower:
                    matched = config
                    break

    return RestaurantConfig(
        name=name_base,
        slug=slug or "unknown",
        accent_color=matched.accent_color if matched else "#c8102e",
        accent_light=matched.accent_light if matched else "#fef2f2",
    )
