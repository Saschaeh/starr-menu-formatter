"""Starr Menu CMS Formatter — Streamlit App."""

import copy
import time

import streamlit as st
import streamlit.components.v1 as components

from src.docx_parser import extract_text, filter_menu_content
from src.models import Restaurant, Tab, Column, Section, MenuItem
from src.restaurant_config import detect_restaurant
from src.llm_client import parse_menu, parse_live_menu
from src.column_balancer import balance_menu
from src.html_renderer import render_html
from src.web_scraper import scrape_menu_page
from src.menu_differ import compare_menus, restaurant_to_parsed_menu, ChangeType
import db

# --- Page Config ---
st.set_page_config(
    page_title="Starr Restaurant Website Content Tool",
    page_icon=":fork_and_knife:",
    layout="wide",
)

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600&display=swap');

    #MainMenu {visibility: hidden;}
    header[data-testid="stHeader"] {display: none;}
    footer {visibility: hidden;}

    :root {
        --navy: #1B2A4A;
        --gold: #C5A55A;
        --cream: #F5F3EF;
        --text-dark: #1B2A4A;
        --text-muted: #6B7280;
        --border-light: #DDD9D1;
    }

    .stApp { background-color: var(--cream); }

    .starr-header {
        background: var(--navy);
        border-top: 3px solid var(--gold);
        border-bottom: 3px solid var(--gold);
        padding: 2rem 2.5rem 1.5rem;
        margin: -1rem -1rem 2rem -1rem;
        position: relative;
    }
    .starr-header h1 {
        font-family: 'Playfair Display', Georgia, serif;
        color: #FFFFFF;
        font-size: 1.75rem;
        font-weight: 700;
        margin: 0;
    }
    .starr-header .subtitle {
        font-family: 'DM Sans', sans-serif;
        color: var(--gold);
        font-size: 0.8rem;
        font-weight: 500;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        margin-top: 0.35rem;
    }
    .starr-header .branding {
        font-family: 'DM Sans', sans-serif;
        color: var(--gold);
        font-style: italic;
        font-size: 0.85rem;
        position: absolute;
        bottom: 1rem;
        right: 2.5rem;
    }

    [data-testid="stFileUploader"] {
        border: 2px dashed var(--border-light);
        border-radius: 12px;
        padding: 1rem;
        background: #FFFFFF;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: var(--gold);
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: var(--navy);
        padding: 0 1rem;
        border-radius: 8px 8px 0 0;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #a09888;
        padding: 0.75rem 1.25rem;
        border: none;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"]:hover { color: #FFFFFF; }
    .stTabs [aria-selected="true"] {
        color: #FFFFFF !important;
        border-bottom: 2px solid var(--gold) !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab-panel"] { padding: 0; }

    /* Compact toolbar bar */
    div[data-testid="stVerticalBlock"] > div[data-testid="element-container"]:has(> .toolbar-bar) {
        margin: 0; padding: 0;
    }
    .toolbar-bar {
        background: #E5E1D8;
        margin: -1rem -1rem 0.75rem -1rem;
        padding: 0;
    }
    .toolbar-bar + div[data-testid="column"] { margin-top: 0; }
    /* Target the horizontal block right after toolbar-bar marker */
    div[data-testid="stVerticalBlock"]:has(> div .toolbar-bar) > div[data-testid="stHorizontalBlock"]:first-of-type {
        background: #E5E1D8;
        padding: 0.35rem 0.75rem;
        margin: 0 -1rem 0.5rem -1rem;
        align-items: center;
        gap: 0;
    }
    div[data-testid="stVerticalBlock"]:has(> div .toolbar-bar) > div[data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"] {
        padding: 0 0.25rem !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .toolbar-bar) > div[data-testid="stHorizontalBlock"]:first-of-type button {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.8rem !important;
        padding: 0.3rem 1rem !important;
        white-space: nowrap !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .toolbar-bar) > div[data-testid="stHorizontalBlock"]:first-of-type [data-testid="stBaseButton-secondary"] button {
        background: transparent !important;
        border: 1px solid var(--border-light) !important;
        color: var(--text-muted) !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .toolbar-bar) > div[data-testid="stHorizontalBlock"]:first-of-type [data-testid="stBaseButton-secondary"] button:hover {
        color: #dc3545 !important;
        border-color: #dc3545 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("""
<div class="starr-header">
    <div>
        <h1>Starr Restaurants</h1>
        <div class="subtitle">Restaurant Website Content Tool</div>
    </div>
    <div class="branding">Made{<i>Tooled</i>}</div>
</div>
""", unsafe_allow_html=True)

# --- Config ---
model_id = "claude-sonnet-4-5"

try:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
except Exception:
    api_key = None


# --- Helpers ---
def _process_upload(file_bytes: bytes, filename: str) -> None:
    """Process a .docx file, save to DB, then rerun."""
    with st.status("Preparing your menu...", expanded=True) as status:
        st.write("Reading the menu...")
        raw_text = extract_text(file_bytes)

        st.write("Prepping ingredients...")
        filtered_text = filter_menu_content(raw_text)

        st.write("Identifying the kitchen...")
        config = detect_restaurant(filename, raw_text)
        st.write(f"Found: **{config.name}**")

        progress = st.empty()

        def on_progress(tab_name, index, total):
            progress.write(f"Plating course {index} of {total}: **{tab_name}**...")

        try:
            parsed_menu, _ = parse_menu(
                filtered_text,
                model=model_id,
                api_key=api_key if api_key else None,
                on_progress=on_progress,
            )
        except Exception as e:
            status.update(label="Something burned in the kitchen", state="error")
            st.error(f"API Error: {e}")
            st.stop()

        progress.empty()

        st.write("Arranging the table...")
        restaurant = balance_menu(
            parsed_menu,
            restaurant_name=config.name,
            slug=config.slug,
            accent_color=config.accent_color,
            accent_light=config.accent_light,
        )

        st.write("Saving to database...")
        db.save_menu(config.name, restaurant)

        status.update(label=f"{config.name} — Bon appétit!", state="complete")

    time.sleep(1.5)
    st.rerun()


# --- Edit helpers ---
def _get_edit_data(restaurant_name, restaurant_model):
    """Get or initialize the working edit copy in session state."""
    key = f"edit_data_{restaurant_name}"
    if key not in st.session_state:
        st.session_state[key] = restaurant_model.model_dump()
    return st.session_state[key]


def _save_edit_data(restaurant_name):
    """Reconstruct Restaurant model from session state edit data and save to DB."""
    key = f"edit_data_{restaurant_name}"
    data = st.session_state.get(key)
    if data:
        model = Restaurant.model_validate(data)
        db.save_menu(restaurant_name, model)
        # Clear edit data so it reloads fresh from DB
        del st.session_state[key]


def _render_edit_view(restaurant_name, restaurant_model):
    """Render inline editing UI for a restaurant menu."""
    data = _get_edit_data(restaurant_name, restaurant_model)
    rk = restaurant_name  # short alias for key building

    for t_idx, tab_data in enumerate(data['tabs']):
        with st.expander(f"Tab: {tab_data['label']}", expanded=False):
            tab_data['label'] = st.text_input(
                "Tab Name", value=tab_data['label'],
                key=f"e_{rk}_t{t_idx}_label",
            )
            tab_data['description'] = st.text_area(
                "Tab Description", value=tab_data.get('description') or '',
                key=f"e_{rk}_t{t_idx}_desc", height=68,
            ) or None

            # Flatten sections across columns for display
            flat_sec_idx = 0
            for c_idx, col_data in enumerate(tab_data['columns']):
                for s_idx, sec_data in enumerate(col_data['sections']):
                    st.markdown(f"---")
                    st.markdown(f"**Column {c_idx + 1} — Section {s_idx + 1}**")

                    sec_data['title'] = st.text_input(
                        "Section Title", value=sec_data['title'],
                        key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_title",
                    )
                    sec_data['note'] = st.text_input(
                        "Section Note", value=sec_data.get('note') or '',
                        key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_note",
                    ) or None

                    # Items
                    items_to_remove = []
                    for it_idx, item_data in enumerate(sec_data['items']):
                        cols = st.columns([3, 2, 3, 1])
                        with cols[0]:
                            item_data['name'] = st.text_input(
                                "Name", value=item_data['name'],
                                key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_i{it_idx}_name",
                                label_visibility="collapsed",
                                placeholder="Item name",
                            )
                        with cols[1]:
                            item_data['price'] = st.text_input(
                                "Price", value=item_data.get('price') or '',
                                key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_i{it_idx}_price",
                                label_visibility="collapsed",
                                placeholder="Price",
                            ) or None
                        with cols[2]:
                            item_data['description'] = st.text_input(
                                "Description", value=item_data.get('description') or '',
                                key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_i{it_idx}_desc",
                                label_visibility="collapsed",
                                placeholder="Description / ingredients",
                            ) or None
                        with cols[3]:
                            if st.button("X", key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_i{it_idx}_rm",
                                         type="secondary", help="Remove item"):
                                items_to_remove.append(it_idx)

                    # Process removals (reverse order to keep indices valid)
                    for rm_idx in sorted(items_to_remove, reverse=True):
                        sec_data['items'].pop(rm_idx)
                        st.rerun()

                    if st.button("+ Add Item", key=f"e_{rk}_t{t_idx}_c{c_idx}_s{s_idx}_add",
                                 type="secondary"):
                        sec_data['items'].append({
                            'name': '', 'price': None, 'description': None,
                            'raw': False, 'supplement': None, 'tags': [],
                        })
                        st.rerun()

                    flat_sec_idx += 1

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("Save Changes", key=f"save_{rk}", type="primary"):
            _save_edit_data(restaurant_name)
            st.session_state[f"editing_{rk}"] = False
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key=f"cancel_{rk}", type="secondary"):
            # Discard edit data
            edit_key = f"edit_data_{rk}"
            if edit_key in st.session_state:
                del st.session_state[edit_key]
            st.session_state[f"editing_{rk}"] = False
            st.rerun()


# --- Review Accuracy helpers ---
def _render_diff(diff):
    """Render a MenuDiff as color-coded Streamlit markdown."""
    # Summary bar
    parts = []
    if diff.total_matched:
        parts.append(f":green[{diff.total_matched} matched]")
    if diff.total_modified:
        parts.append(f":orange[{diff.total_modified} changed]")
    if diff.total_removed:
        parts.append(f":red[{diff.total_removed} missing]")
    if diff.total_added:
        parts.append(f":blue[{diff.total_added} new]")
    st.markdown(" &nbsp;|&nbsp; ".join(parts) if parts else "No items to compare")

    # Tab-by-tab breakdown
    for tab_diff in diff.tabs:
        icon = {
            ChangeType.matched: ":green[OK]",
            ChangeType.modified: ":orange[CHANGED]",
            ChangeType.removed: ":red[MISSING]",
            ChangeType.added: ":blue[NEW]",
        }.get(tab_diff.change_type, "")

        with st.expander(f"{icon} **{tab_diff.tab_label}**", expanded=tab_diff.change_type != ChangeType.matched):
            for sec_diff in tab_diff.section_diffs:
                sec_icon = {
                    ChangeType.matched: ":green[OK]",
                    ChangeType.modified: ":orange[~]",
                    ChangeType.removed: ":red[-]",
                    ChangeType.added: ":blue[+]",
                }.get(sec_diff.change_type, "")

                st.markdown(f"**{sec_icon} {sec_diff.section_title}**")

                for item in sec_diff.item_diffs:
                    if item.change_type == ChangeType.matched:
                        st.markdown(f"&emsp; :green[OK] {item.item_name} — {item.doc_price or '—'}")
                    elif item.change_type == ChangeType.modified:
                        st.markdown(f"&emsp; :orange[CHANGED] {item.item_name} — {item.details}")
                    elif item.change_type == ChangeType.removed:
                        st.markdown(f"&emsp; :red[MISSING] {item.item_name} — {item.doc_price or '—'}")
                    elif item.change_type == ChangeType.added:
                        st.markdown(f"&emsp; :blue[NEW] {item.item_name} — {item.live_price or '—'}")


def _run_review(restaurant_name, restaurant_model, menu_url, menu_record):
    """Execute the live-site review flow: scrape → parse → compare → render diff."""
    with st.status("Checking the live menu...", expanded=True) as status:
        st.write("Fetching the live site...")
        try:
            page_text = scrape_menu_page(menu_url)
        except Exception as e:
            status.update(label="Could not fetch the page", state="error")
            st.error(f"Fetch error: {e}")
            return

        st.write(f"Got {len(page_text):,} characters of text")

        progress = st.empty()

        def on_progress(msg):
            progress.write(msg)

        try:
            live_menu = parse_live_menu(
                page_text,
                model=model_id,
                api_key=api_key if api_key else None,
                on_progress=on_progress,
            )
        except Exception as e:
            status.update(label="Parsing the live menu failed", state="error")
            st.error(f"API Error: {e}")
            return

        progress.empty()

        st.write("Comparing menus...")
        doc_menu = restaurant_to_parsed_menu(restaurant_model)
        diff = compare_menus(doc_menu, live_menu)

        # Save URL on success
        db.set_menu_url(restaurant_name, menu_url)

        status.update(label=f"Review complete — {diff.summary}", state="complete")

    st.session_state[f"review_diff_{restaurant_name}"] = diff.model_dump()


# --- Main UI ---
saved_menus = db.list_menus()
tab_names = [m['restaurant'] for m in saved_menus] + ["Upload"]
tabs = st.tabs(tab_names)

# Saved menu tabs
for i, menu_record in enumerate(saved_menus):
    restaurant_name = menu_record['restaurant']
    editing_key = f"editing_{restaurant_name}"

    with tabs[i]:
        restaurant_model = db.load_menu(restaurant_name)

        if st.session_state.get(editing_key, False) and restaurant_model:
            # Edit mode
            _render_edit_view(restaurant_name, restaurant_model)
        else:
            # Preview mode
            reviewing_key = f"reviewing_{restaurant_name}"

            # --- Compact toolbar ---
            if restaurant_model:
                st.markdown('<div class="toolbar-bar"></div>', unsafe_allow_html=True)
                c1, c2, c3, spacer, c4 = st.columns([0.8, 0.7, 1.3, 4, 1.1], gap="small")
                with c1:
                    if st.button("Edit", key=f"edit_{restaurant_name}"):
                        st.session_state[editing_key] = True
                        st.rerun()
                with c2:
                    if st.button("Delete", key=f"del_{restaurant_name}", type="secondary"):
                        db.delete_menu(restaurant_name)
                        st.rerun()
                with c3:
                    if st.button("Review Accuracy", key=f"review_{restaurant_name}"):
                        st.session_state[reviewing_key] = not st.session_state.get(reviewing_key, False)
                        st.rerun()
                with c4:
                    push_val = st.toggle(
                        "Push Data",
                        value=bool(menu_record['push_data']),
                        key=f"push_{restaurant_name}",
                    )
                    if push_val != bool(menu_record['push_data']):
                        db.set_push_data(restaurant_name, push_val)
                        st.rerun()

            # --- Review Accuracy panel ---
            if st.session_state.get(reviewing_key, False) and restaurant_model:
                url_col, btn_col = st.columns([5, 1])
                saved_url = menu_record.get('menu_url') or ""
                with url_col:
                    menu_url = st.text_input(
                        "Restaurant menu page URL",
                        value=saved_url,
                        key=f"review_url_{restaurant_name}",
                        placeholder="https://example.com/restaurant/menu",
                        label_visibility="collapsed",
                    )
                with btn_col:
                    check_clicked = st.button("Check Live Site", key=f"check_{restaurant_name}", type="primary", use_container_width=True)

                if check_clicked:
                    if not menu_url:
                        st.warning("Please enter a URL first.")
                    else:
                        _run_review(restaurant_name, restaurant_model, menu_url, menu_record)

                # Show diff results if available
                diff_key = f"review_diff_{restaurant_name}"
                if diff_key in st.session_state:
                    from src.menu_differ import MenuDiff
                    diff = MenuDiff.model_validate(st.session_state[diff_key])
                    _render_diff(diff)

            # --- Menu preview ---
            if restaurant_model:
                html_content = render_html(restaurant_model)
                components.html(html_content, height=800, scrolling=True)

# Upload tab
with tabs[-1]:
    uploaded_file = st.file_uploader(
        "Drop a .docx menu file here",
        type=["docx"],
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        _process_upload(uploaded_file.read(), uploaded_file.name)
