"""Pydantic data models for the menu CMS formatter."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class MenuItem(BaseModel):
    """A single menu item (dish, drink, etc.)."""

    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("MenuItem name cannot be empty")
        return v
    price: str | None = None
    description: str | None = None
    raw: bool = False
    supplement: str | None = None  # e.g. "+$7"
    tags: list[str] = Field(default_factory=list)  # e.g. ["GF", "V", "VG"]


class Section(BaseModel):
    """A named group of menu items (e.g. 'Starters', 'Raw Bar')."""

    title: str
    note: str | None = None  # subtitle text like "choice of:" or "charcoal grilled"
    items: list[MenuItem] = Field(default_factory=list)


class Column(BaseModel):
    """A column of sections in the CMS layout."""

    sections: list[Section] = Field(default_factory=list)


class Tab(BaseModel):
    """A menu tab (page) with balanced columns — ready for rendering."""

    id: str
    label: str
    description: str | None = None
    columns: list[Column] = Field(default_factory=list)
    footnote: str | None = None


class Restaurant(BaseModel):
    """Top-level restaurant with all tabs — the final render model."""

    name: str
    slug: str
    accent_color: str = "#c8102e"
    accent_light: str = "#fef2f2"
    tabs: list[Tab] = Field(default_factory=list)


# --- LLM output models (flat sections, no columns yet) ---


class ParsedTab(BaseModel):
    """A tab as returned by the LLM — flat list of sections, no column balancing."""

    id: str
    label: str
    description: str | None = None
    sections: list[Section] = Field(default_factory=list)
    footnote: str | None = None


class ParsedMenu(BaseModel):
    """Complete LLM output for one document."""

    restaurant_name: str
    tabs: list[ParsedTab] = Field(default_factory=list)
