"""Extract and annotate text from .docx files for LLM consumption."""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn


def _is_bold(run) -> bool:
    """Determine if a run is bold, handling tri-state (True / None / False).

    None means inherited from style — we treat that as not-bold for inline detection.
    Explicit True means the author deliberately bolded that run.
    """
    return run.bold is True


def _get_heading_level(para) -> int | None:
    """Return heading level (1, 2, ...) or None if not a heading."""
    style_name = para.style.name if para.style else ""
    if style_name == "Title":
        return 1
    match = re.match(r"Heading (\d+)", style_name)
    if match:
        return int(match.group(1))
    return None


def _is_list_paragraph(para) -> bool:
    return (para.style.name if para.style else "") == "List Paragraph"


def extract_text(file_bytes: bytes) -> str:
    """Extract annotated text from a .docx file.

    Returns markdown-style annotated text:
    - # Title for H1/Title
    - ## Tab Name for H2
    - **Bold text** for bold runs
    - Regular text as-is
    """
    doc = Document(BytesIO(file_bytes))
    lines: list[str] = []
    in_menu_section = False

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Normalize non-breaking spaces
        text = text.replace("\xa0", " ")

        heading = _get_heading_level(para)
        if heading == 1:
            if re.match(r"Menu Pages", text, re.IGNORECASE):
                in_menu_section = True
            lines.append(f"# {text}")
            continue
        if heading == 2:
            lines.append(f"## {text}")
            continue

        # Skip list paragraphs only before "Menu Pages" heading (homepage meta-notes)
        if _is_list_paragraph(para) and not in_menu_section:
            continue

        # Check if the entire paragraph is bold via runs
        runs_with_text = [r for r in para.runs if r.text.strip()]
        if runs_with_text and all(_is_bold(r) for r in runs_with_text):
            lines.append(f"**{text}**")
        else:
            lines.append(text)

    return "\n".join(lines)


def filter_menu_content(text: str) -> str:
    """Filter extracted text to only include menu content.

    Discards:
    - Everything before "Menu Pages" heading
    - DOWNLOAD PDF lines
    - Repeated menu nav headers (tab names that appear on every page)
    - Footer/homepage content
    """
    lines = text.split("\n")

    # Find "Menu Pages" marker
    menu_start = None
    for i, line in enumerate(lines):
        if re.match(r"^#\s+Menu Pages", line, re.IGNORECASE):
            menu_start = i + 1
            break

    if menu_start is None:
        # Fallback: try to find the first ## heading
        for i, line in enumerate(lines):
            if line.startswith("## "):
                menu_start = i
                break

    if menu_start is None:
        # No markers found — return everything
        return text

    lines = lines[menu_start:]

    # Filter out noise
    filtered: list[str] = []
    skip_patterns = [
        r"^DOWNLOAD PDF$",
        r"^Click.*(vegan|vegetarian|gluten-free|menu).*$",
        r"^Click\s*here\s",
        r"^Menu Header\s*\(",
        r"^STARR RESTAURANTS$",
        r"^(Facebook|Instagram|Spotify|LinkedIn|Careers|Shop|Donations)$",
        r"^(Privacy Policy|Accessibility|Terms of Use)$",
        r"^JOIN OUR MAILING LIST$",
        r"^CONNECT WITH US$",
        r"^(HOURS|CONTACT|LOCATION)$",
        r"^PHONE:",
        r"^GENERAL:",
        r"^(GROUP DINING|MARKETING|PRESS):",
        r"^ORDER NOW",
        r"^RESERVE A TABLE$",
        r"^VIEW ALL HAPPENINGS$",
        r"^Book your spot",
        r"^SAVE THE DATES",
    ]

    # Tab headings to skip entirely (variant/dietary tabs, non-menu pages)
    skip_tab_patterns = [
        r"vegan|vegetarian|gluten.free",
        r"^VEG\s+",  # "VEG Dinner Menu", "VEG Dessert Menu"
        r"group\s+dining",
        r"happenings?",
        r"private\s+(dining|events?)",
        r"gift\s+cards?",
    ]

    # Track which tab labels we've seen (to skip repeated nav headers)
    in_nav_block = False
    nav_labels: set[str] = set()
    skip_current_tab = False

    # First pass: collect all H2 tab labels
    for line in lines:
        m = re.match(r"^##\s+(.+?)(?:\s+Page)?:?\s*$", line)
        if m:
            nav_labels.add(m.group(1).strip().upper())

    for line in lines:
        stripped = line.strip()

        # Skip blank lines
        if not stripped:
            continue

        # Check for tab headings — decide whether to skip entire tab
        if stripped.startswith("## "):
            tab_label = stripped[3:].strip()
            skip_current_tab = any(
                re.search(pat, tab_label, re.IGNORECASE)
                for pat in skip_tab_patterns
            )
            if skip_current_tab:
                continue
            in_nav_block = False

        # Skip all content under a skipped tab (until next ## heading)
        if skip_current_tab:
            continue

        # Skip known noise patterns
        if any(re.match(pat, stripped, re.IGNORECASE) for pat in skip_patterns):
            continue

        # Skip repeated menu nav blocks (tab names that appear at top of each page)
        # These are lines that exactly match known tab labels in ALL CAPS
        if stripped.upper() in nav_labels and not stripped.startswith("## "):
            # Could be a nav label OR a section title — only skip if it appears
            # right after a tab heading or other nav labels (within first few lines of a tab)
            if in_nav_block or (filtered and re.match(r"^##\s+", filtered[-1])):
                in_nav_block = True
                continue

        if in_nav_block and stripped.upper() not in nav_labels:
            in_nav_block = False

        filtered.append(line)

    return "\n".join(filtered)
