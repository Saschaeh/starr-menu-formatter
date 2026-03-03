"""Starr Menu CMS Formatter — Streamlit App."""

import copy
import time
from collections import defaultdict
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from src.docx_parser import extract_text, filter_menu_content
from src.models import Restaurant, Tab, Column, Section, MenuItem
from src.restaurant_config import detect_restaurant, get_city, display_name, CITY_ORDER
from src.llm_client import parse_menu, parse_live_menu
from src.column_balancer import balance_menu
from src.html_renderer import render_html
from src.web_scraper import scrape_menu_page
from src.menu_differ import compare_menus, restaurant_to_parsed_menu, apply_diff, ChangeType
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

    /* Give all form elements white backgrounds so they don't inherit cream */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"],
    [data-testid="stNumberInput"] input {
        background-color: #FFFFFF !important;
    }
    /* Primary buttons — gold brand color */
    .stButton button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background-color: var(--gold) !important;
        border-color: var(--gold) !important;
        color: #FFFFFF !important;
    }
    /* Secondary buttons — clean white with border */
    .stButton button[kind="secondary"],
    button[data-testid="stBaseButton-secondary"] {
        background-color: #FFFFFF !important;
        border: 1px solid var(--border-light) !important;
        color: var(--text-dark) !important;
    }
    /* Info/alert boxes */
    [data-testid="stAlert"] {
        background: #FFFFFF;
        border-radius: 8px;
    }

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

    /* Upload status widget */
    [data-testid="stStatusWidget"] {
        background: #FFFFFF;
        border: 1px solid var(--border-light);
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    [data-testid="stStatusWidget"] [data-testid="stMarkdown"] {
        font-family: 'DM Sans', sans-serif;
    }

    /* Toolbar bar */
    [class*="st-key-toolbar_"] {
        background: #E8EEF4;
        border-bottom: 1px solid #D0DAE4;
        padding: 0.4rem 0.5rem;
        margin-bottom: 0.5rem;
    }
    [class*="st-key-toolbar_"] [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }
    [class*="st-key-toolbar_"] button {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.75rem !important;
        padding: 0.2rem 0.5rem !important;
        min-height: 0 !important;
    }
    [class*="st-key-toolbar_"] [data-testid="stColumn"]:last-child {
        display: flex;
        justify-content: flex-end;
    }
    [class*="st-key-toolbar_"] [data-testid="stColumn"]:last-child label {
        flex-direction: row-reverse !important;
        gap: 0.4rem;
    }

    /* Dashboard — tighter column gap */
    [class*="st-key-dash_grid"] [data-testid="stHorizontalBlock"] {
        gap: 1.5rem !important;
    }
    /* City label — compact uppercase */
    .city-label {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin: 0 0 0.15rem 0;
        padding: 0;
    }
    .city-group { margin-bottom: 1rem; }
    /* Restaurant row buttons — stripped to plain text */
    [class*="st-key-r_"] {
        margin: 0 !important;
        padding: 0 !important;
    }
    [class*="st-key-r_"] [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0 !important;
        margin: 0 !important;
    }
    [class*="st-key-r_"] button {
        background: none !important;
        border: none !important;
        box-shadow: none !important;
        text-align: left !important;
        padding: 0.12rem 0.25rem !important;
        min-height: 0 !important;
        height: auto !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: var(--text-dark) !important;
        width: 100% !important;
        justify-content: flex-start !important;
        border-radius: 3px !important;
        line-height: 1.3 !important;
    }
    [class*="st-key-r_"] button:hover {
        color: var(--gold) !important;
        background: rgba(197, 165, 90, 0.08) !important;
    }
    [class*="st-key-r_"] button p {
        font-size: 0.88rem !important;
        margin: 0 !important;
        line-height: 1.3 !important;
    }
    /* Back button */
    [class*="st-key-back_btn"] button {
        background: none !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        min-height: 0 !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.85rem !important;
        color: var(--text-muted) !important;
    }
    [class*="st-key-back_btn"] button:hover {
        color: var(--gold) !important;
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
def _process_upload(file_bytes: bytes, filename: str, file_id: str) -> None:
    """Process a .docx file, save to DB, then rerun.

    Uses file_id to avoid re-processing the same upload across Streamlit reruns.
    """
    # Already processed this exact upload — nothing to do
    if st.session_state.get("_processed_file_id") == file_id:
        return

    # Mid-processing rerun — show a simple wait message instead of duplicating
    if st.session_state.get("_upload_processing"):
        st.info("Processing your menu — please wait...")
        st.stop()

    st.session_state["_upload_processing"] = True

    try:
        with st.status("Preparing your menu...", expanded=True) as status:
            bar = st.progress(0, text="Reading the menu...")
            raw_text = extract_text(file_bytes)

            bar.progress(5, text="Prepping ingredients...")
            filtered_text = filter_menu_content(raw_text)

            bar.progress(10, text="Identifying the kitchen...")
            config = detect_restaurant(filename, raw_text)

            # Check for existing restaurant — warn before spending API credits
            existing = db.load_menu(config.name)
            if existing and not st.session_state.get("_overwrite_confirmed"):
                status.update(label=f"**{config.name}** already exists", state="error")
                st.warning(
                    f"**{config.name}** is already in the database. "
                    "Re-uploading will overwrite the existing menu."
                )
                if st.button("Overwrite Existing Menu", type="primary"):
                    st.session_state["_overwrite_confirmed"] = True
                    st.rerun()
                st.session_state["_upload_processing"] = False
                st.stop()

            # Clear overwrite flag once we proceed
            st.session_state.pop("_overwrite_confirmed", None)

            bar.progress(15, text=f"Found **{config.name}** — parsing tabs...")

            def on_progress(tab_name, index, total):
                # LLM parsing spans 15%–85%
                pct = 15 + int((index / total) * 70)
                bar.progress(pct, text=f"Plating course {index} of {total}: **{tab_name}**...")

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
                st.session_state["_upload_processing"] = False
                st.stop()

            bar.progress(90, text="Arranging the table...")
            restaurant = balance_menu(
                parsed_menu,
                restaurant_name=config.name,
                slug=config.slug,
                accent_color=config.accent_color,
                accent_light=config.accent_light,
            )

            bar.progress(95, text="Saving to database...")
            db.save_menu(config.name, restaurant)

            bar.progress(100, text="Done!")
            status.update(label=f"{config.name} — Bon appétit!", state="complete")

        time.sleep(1.5)
    finally:
        st.session_state["_upload_processing"] = False

    # Mark this file as done so reruns don't reprocess it
    st.session_state["_processed_file_id"] = file_id
    # Auto-select the newly uploaded restaurant
    st.session_state["selected_restaurant"] = config.name
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
    st.session_state[f"review_live_{restaurant_name}"] = live_menu.model_dump()


# --- Tab rendering helper ---
def render_tab_html(restaurant, tab):
    """Render a single tab as a self-contained HTML fragment for inline preview."""
    import os
    from jinja2 import Environment, FileSystemLoader
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("menu_tab_template.html")
    return template.render(
        tab=tab,
        accent_color=restaurant.accent_color,
        accent_light=restaurant.accent_light,
    )


# --- Height estimation helper ---
def _estimate_tab_height(tab):
    """Estimate pixel height for a single menu tab's content."""
    max_col_height = 0
    for col in tab.columns:
        col_height = 80  # column padding + label
        for sec in col.sections:
            col_height += 60  # section title + margin
            if sec.note:
                col_height += 30
            for item in sec.items:
                h = 40  # name + price row
                if item.description:
                    h += 20
                if item.tags:
                    h += 24
                col_height += h
        max_col_height = max(max_col_height, col_height)
    height = max_col_height + 80  # body padding
    if tab.description:
        height += 70
    if tab.footnote:
        height += 80
    return max(300, height)


# --- Main UI ---
saved_menus = db.list_menus()
restaurant_names = [m['restaurant'] for m in saved_menus]

# Two-state UI: dashboard (no selection) vs detail (restaurant selected)
selected_restaurant = st.session_state.get("selected_restaurant")

if (selected_restaurant
        and selected_restaurant != "__upload__"
        and selected_restaurant not in restaurant_names):
    # Restaurant was deleted or doesn't exist — clear selection
    selected_restaurant = None
    st.session_state.pop("selected_restaurant", None)

if selected_restaurant is None:
    # --- Dashboard view ---
    def _fmt_date(iso_str):
        """Format an ISO date string as short date like 'Mar 1'."""
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return f"{dt.strftime('%b')} {dt.day}"
        except Exception:
            return ""

    # Upload button top-right
    _, btn_col = st.columns([5, 1])
    with btn_col:
        if st.button("+ Upload Menu", type="primary", key="upload_btn", use_container_width=True):
            st.session_state["selected_restaurant"] = "__upload__"
            st.rerun()

    # Group restaurants by city
    city_groups = defaultdict(list)
    for m in saved_menus:
        city = get_city(m['restaurant'])
        city_groups[city].append(m)

    # Build ordered city list (CITY_ORDER first, then "Other" if any)
    ordered_cities = [c for c in CITY_ORDER if c in city_groups]
    if "Other" in city_groups:
        ordered_cities.append("Other")

    if ordered_cities:
        # Distribute cities across 3 columns to balance height
        city_heights = []
        for city in ordered_cities:
            h = 1 + len(city_groups[city])
            city_heights.append((city, h))

        col_assignments = [[] for _ in range(3)]
        col_heights = [0] * 3
        for city, h in city_heights:
            shortest = col_heights.index(min(col_heights))
            col_assignments[shortest].append(city)
            col_heights[shortest] += h

        with st.container(key="dash_grid"):
            cols = st.columns(3)
            for col_idx, col in enumerate(cols):
                with col:
                    for city in col_assignments[col_idx]:
                        st.markdown(
                            f'<div class="city-group"><p class="city-label">{city}</p></div>',
                            unsafe_allow_html=True,
                        )
                        for m in city_groups[city]:
                            name = m['restaurant']
                            dname = display_name(name)
                            date_str = _fmt_date(m.get('updated_at'))
                            label = f"{dname}  ·  {date_str}" if date_str else dname
                            with st.container(key=f"r_{name}"):
                                if st.button(label, key=f"go_{name}"):
                                    st.session_state["selected_restaurant"] = name
                                    st.rerun()

elif selected_restaurant == "__upload__":
    # --- Upload view ---
    with st.container(key="back_btn"):
        if st.button("← All Restaurants", key="back_from_upload"):
            st.session_state.pop("selected_restaurant", None)
            st.rerun()

    uploaded_file = st.file_uploader(
        "Drop a .docx menu file here",
        type=["docx"],
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        _process_upload(uploaded_file.read(), uploaded_file.name, uploaded_file.file_id)

else:
    # --- Restaurant detail view ---
    restaurant_name = selected_restaurant
    with st.container(key="back_btn"):
        if st.button("← All Restaurants", key="back_to_dash"):
            st.session_state.pop("selected_restaurant", None)
            st.rerun()
    menu_record = next(m for m in saved_menus if m['restaurant'] == restaurant_name)
    editing_key = f"editing_{restaurant_name}"
    restaurant_model = db.load_menu(restaurant_name)

    if st.session_state.get(editing_key, False) and restaurant_model:
        # Edit mode
        _render_edit_view(restaurant_name, restaurant_model)
    else:
        # Preview mode
        reviewing_key = f"reviewing_{restaurant_name}"

        # --- Compact toolbar ---
        if restaurant_model:
            with st.container(key=f"toolbar_{restaurant_name}"):
                c1, c2, c3, _, c4 = st.columns([1, 1, 1, 5, 1])
                with c1:
                    if st.button("Edit", key=f"edit_{restaurant_name}", use_container_width=True):
                        st.session_state[editing_key] = True
                        st.rerun()
                with c2:
                    confirm_key = f"confirm_del_{restaurant_name}"
                    if st.session_state.get(confirm_key, False):
                        # Confirmation step — show "Confirm?" in red
                        if st.button("Confirm?", key=f"del_confirm_{restaurant_name}", type="primary", use_container_width=True):
                            db.delete_menu(restaurant_name)
                            st.session_state.pop(confirm_key, None)
                            st.session_state.pop("selected_restaurant", None)
                            st.rerun()
                    else:
                        if st.button("Delete", key=f"del_{restaurant_name}", type="secondary", use_container_width=True):
                            st.session_state[confirm_key] = True
                            st.rerun()
                with c3:
                    if st.button("Review Accuracy", key=f"review_{restaurant_name}", use_container_width=True):
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
                from src.models import ParsedMenu
                diff = MenuDiff.model_validate(st.session_state[diff_key])
                _render_diff(diff)

                # Apply Changes button — only when there are actual changes
                has_changes = (diff.total_modified + diff.total_added + diff.total_removed) > 0
                live_key = f"review_live_{restaurant_name}"
                if has_changes and live_key in st.session_state:
                    # Show destructive change warning if items/sections/tabs are being removed
                    if diff.total_removed > 0:
                        st.warning(
                            f"This will **remove {diff.total_removed} item(s)** from the menu. "
                            "A backup will be saved automatically."
                        )
                    if st.button("Apply Changes", key=f"apply_{restaurant_name}", type="primary"):
                        # Save backup of current state before modifying
                        backup_key = f"backup_{restaurant_name}"
                        st.session_state[backup_key] = restaurant_model.model_dump_json()

                        live_menu = ParsedMenu.model_validate(st.session_state[live_key])
                        doc_menu = restaurant_to_parsed_menu(restaurant_model)
                        updated_menu = apply_diff(doc_menu, diff, live_menu)
                        updated_restaurant = balance_menu(
                            updated_menu,
                            restaurant_name=restaurant_model.name,
                            slug=restaurant_model.slug,
                            accent_color=restaurant_model.accent_color,
                            accent_light=restaurant_model.accent_light,
                        )
                        db.save_menu(restaurant_name, updated_restaurant)
                        # Clear review state
                        del st.session_state[diff_key]
                        del st.session_state[live_key]
                        st.rerun()

        # --- Undo button for review changes ---
        backup_key = f"backup_{restaurant_name}"
        if backup_key in st.session_state:
            if st.button("Undo Last Review Changes", key=f"undo_{restaurant_name}", type="secondary"):
                restored = Restaurant.model_validate_json(st.session_state[backup_key])
                db.save_menu(restaurant_name, restored)
                del st.session_state[backup_key]
                st.rerun()

        # --- Menu preview (per-tab, no iframe scroll) ---
        if restaurant_model and restaurant_model.tabs:
            if len(restaurant_model.tabs) > 1:
                tab_labels = [t.label for t in restaurant_model.tabs]
                menu_tabs = st.tabs(tab_labels)
                for i, tab in enumerate(restaurant_model.tabs):
                    with menu_tabs[i]:
                        tab_html = render_tab_html(restaurant_model, tab)
                        h = _estimate_tab_height(tab)
                        components.html(tab_html, height=h, scrolling=False)
            else:
                # Single tab — render directly, no tab bar needed
                tab = restaurant_model.tabs[0]
                tab_html = render_tab_html(restaurant_model, tab)
                h = _estimate_tab_height(tab)
                components.html(tab_html, height=h, scrolling=False)
