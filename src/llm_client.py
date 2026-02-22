"""Claude API integration for menu parsing."""

from __future__ import annotations

import json
import re

import anthropic

from .models import ParsedMenu, ParsedTab

SYSTEM_PROMPT = """\
You are a menu data extraction specialist for Starr Restaurants. Your job is to parse a single menu tab into structured JSON.

## Output Schema

Return ONLY valid JSON (no markdown, no code fences):

{
  "id": "tab-slug",
  "label": "Tab Label",
  "description": "Optional tab description text",
  "sections": [
    {
      "title": "Section Name",
      "note": "Optional subtitle like 'choice of:' or 'charcoal grilled'",
      "items": [
        {
          "name": "Item Name",
          "price": "$29",
          "description": "item description, ingredients",
          "raw": false,
          "supplement": null,
          "tags": []
        }
      ]
    }
  ],
  "footnote": "Optional footnote text (raw/undercooked disclaimer, etc.)"
}

## Parsing Rules

### Tab Identity
- The tab heading is provided. Generate a URL-friendly slug for "id" and a clean "label".
- Remove "Page:" or "Page" suffix from labels: "Dinner Page:" → id: "dinner", label: "Dinner"

### Section Headings
- Lines wrapped in `**bold**` are SECTION headings within the tab.

### Menu Items
Each item can appear in two formats:

**Format A — One item per line with inline price:**
`Item Name  description  $29`
or `Item Name  $29` followed by a description on a new line.

**Format B — Multi-line blocks:**
`Item Name  $29` then `description text, ingredients`
or `Item Name*  +$7` then `description`

### Price Extraction
- Standard: `$29`, `$198`, `$30 per oz.`
- Supplement/upcharge: `+$7`, `+$12` → "supplement" field, NOT "price"
- Prix fixe base price like "$35 per person" → section note or tab description
- Dual prices: `8 oz. $72` / `10 oz. $89` → keep size in name, price separate
- No price: set price to null

### Special Markers
- `*` after item name → set "raw": true
- Dietary tags (GF), (V), (VG) → "tags" array
- Section subtitle text like "choice of:", "charcoal grilled" → section "note"

### Content to IGNORE
- "DOWNLOAD PDF" lines
- "Click to view/see..." links
- Tab names listed at top (navigation headers)
- Footer content, contact info

### Footnotes
- Raw/undercooked disclaimers → "footnote"

### Tab Description
- Text right after the tab title (before sections) describing the tab → "description"

## Important
- Preserve exact item names, descriptions, and prices
- Do NOT invent items — only extract what's in the document
- Keep accent marks and special characters
- Maintain document order
- If the tab has NO menu items, return sections as an empty array
"""


def _split_into_tabs(text: str) -> list[tuple[str, str]]:
    """Split filtered document text into (heading, content) per tab."""
    lines = text.split("\n")
    tabs: list[tuple[str, str]] = []
    current_heading = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            # Save previous tab
            if current_heading is not None:
                tabs.append((current_heading, "\n".join(current_lines)))
            current_heading = line
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    # Save last tab
    if current_heading is not None:
        tabs.append((current_heading, "\n".join(current_lines)))

    return tabs


def _parse_single_tab(
    client: anthropic.Anthropic,
    heading: str,
    content: str,
    model: str,
) -> ParsedTab | None:
    """Parse a single tab's content via the API. Returns None if tab is empty."""
    # Skip tabs with no real content
    stripped = content.strip()
    if not stripped or len(stripped) < 10:
        return None

    user_prompt = f"Parse this menu tab into structured JSON:\n\nTab heading: {heading}\n\n<content>\n{content}\n</content>"

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)

    data = json.loads(raw)
    tab = ParsedTab.model_validate(data)

    # Skip tabs that have no items at all
    total_items = sum(len(s.items) for s in tab.sections)
    if total_items == 0:
        return None

    return tab


def parse_menu(
    text: str,
    model: str = "claude-3-haiku-20240307",
    api_key: str | None = None,
    on_progress: callable = None,
) -> tuple[ParsedMenu, str]:
    """Parse menu by splitting into per-tab API calls.

    Args:
        text: Filtered, annotated menu text from docx_parser.
        model: Claude model ID to use.
        api_key: Optional API key.
        on_progress: Optional callback(tab_name, index, total) for progress updates.

    Returns:
        Tuple of (ParsedMenu, raw_responses_combined).
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    tab_chunks = _split_into_tabs(text)
    if not tab_chunks:
        raise ValueError("No tab headings (## ) found in the document.")

    tabs: list[ParsedTab] = []
    raw_responses: list[str] = []
    errors: list[str] = []

    for i, (heading, content) in enumerate(tab_chunks):
        tab_name = heading.replace("## ", "").replace("Page:", "").replace("Page", "").strip().rstrip(":")
        if on_progress:
            on_progress(tab_name, i + 1, len(tab_chunks))

        try:
            tab = _parse_single_tab(client, heading, content, model)
            if tab:
                tabs.append(tab)
                raw_responses.append(f"--- {tab_name} ---\n{json.dumps(tab.model_dump(), indent=2)}")
        except json.JSONDecodeError as e:
            errors.append(f"{tab_name}: JSON parse error — {e}")
        except anthropic.APIError as e:
            errors.append(f"{tab_name}: API error — {e}")

    if not tabs:
        error_detail = "\n".join(errors) if errors else "No menu items found in any tab."
        raise ValueError(f"No tabs with menu items were parsed.\n{error_detail}")

    # Extract restaurant name from first tab or heading
    restaurant_name = tab_chunks[0][0].replace("## ", "").split("Page")[0].strip().rstrip(":")
    parsed = ParsedMenu(restaurant_name=restaurant_name, tabs=tabs)

    return parsed, "\n\n".join(raw_responses)
