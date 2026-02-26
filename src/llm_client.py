"""Claude API integration for menu parsing."""

from __future__ import annotations

import json
import re
import time

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

### Section Headings — CRITICAL
- EVERY line wrapped in `**bold**` markers is a section heading. You MUST create a section for EACH one.
- This includes food sections AND beverage sections: **Cocktails**, **Sake**, **Wine**, **Beer**, **Spirits**, etc.
- Do NOT skip or merge bold headings. Each `**bold**` line = one section in the output.
- If a section has sub-categories (e.g. WHITE / ROSE / RED under Wine), include the sub-category as a tag on each item.

### Menu Items
Each item can appear in two formats:

**Format A — One item per line with inline price:**
`Item Name  description  $29`
or `Item Name  $29` followed by a description on a new line.

**Format B — Multi-line blocks:**
`Item Name  $29` then `description text, ingredients`
or `Item Name*  +$7` then `description`

### Price Extraction
- Standard: `$29`, `$198`, `$30 per oz.`, `$30/oz.`
- Market price: `MP` or `Market Price` → set price to "MP"
- Supplement/upcharge: `+$7`, `+$12` → "supplement" field, NOT "price"
- Prix fixe base price like "$35 per person" → section note or tab description
- Dual prices: `$60 / $80` → keep as-is in price field
- Size + price: `8 oz. $72` → include size in description, price separate
- No price found: set price to null

### Special Markers
- `*` after item name → set "raw": true
- Dietary tags (GF), (V), (VG) → "tags" array
- Wine type labels (WHITE, ROSE/ROSÉ, RED) → add as tag on each wine item
- Section subtitle text like "choice of:", "charcoal grilled", "2 pieces per order" → section "note"

### Content to IGNORE (do NOT include as items)
- "DOWNLOAD PDF" lines
- "Click to view/see..." links
- Navigation labels at the start of content (single words in ALL CAPS that match tab names, e.g. "BEVERAGE", "LUNCH", "DINNER")
- The tab name repeated as plain text
- Footer content, contact info
- "Please let your server know..." disclaimers (these are NOT items)

### Footnotes
- Raw/undercooked disclaimers (lines starting with `*` at the end) → "footnote"

### Tab Description
- Text right after the tab title that describes pricing/availability/rules → "description"
- Examples: "Available August 1st – September 30th...", "$35 per person", "served with miso soup..."

## Important
- Preserve exact item names, descriptions, and prices from the document
- Do NOT invent items — only extract what's in the document
- Keep accent marks and special characters (é, â, ô, etc.)
- Maintain document order
- Extract ALL sections including beverages — do not stop at food sections
- If the tab has NO menu items, return sections as an empty array
"""


WEB_SYSTEM_PROMPT = """\
You are a menu data extraction specialist for Starr Restaurants. Your job is to parse a restaurant's live website menu text into structured JSON.

The text was scraped from a web page — it will NOT have markdown formatting like `**bold**` or `## headings`. Instead, section names and tab labels appear as plain text, often in ALL CAPS or Title Case. Use context clues (pricing, item lists) to identify structure.

## Output Schema

Return ONLY valid JSON (no markdown, no code fences):

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
          "note": "Optional subtitle",
          "items": [
            {
              "name": "Item Name",
              "price": "$29",
              "description": "item description",
              "raw": false,
              "supplement": null,
              "tags": []
            }
          ]
        }
      ],
      "footnote": null
    }
  ]
}

## Parsing Rules

### Tab Detection
- Look for major menu divisions: Lunch, Dinner, Brunch, Dessert, Beverage, Happy Hour, etc.
- If the page only has one menu (no tab divisions), create a single tab with id "menu" and label "Menu".
- Navigation-style labels at the top often indicate available tabs.

### Section Headings
- Lines in ALL CAPS or Title Case followed by menu items are section headings.
- Common sections: STARTERS, APPETIZERS, ENTREES, MAINS, SIDES, DESSERTS, COCKTAILS, WINE, etc.

### Menu Items
- Items typically have a name and a price on the same line or nearby.
- Descriptions/ingredients may follow on the next line.

### Price Extraction
- Standard: `$29`, `$198`, `$30 per oz.`
- Market price: `MP` or `Market Price` → set price to "MP"
- Supplement/upcharge: `+$7` → "supplement" field
- Dual prices: `$60 / $80` → keep as-is
- No price found: set price to null

### Special Markers
- `*` after item name → set "raw": true
- Dietary tags (GF), (V), (VG) → "tags" array

### Content to IGNORE
- Navigation links, "DOWNLOAD PDF", "Click to view..."
- Footer content, contact info, addresses, phone numbers
- Social media links, reservation buttons
- Cookie notices, legal disclaimers

## Important
- Preserve exact item names, descriptions, and prices
- Do NOT invent items — only extract what's in the text
- Keep accent marks and special characters
- Maintain document order
- Extract ALL sections including beverages
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

    # Collect all tab labels for noise detection
    tab_labels = set()
    for heading, _ in tabs:
        label = heading.replace("## ", "").strip()
        # Extract just the name part before "Page"
        name = re.sub(r"\s*Page\s*:?\s*$", "", label, flags=re.IGNORECASE).strip()
        tab_labels.add(name.upper())

    # Clean each tab's content: remove nav noise at the start
    cleaned_tabs = []
    for heading, content in tabs:
        cleaned_content = _clean_tab_content(content, tab_labels)
        cleaned_tabs.append((heading, cleaned_content))

    return cleaned_tabs


def _clean_tab_content(content: str, tab_labels: set[str]) -> str:
    """Remove navigation noise from the start of a tab's content.

    Strips lines before the first section heading (**bold**) or menu item
    that are just nav labels (e.g. "BEVERAGE", "LUNCH", the tab name repeated).
    """
    lines = content.split("\n")
    cleaned: list[str] = []
    found_content = False

    for line in lines:
        stripped = line.strip()

        if not found_content:
            # Skip empty lines at the start
            if not stripped:
                continue
            # Skip nav-like labels (single words in ALL CAPS that match tab labels)
            if stripped.upper() in tab_labels:
                continue
            # Skip single-word ALL CAPS lines that look like nav labels
            if re.match(r"^[A-Z]{3,}$", stripped) and stripped not in ("GF", "MP"):
                continue
            # Once we hit real content (bold section, price, description), keep everything
            found_content = True

        cleaned.append(line)

    return "\n".join(cleaned)


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

    # Retry with exponential backoff on transient API errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except anthropic.APIStatusError as e:
            if e.status_code in (503, 529) and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise

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
    model: str = "claude-sonnet-4-5",
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
            if "credit balance is too low" in str(e):
                errors.append(f"{tab_name}: The kitchen ran out of AI tokens — top up your credits to keep cooking!")
            else:
                errors.append(f"{tab_name}: Something went wrong in the kitchen — {e}")

    if not tabs:
        error_detail = "\n".join(errors) if errors else "No menu items found in any tab."
        raise ValueError(f"No tabs with menu items were parsed.\n{error_detail}")

    # Surface partial errors alongside successful results
    if errors:
        import warnings
        warnings.warn(
            f"{len(errors)} tab(s) failed to parse: " + "; ".join(errors),
            stacklevel=2,
        )

    # Extract restaurant name from first tab or heading
    restaurant_name = tab_chunks[0][0].replace("## ", "").split("Page")[0].strip().rstrip(":")
    parsed = ParsedMenu(restaurant_name=restaurant_name, tabs=tabs)

    return parsed, "\n\n".join(raw_responses)


def parse_live_menu(
    text: str,
    model: str = "claude-sonnet-4-5",
    api_key: str | None = None,
    on_progress: callable = None,
) -> ParsedMenu:
    """Parse web-scraped menu text into a ParsedMenu via a single API call.

    Args:
        text: Cleaned text from web_scraper.scrape_menu_page().
        model: Claude model ID.
        api_key: Optional API key.
        on_progress: Optional callback(message) for status updates.

    Returns:
        ParsedMenu with all tabs/sections/items extracted from the live site.
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    if on_progress:
        on_progress("Sending to Claude for parsing...")

    user_prompt = (
        "Parse this restaurant's live website menu text into structured JSON.\n\n"
        "<content>\n"
        f"{text}\n"
        "</content>"
    )

    message = client.messages.create(
        model=model,
        max_tokens=16384,
        system=WEB_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)

    data = json.loads(raw)
    parsed = ParsedMenu.model_validate(data)

    if on_progress:
        on_progress(f"Parsed {len(parsed.tabs)} tab(s) from live site")

    return parsed
