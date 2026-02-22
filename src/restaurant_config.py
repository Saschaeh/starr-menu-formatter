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

    Tries filename first, then scans first 500 chars of content.
    Falls back to generating config from filename.
    """
    # Clean filename (remove extension)
    name_base = re.sub(r"\.(docx?|pdf)$", "", filename, flags=re.IGNORECASE).strip()

    # Try exact match on filename
    key = name_base.lower()
    if key in RESTAURANTS:
        return RESTAURANTS[key]

    # Try substring match on filename
    for rkey, config in RESTAURANTS.items():
        if rkey in key or key in rkey:
            return config

    # Try matching against document text
    text_lower = text[:500].lower()
    for rkey, config in RESTAURANTS.items():
        if rkey in text_lower:
            return config

    # Fallback: generate from filename
    slug = re.sub(r"[^a-z0-9]+", "-", name_base.lower()).strip("-")
    return RestaurantConfig(
        name=name_base.title(),
        slug=slug or "unknown",
        accent_color="#c8102e",
        accent_light="#fef2f2",
    )
