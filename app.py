"""Starr Menu CMS Formatter — Streamlit App."""

import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.docx_parser import extract_text, filter_menu_content
from src.restaurant_config import detect_restaurant
from src.llm_client import parse_menu
from src.column_balancer import balance_menu
from src.html_renderer import render_html

OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

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
    .stTabs [data-baseweb="tab-panel"] { padding: 1rem 0; }

    /* Subtle delete button — right-aligned below preview */
    .delete-row {
        display: flex;
        justify-content: flex-end;
        margin-top: 0.5rem;
    }
    .stTabs [data-baseweb="tab-panel"] button[kind="secondary"] {
        background: transparent;
        border: none;
        color: var(--text-muted);
        font-family: 'DM Sans', sans-serif;
        font-size: 0.75rem;
        padding: 0.25rem 0;
        opacity: 0.5;
    }
    .stTabs [data-baseweb="tab-panel"] button[kind="secondary"]:hover {
        color: #dc3545;
        opacity: 1;
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
def _get_saved_menus() -> dict[str, Path]:
    menus = {}
    for f in sorted(OUTPUTS_DIR.glob("*.html")):
        name = f.stem.replace("-menu", "").replace("-", " ").title()
        menus[name] = f
    return menus


def _process_upload(file_bytes: bytes, filename: str) -> None:
    """Process a .docx file, save HTML to outputs/, then rerun."""
    with st.status("Processing menu...", expanded=True) as status:
        st.write("Extracting text...")
        raw_text = extract_text(file_bytes)

        st.write("Filtering content...")
        filtered_text = filter_menu_content(raw_text)

        st.write("Detecting restaurant...")
        config = detect_restaurant(filename, raw_text)
        st.write(f"Detected: **{config.name}**")

        progress = st.empty()

        def on_progress(tab_name, index, total):
            progress.write(f"Parsing tab {index}/{total}: **{tab_name}**...")

        try:
            parsed_menu, _ = parse_menu(
                filtered_text,
                model=model_id,
                api_key=api_key if api_key else None,
                on_progress=on_progress,
            )
        except Exception as e:
            status.update(label="Error", state="error")
            st.error(f"API Error: {e}")
            st.stop()

        progress.empty()

        st.write("Balancing columns...")
        restaurant = balance_menu(
            parsed_menu,
            restaurant_name=config.name,
            slug=config.slug,
            accent_color=config.accent_color,
            accent_light=config.accent_light,
        )

        st.write("Rendering...")
        html_output = render_html(restaurant)

        path = OUTPUTS_DIR / f"{config.slug}-menu.html"
        path.write_text(html_output, encoding="utf-8")

        status.update(label=f"{config.name} — Complete!", state="complete")

    time.sleep(1.5)
    st.rerun()


# --- Main UI ---
saved_menus = _get_saved_menus()
tab_names = list(saved_menus.keys()) + ["Upload"]
tabs = st.tabs(tab_names)

# Saved menu tabs
for i, (name, path) in enumerate(saved_menus.items()):
    with tabs[i]:
        html_content = path.read_text(encoding="utf-8")
        components.html(html_content, height=800, scrolling=True)

        _, col_del = st.columns([9, 1])
        with col_del:
            if st.button("Delete this menu", key=f"del_{name}", type="secondary"):
                path.unlink()
                st.rerun()

# Upload tab
with tabs[-1]:
    uploaded_file = st.file_uploader(
        "Drop a .docx menu file here",
        type=["docx"],
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        _process_upload(uploaded_file.read(), uploaded_file.name)
