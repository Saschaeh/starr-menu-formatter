"""Distribute flat sections into balanced columns for CMS layout."""

from __future__ import annotations

from .models import Column, MenuItem, ParsedMenu, ParsedTab, Restaurant, Section, Tab


def _count_items(sections: list[Section]) -> int:
    """Total item count across sections."""
    return sum(len(s.items) for s in sections)


def _target_columns(total_items: int, num_sections: int) -> int:
    """Determine column count based on items and section count."""
    # Many sections (4+) always get 3 columns for visual balance
    if num_sections >= 4:
        return 3
    # Even with few items, multiple sections benefit from 2-3 columns
    if num_sections >= 2 and total_items >= 4:
        return min(3, num_sections) if total_items >= 6 else 2
    # Single section: spread items across columns for visual balance
    if total_items <= 3:
        return 1
    if total_items <= 5:
        return 2
    return 3


def _split_section(section: Section, max_items: int) -> list[Section]:
    """Split a large section into multiple sections with '(cont.)' suffix.

    Used when a single section has too many items to fit in one column.
    """
    if len(section.items) <= max_items:
        return [section]

    parts: list[Section] = []
    items = section.items
    for i in range(0, len(items), max_items):
        chunk = items[i : i + max_items]
        if i == 0:
            parts.append(Section(
                title=section.title,
                note=section.note,
                items=chunk,
            ))
        else:
            parts.append(Section(
                title=f"{section.title} (cont.)",
                note=section.note,
                items=chunk,
            ))

    return parts


def _prepare_sections(sections: list[Section], num_columns: int) -> list[Section]:
    """Pre-process sections: split oversized ones so they can balance across columns."""
    if num_columns <= 1:
        return list(sections)

    total_items = _count_items(sections)
    target_per_col = max(total_items // num_columns, 4)
    # Allow a section up to 1.5x the target before splitting
    max_per_section = int(target_per_col * 1.5)

    result: list[Section] = []
    for section in sections:
        if len(section.items) > max_per_section:
            result.extend(_split_section(section, target_per_col))
        else:
            result.append(section)

    return result


def _balance_sections(sections: list[Section], num_columns: int) -> list[Column]:
    """Distribute sections across columns using sequential greedy assignment.

    Splits oversized sections with '(cont.)' suffix, then assigns sections
    sequentially, moving to the next column when the current one exceeds target.
    """
    if num_columns <= 1 or not sections:
        return [Column(sections=list(sections))]

    # Pre-split oversized sections
    prepared = _prepare_sections(sections, num_columns)

    total = _count_items(prepared)
    target_per_col = total / num_columns

    columns: list[Column] = []
    current_sections: list[Section] = []
    current_count = 0

    for section in prepared:
        section_count = len(section.items)

        # If adding this section would exceed target AND we have items AND
        # we haven't filled all columns yet, start a new column
        if (
            current_count > 0
            and current_count + section_count > target_per_col * 1.15
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


def _balance_single_section(section: Section, num_columns: int) -> list[Column]:
    """Special case: spread a single section's items evenly across columns.

    Used when there's only one section (e.g. Dessert) but we want multiple
    columns for visual balance. Creates columns with empty-title sections.
    """
    items = section.items
    total = len(items)
    per_col = max(1, (total + num_columns - 1) // num_columns)

    columns: list[Column] = []
    for i in range(0, total, per_col):
        chunk = items[i : i + per_col]
        # First column keeps the section title; others get blank title
        title = section.title if i == 0 else "\u00a0"
        columns.append(Column(sections=[Section(
            title=title,
            note=section.note if i == 0 else None,
            items=chunk,
        )]))

    return columns


def balance_tab(parsed_tab: ParsedTab) -> Tab:
    """Convert a ParsedTab (flat sections) into a Tab (with balanced columns)."""
    sections = parsed_tab.sections
    total_items = _count_items(sections)
    num_columns = _target_columns(total_items, len(sections))

    # Special case: single section with items should spread across columns
    if len(sections) == 1 and num_columns > 1 and total_items >= 4:
        columns = _balance_single_section(sections[0], num_columns)
    else:
        columns = _balance_sections(sections, num_columns)

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
