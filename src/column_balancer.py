"""Distribute flat sections into balanced columns for CMS layout."""

from __future__ import annotations

from .models import Column, ParsedMenu, ParsedTab, Restaurant, Section, Tab


def _count_items(sections: list[Section]) -> int:
    """Total item count across sections."""
    return sum(len(s.items) for s in sections)


def _target_columns(total_items: int) -> int:
    """Determine column count based on item thresholds."""
    if total_items <= 8:
        return 1
    if total_items <= 16:
        return 2
    return 3


def _balance_sections(sections: list[Section], num_columns: int) -> list[Column]:
    """Distribute sections across columns using sequential greedy assignment.

    Never splits a section across columns. Assigns sections sequentially,
    moving to the next column when the current one exceeds the target size.
    """
    if num_columns <= 1 or not sections:
        return [Column(sections=list(sections))]

    total = _count_items(sections)
    target_per_col = total / num_columns

    columns: list[Column] = []
    current_sections: list[Section] = []
    current_count = 0

    for section in sections:
        section_count = len(section.items)

        # If adding this section would exceed target AND we have items AND
        # we haven't filled all columns yet, start a new column
        if (
            current_count > 0
            and current_count + section_count > target_per_col * 1.2
            and len(columns) < num_columns - 1
        ):
            columns.append(Column(sections=current_sections))
            current_sections = []
            current_count = 0

        current_sections.append(section)
        current_count += section_count

    # Final column gets remaining sections
    if current_sections:
        columns.append(Column(sections=current_sections))

    return columns


def balance_tab(parsed_tab: ParsedTab) -> Tab:
    """Convert a ParsedTab (flat sections) into a Tab (with balanced columns)."""
    total_items = _count_items(parsed_tab.sections)
    num_columns = _target_columns(total_items)
    columns = _balance_sections(parsed_tab.sections, num_columns)

    return Tab(
        id=parsed_tab.id,
        label=parsed_tab.label,
        description=parsed_tab.description,
        columns=columns,
        footnote=parsed_tab.footnote,
    )


def balance_menu(
    parsed_menu: ParsedMenu,
    restaurant_name: str,
    slug: str,
    accent_color: str,
    accent_light: str,
) -> Restaurant:
    """Convert a ParsedMenu into a Restaurant with balanced columns."""
    tabs = [balance_tab(pt) for pt in parsed_menu.tabs]

    return Restaurant(
        name=restaurant_name,
        slug=slug,
        accent_color=accent_color,
        accent_light=accent_light,
        tabs=tabs,
    )
