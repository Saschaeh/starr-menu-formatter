"""Compare a doc-parsed menu against a live-site-parsed menu and produce a diff."""

from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher
from enum import Enum

from pydantic import BaseModel, Field

from .models import MenuItem, ParsedMenu, ParsedTab, Restaurant, Section


# ---------------------------------------------------------------------------
# Diff models
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    matched = "matched"
    added = "added"
    removed = "removed"
    modified = "modified"


class ItemDiff(BaseModel):
    item_name: str
    change_type: ChangeType
    doc_price: str | None = None
    live_price: str | None = None
    doc_description: str | None = None
    live_description: str | None = None
    details: str | None = None


class SectionDiff(BaseModel):
    section_title: str
    change_type: ChangeType
    item_diffs: list[ItemDiff] = Field(default_factory=list)


class TabDiff(BaseModel):
    tab_label: str
    change_type: ChangeType
    section_diffs: list[SectionDiff] = Field(default_factory=list)


class MenuDiff(BaseModel):
    restaurant_name: str
    summary: str = ""
    tabs: list[TabDiff] = Field(default_factory=list)
    total_matched: int = 0
    total_added: int = 0
    total_removed: int = 0
    total_modified: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip non-alphanumeric for fuzzy comparison."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _normalize_price(price: str | None) -> str | None:
    """Strip $ and trailing .00 so '$24' == '$24.00'."""
    if not price:
        return None
    cleaned = price.strip().replace("$", "").replace(",", "")
    # Try to parse as a number and normalize
    try:
        val = float(cleaned)
        # Return without trailing zeros: 24.0 -> "24", 24.50 -> "24.5"
        if val == int(val):
            return str(int(val))
        return str(val)
    except ValueError:
        return cleaned.lower()


def _fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    """Check if two strings are a fuzzy match above the threshold."""
    na, nb = _normalize(a), _normalize(b)
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def _best_match(target: str, candidates: list[str], threshold: float = 0.8) -> int | None:
    """Find the best fuzzy match index in candidates, or None."""
    best_idx = None
    best_score = 0.0
    nt = _normalize(target)
    for i, c in enumerate(candidates):
        nc = _normalize(c)
        if nt == nc:
            return i
        score = SequenceMatcher(None, nt, nc).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_idx = i
    return best_idx


# ---------------------------------------------------------------------------
# Restaurant → ParsedMenu (flatten columns, merge cont. splits)
# ---------------------------------------------------------------------------

def restaurant_to_parsed_menu(restaurant: Restaurant) -> ParsedMenu:
    """Flatten a balanced Restaurant back to a flat ParsedMenu for comparison."""
    tabs: list[ParsedTab] = []

    for tab in restaurant.tabs:
        # Collect all sections across all columns
        flat_sections: list[Section] = []
        for col in tab.columns:
            flat_sections.extend(col.sections)

        # Merge (cont.) sections back together
        merged: list[Section] = []
        for sec in flat_sections:
            title = sec.title.strip()
            # Check if this is a continuation
            if title.endswith("(cont.)"):
                base_title = title.replace("(cont.)", "").strip()
                # Find the original section to merge into
                found = False
                for m in merged:
                    if _normalize(m.title) == _normalize(base_title):
                        m.items.extend(sec.items)
                        found = True
                        break
                if not found:
                    merged.append(Section(
                        title=base_title,
                        note=sec.note,
                        items=list(sec.items),
                    ))
            elif title == "\u00a0":
                # Non-breaking space title from single-section column split
                if merged:
                    merged[-1].items.extend(sec.items)
                else:
                    merged.append(Section(title="", note=sec.note, items=list(sec.items)))
            else:
                merged.append(Section(
                    title=title,
                    note=sec.note,
                    items=list(sec.items),
                ))

        tabs.append(ParsedTab(
            id=tab.id,
            label=tab.label,
            description=tab.description,
            sections=merged,
            footnote=tab.footnote,
        ))

    return ParsedMenu(restaurant_name=restaurant.name, tabs=tabs)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _compare_items(doc_items: list[MenuItem], live_items: list[MenuItem]) -> list[ItemDiff]:
    """Compare items within a matched section."""
    diffs: list[ItemDiff] = []
    live_used: set[int] = set()

    for doc_item in doc_items:
        # Try to find a matching live item
        live_names = [it.name for it in live_items]
        match_idx = _best_match(doc_item.name, live_names, threshold=0.75)

        # Make sure we haven't already used this match
        if match_idx is not None and match_idx in live_used:
            match_idx = None

        if match_idx is not None:
            live_used.add(match_idx)
            live_item = live_items[match_idx]

            # Compare prices
            doc_p = _normalize_price(doc_item.price)
            live_p = _normalize_price(live_item.price)
            price_changed = doc_p != live_p

            # Compare descriptions (looser — web descriptions are often different)
            doc_d = _normalize(doc_item.description or "")
            live_d = _normalize(live_item.description or "")
            desc_changed = bool(doc_d and live_d and not _fuzzy_match(
                doc_item.description or "", live_item.description or "", threshold=0.6
            ))

            if price_changed or desc_changed:
                details_parts = []
                if price_changed:
                    details_parts.append(f"Price: {doc_item.price or '—'} → {live_item.price or '—'}")
                if desc_changed:
                    details_parts.append("Description changed")
                diffs.append(ItemDiff(
                    item_name=doc_item.name,
                    change_type=ChangeType.modified,
                    doc_price=doc_item.price,
                    live_price=live_item.price,
                    doc_description=doc_item.description,
                    live_description=live_item.description,
                    details="; ".join(details_parts),
                ))
            else:
                diffs.append(ItemDiff(
                    item_name=doc_item.name,
                    change_type=ChangeType.matched,
                    doc_price=doc_item.price,
                    live_price=live_item.price,
                ))
        else:
            diffs.append(ItemDiff(
                item_name=doc_item.name,
                change_type=ChangeType.removed,
                doc_price=doc_item.price,
                doc_description=doc_item.description,
                details="In doc but not found on live site",
            ))

    # Items on live site not matched to any doc item
    for i, live_item in enumerate(live_items):
        if i not in live_used:
            diffs.append(ItemDiff(
                item_name=live_item.name,
                change_type=ChangeType.added,
                live_price=live_item.price,
                live_description=live_item.description,
                details="On live site but not in doc",
            ))

    return diffs


def _compare_sections(
    doc_sections: list[Section],
    live_sections: list[Section],
) -> list[SectionDiff]:
    """Compare sections within a matched tab."""
    diffs: list[SectionDiff] = []
    live_used: set[int] = set()

    for doc_sec in doc_sections:
        live_titles = [s.title for s in live_sections]
        match_idx = _best_match(doc_sec.title, live_titles, threshold=0.7)

        if match_idx is not None and match_idx in live_used:
            match_idx = None

        if match_idx is not None:
            live_used.add(match_idx)
            live_sec = live_sections[match_idx]
            item_diffs = _compare_items(doc_sec.items, live_sec.items)

            has_changes = any(d.change_type != ChangeType.matched for d in item_diffs)
            diffs.append(SectionDiff(
                section_title=doc_sec.title,
                change_type=ChangeType.modified if has_changes else ChangeType.matched,
                item_diffs=item_diffs,
            ))
        else:
            # Section removed from live site
            diffs.append(SectionDiff(
                section_title=doc_sec.title,
                change_type=ChangeType.removed,
                item_diffs=[
                    ItemDiff(
                        item_name=it.name,
                        change_type=ChangeType.removed,
                        doc_price=it.price,
                    )
                    for it in doc_sec.items
                ],
            ))

    # Sections on live site not in doc
    for i, live_sec in enumerate(live_sections):
        if i not in live_used:
            diffs.append(SectionDiff(
                section_title=live_sec.title,
                change_type=ChangeType.added,
                item_diffs=[
                    ItemDiff(
                        item_name=it.name,
                        change_type=ChangeType.added,
                        live_price=it.price,
                    )
                    for it in live_sec.items
                ],
            ))

    return diffs


def compare_menus(doc_menu: ParsedMenu, live_menu: ParsedMenu) -> MenuDiff:
    """Three-phase comparison: tabs → sections → items."""
    tab_diffs: list[TabDiff] = []
    live_tab_used: set[int] = set()

    total_matched = total_added = total_removed = total_modified = 0

    for doc_tab in doc_menu.tabs:
        live_labels = [t.label for t in live_menu.tabs]
        match_idx = _best_match(doc_tab.label, live_labels, threshold=0.6)

        if match_idx is not None and match_idx in live_tab_used:
            match_idx = None

        if match_idx is not None:
            live_tab_used.add(match_idx)
            live_tab = live_menu.tabs[match_idx]
            section_diffs = _compare_sections(doc_tab.sections, live_tab.sections)

            has_changes = any(s.change_type != ChangeType.matched for s in section_diffs)
            tab_diffs.append(TabDiff(
                tab_label=doc_tab.label,
                change_type=ChangeType.modified if has_changes else ChangeType.matched,
                section_diffs=section_diffs,
            ))
        else:
            tab_diffs.append(TabDiff(
                tab_label=doc_tab.label,
                change_type=ChangeType.removed,
                section_diffs=[
                    SectionDiff(
                        section_title=sec.title,
                        change_type=ChangeType.removed,
                        item_diffs=[
                            ItemDiff(item_name=it.name, change_type=ChangeType.removed, doc_price=it.price)
                            for it in sec.items
                        ],
                    )
                    for sec in doc_tab.sections
                ],
            ))

    # Tabs on live site not matched
    for i, live_tab in enumerate(live_menu.tabs):
        if i not in live_tab_used:
            tab_diffs.append(TabDiff(
                tab_label=live_tab.label,
                change_type=ChangeType.added,
                section_diffs=[
                    SectionDiff(
                        section_title=sec.title,
                        change_type=ChangeType.added,
                        item_diffs=[
                            ItemDiff(item_name=it.name, change_type=ChangeType.added, live_price=it.price)
                            for it in sec.items
                        ],
                    )
                    for sec in live_tab.sections
                ],
            ))

    # Count totals across all item diffs
    for tab in tab_diffs:
        for sec in tab.section_diffs:
            for item in sec.item_diffs:
                if item.change_type == ChangeType.matched:
                    total_matched += 1
                elif item.change_type == ChangeType.added:
                    total_added += 1
                elif item.change_type == ChangeType.removed:
                    total_removed += 1
                elif item.change_type == ChangeType.modified:
                    total_modified += 1

    total = total_matched + total_added + total_removed + total_modified
    summary = (
        f"{total_matched} matched, {total_modified} changed, "
        f"{total_removed} missing, {total_added} new "
        f"(out of {total} items compared)"
    )

    return MenuDiff(
        restaurant_name=doc_menu.restaurant_name,
        summary=summary,
        tabs=tab_diffs,
        total_matched=total_matched,
        total_added=total_added,
        total_removed=total_removed,
        total_modified=total_modified,
    )


# ---------------------------------------------------------------------------
# Apply diff — mutate a doc_menu to match live_menu based on a diff
# ---------------------------------------------------------------------------

def _find_section(tab: ParsedTab, title: str) -> Section | None:
    """Find a section in a tab by fuzzy title match."""
    for sec in tab.sections:
        if _fuzzy_match(sec.title, title, threshold=0.7):
            return sec
    return None


def _find_item(section: Section, name: str) -> MenuItem | None:
    """Find an item in a section by fuzzy name match."""
    for item in section.items:
        if _fuzzy_match(item.name, name, threshold=0.75):
            return item
    return None


def _find_tab(menu: ParsedMenu, label: str) -> ParsedTab | None:
    """Find a tab in a menu by fuzzy label match."""
    for tab in menu.tabs:
        if _fuzzy_match(tab.label, label, threshold=0.6):
            return tab
    return None


def apply_diff(
    doc_menu: ParsedMenu,
    diff: MenuDiff,
    live_menu: ParsedMenu,
) -> ParsedMenu:
    """Apply a MenuDiff to doc_menu, pulling new data from live_menu.

    Returns a new ParsedMenu with:
    - modified items: price/description updated from live values in the diff
    - removed items: deleted from their sections
    - added items: copied from live_menu into the matching section
    - added sections: copied whole from live_menu
    - added tabs: copied whole from live_menu
    """
    result = copy.deepcopy(doc_menu)

    for tab_diff in diff.tabs:
        if tab_diff.change_type == ChangeType.added:
            # Whole tab is new — copy from live_menu
            live_tab = _find_tab(live_menu, tab_diff.tab_label)
            if live_tab:
                result.tabs.append(copy.deepcopy(live_tab))
            continue

        if tab_diff.change_type == ChangeType.removed:
            # Tab was in doc but not on live site — remove it
            result.tabs = [
                t for t in result.tabs
                if not _fuzzy_match(t.label, tab_diff.tab_label, threshold=0.6)
            ]
            continue

        # matched or modified — walk sections
        doc_tab = _find_tab(result, tab_diff.tab_label)
        if not doc_tab:
            continue

        for sec_diff in tab_diff.section_diffs:
            if sec_diff.change_type == ChangeType.added:
                # Whole section is new — copy from live_menu
                live_tab = _find_tab(live_menu, tab_diff.tab_label)
                if live_tab:
                    live_sec = _find_section(live_tab, sec_diff.section_title)
                    if live_sec:
                        doc_tab.sections.append(copy.deepcopy(live_sec))
                continue

            if sec_diff.change_type == ChangeType.removed:
                # Section was in doc but not on live site — remove it
                doc_tab.sections = [
                    s for s in doc_tab.sections
                    if not _fuzzy_match(s.title, sec_diff.section_title, threshold=0.7)
                ]
                continue

            # matched or modified — walk items
            doc_sec = _find_section(doc_tab, sec_diff.section_title)
            if not doc_sec:
                continue

            items_to_remove: list[str] = []

            for item_diff in sec_diff.item_diffs:
                if item_diff.change_type == ChangeType.modified:
                    doc_item = _find_item(doc_sec, item_diff.item_name)
                    if doc_item:
                        if item_diff.live_price is not None:
                            doc_item.price = item_diff.live_price
                        if item_diff.live_description is not None:
                            doc_item.description = item_diff.live_description

                elif item_diff.change_type == ChangeType.removed:
                    items_to_remove.append(item_diff.item_name)

                elif item_diff.change_type == ChangeType.added:
                    # Find the item in live_menu and append
                    live_tab = _find_tab(live_menu, tab_diff.tab_label)
                    if live_tab:
                        live_sec = _find_section(live_tab, sec_diff.section_title)
                        if live_sec:
                            live_item = _find_item(live_sec, item_diff.item_name)
                            if live_item:
                                doc_sec.items.append(copy.deepcopy(live_item))

            # Remove items flagged for deletion
            if items_to_remove:
                doc_sec.items = [
                    it for it in doc_sec.items
                    if not any(
                        _fuzzy_match(it.name, name, threshold=0.75)
                        for name in items_to_remove
                    )
                ]

    return result
