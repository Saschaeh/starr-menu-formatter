"""Claude API integration for menu parsing."""

from __future__ import annotations

import json
import re

import anthropic

from .models import ParsedMenu

SYSTEM_PROMPT = """\
You are a menu data extraction specialist for Starr Restaurants. Your job is to parse restaurant menu documents into structured JSON that maps to a WordPress CMS layout.

## Output Schema

Return ONLY valid JSON matching this structure (no markdown, no code fences):

{
  "restaurant_name": "Restaurant Name",
  "tabs": [
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
  ]
}

## Parsing Rules

### Document Structure
- Lines starting with `## ` are TAB headings. The text after `## ` (minus "Page:" suffix) becomes the tab label.
- Lines wrapped in `**bold**` are SECTION headings within a tab.
- Everything else is menu item content.

### Tab IDs
- Generate URL-friendly slugs: "Miami Spice Page:" → id: "miami-spice", label: "Miami Spice"
- Remove "Page:" or "Page" suffix from labels.

### Menu Items
Each item can appear in two formats:

**Format A — One item per line with inline price:**
`Item Name  description  $29`
or
`Item Name  $29`
followed by a description on a new line.

**Format B — Multi-line blocks:**
```
Item Name  $29
description text, ingredients
```
or
```
Item Name*  +$7
description
```

### Price Extraction
- Standard: `$29`, `$198`, `$30 per oz.`
- Supplement/upcharge: `+$7`, `+$12` — put in "supplement" field, NOT in "price"
- Prix fixe base price: appears after section note like "$35 per person" — put as section note
- Dual prices: `8 oz. $72` / `10 oz. $89` — keep size in the name, price separate
- No price: some items in prix fixe menus have no individual price — set price to null

### Special Markers
- `*` after item name → set "raw": true (indicates may contain raw ingredients)
- Dietary tags like (GF), (V), (VG) → extract into "tags" array
- Section subtitle text like "choice of:", "charcoal grilled", "served with..." → put in section "note"

### Content to IGNORE
- "DOWNLOAD PDF" lines
- "Click to view/see..." links
- Repeated menu navigation headers (tab names listed at top of each page)
- Footer content, contact info, social media
- "Menu Header (appears on every menu page)" annotations

### Footnotes
- Raw/undercooked disclaimers → capture as tab "footnote"
- Format: "*May contain raw or undercooked..."

### Tab Description
- Text immediately after the tab title (before sections) that describes the tab
- Examples: "Available from August 1st – September 30th", "$35 per person"
- Put this in the tab's "description" field

## Important
- Preserve exact item names, descriptions, and prices from the document
- Do NOT invent or guess items — only extract what's in the document
- If a section has a subtitle/note, include it
- Keep accent marks and special characters (é, ü, ñ, etc.)
- Items within a section should maintain their document order
"""


def parse_menu(
    text: str,
    model: str = "claude-sonnet-4-5-20250514",
    api_key: str | None = None,
) -> tuple[ParsedMenu, str]:
    """Send filtered menu text to Claude and parse the JSON response.

    Args:
        text: Filtered, annotated menu text from docx_parser.
        model: Claude model ID to use.
        api_key: Optional API key (falls back to ANTHROPIC_API_KEY env var).

    Returns:
        ParsedMenu with flat sections per tab (no column balancing yet).

    Raises:
        ValueError: If the API returns invalid JSON or empty results.
        anthropic.APIError: On API communication errors.
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    user_prompt = f"Parse this restaurant menu document into structured JSON:\n\n<document>\n{text}\n</document>"

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_response = message.content[0].text

    # Extract JSON from response (handle potential markdown code fences)
    json_str = raw_response.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r"^```(?:json)?\s*\n?", "", json_str)
        json_str = re.sub(r"\n?```\s*$", "", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}\n\nRaw response:\n{raw_response[:500]}")

    parsed = ParsedMenu.model_validate(data)

    if not parsed.tabs:
        raise ValueError("LLM returned no tabs — the document may not contain menu content.")

    return parsed, raw_response
