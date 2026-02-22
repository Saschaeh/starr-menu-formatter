"""Starr Menu CMS Formatter — Streamlit App."""

import json
import os
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
    page_title="Starr Menu CMS Formatter",
    page_icon=":fork_and_knife:",
    layout="wide",
)

# --- Custom CSS matching Starr brand ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600&display=swap');

    /* Hide default Streamlit header/footer */
    #MainMenu {visibility: hidden;}
    header[data-testid="stHeader"] {display: none;}
    footer {visibility: hidden;}

    /* Root vars */
    :root {
        --navy: #1B2A4A;
        --gold: #C5A55A;
        --cream: #F5F3EF;
        --text-dark: #1B2A4A;
        --text-muted: #6B7280;
        --border-light: #DDD9D1;
    }

    /* Background */
    .stApp {
        background-color: var(--cream);
    }

    /* Branded header bar */
    .starr-header {
        background: var(--navy);
        border-top: 4px solid var(--gold);
        border-bottom: 4px solid var(--gold);
        padding: 1.75rem 2.5rem;
        margin: -1rem -1rem 2rem -1rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .starr-header h1 {
        font-family: 'Playfair Display', Georgia, serif;
        color: #FFFFFF;
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.01em;
    }
    .starr-header .subtitle {
        font-family: 'DM Sans', sans-serif;
        color: var(--gold);
        font-size: 0.85rem;
        font-weight: 500;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        margin-top: 0.25rem;
    }
    .starr-header .branding {
        font-family: 'DM Sans', sans-serif;
        color: var(--gold);
        font-style: italic;
        font-size: 0.9rem;
    }

    /* Section headings */
    .section-heading {
        font-family: 'Playfair Display', Georgia, serif;
        color: var(--navy);
        font-size: 1.5rem;
        font-weight: 700;
        margin: 1.5rem 0 0.25rem 0;
    }
    .gold-rule {
        border: none;
        border-top: 3px solid var(--gold);
        margin: 0 0 1.5rem 0;
    }

    /* File uploader styling */
    [data-testid="stFileUploader"] {
        border: 2px dashed var(--border-light);
        border-radius: 12px;
        padding: 1rem;
        background: #FFFFFF;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: var(--gold);
    }

    /* Buttons */
    .stDownloadButton > button {
        background: var(--navy) !important;
        color: #FFFFFF !important;
        border: 2px solid var(--navy) !important;
        border-radius: 6px;
        font-family: 'DM Sans', sans-serif;
        font-weight: 600;
        letter-spacing: 0.04em;
        padding: 0.5rem 2rem;
        transition: all 0.2s;
    }
    .stDownloadButton > button:hover {
        background: transparent !important;
        color: var(--navy) !important;
        border-color: var(--navy) !important;
    }

    /* Status expander */
    [data-testid="stStatus"] {
        background: #FFFFFF;
        border: 1px solid var(--border-light);
        border-radius: 8px;
    }

    /* Divider */
    hr {
        border-color: var(--border-light) !important;
    }

    /* Subheader */
    .stMarkdown h3 {
        font-family: 'Playfair Display', Georgia, serif;
        color: var(--navy);
    }

    /* Streamlit tabs styling */
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
    .stTabs [data-baseweb="tab"]:hover {
        color: #FFFFFF;
    }
    .stTabs [aria-selected="true"] {
        color: #FFFFFF !important;
        border-bottom: 2px solid var(--gold) !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# --- Branded Header ---
st.markdown("""
<div class="starr-header">
    <div>
        <h1>Starr Restaurants</h1>
        <div class="subtitle">Menu CMS Formatter</div>
    </div>
    <div class="branding">Made{<i>Tooled</i>}</div>
</div>
""", unsafe_allow_html=True)

# --- Config (from secrets / env only) ---
model_id = "claude-sonnet-4-5"

try:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
except Exception:
    api_key = None


# --- Helper: load saved menus ---
def _get_saved_menus() -> dict[str, Path]:
    """Return {display_name: path} for saved HTML files in outputs/."""
    menus = {}
    for f in sorted(OUTPUTS_DIR.glob("*.html")):
        # Turn slug into display name: "makoto-menu.html" → "Makoto"
        name = f.stem.replace("-menu", "").replace("-", " ").title()
        menus[name] = f
    return menus


def _save_menu(slug: str, html: str) -> None:
    """Save processed HTML to outputs/."""
    path = OUTPUTS_DIR / f"{slug}-menu.html"
    path.write_text(html, encoding="utf-8")


# --- Build tab list ---
saved_menus = _get_saved_menus()
tab_names = list(saved_menus.keys()) + ["+ Upload New"]

if tab_names == ["+ Upload New"]:
    # No saved menus yet — just show upload
    st.markdown('<div class="section-heading">Upload Menu Document</div><hr class="gold-rule">', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drop a .docx menu file here",
        type=["docx"],
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        filename = uploaded_file.name

        with st.status("Processing menu...", expanded=True) as status:
            st.write("Extracting text from document...")
            raw_text = extract_text(file_bytes)

            st.write("Filtering menu content...")
            filtered_text = filter_menu_content(raw_text)

            st.write("Detecting restaurant...")
            config = detect_restaurant(filename, raw_text)
            st.write(f"Detected: **{config.name}**")

            status_placeholder = st.empty()

            def on_progress(tab_name, index, total):
                status_placeholder.write(f"Parsing tab {index}/{total}: **{tab_name}**...")

            try:
                parsed_menu, raw_json = parse_menu(
                    filtered_text,
                    model=model_id,
                    api_key=api_key if api_key else None,
                    on_progress=on_progress,
                )
            except Exception as e:
                status.update(label="Error", state="error")
                st.error(f"API Error: {e}")
                st.stop()

            status_placeholder.empty()

            st.write("Balancing columns...")
            restaurant = balance_menu(
                parsed_menu,
                restaurant_name=config.name,
                slug=config.slug,
                accent_color=config.accent_color,
                accent_light=config.accent_light,
            )

            st.write("Rendering HTML preview...")
            html_output = render_html(restaurant)

            # Save to outputs/
            _save_menu(config.slug, html_output)

            status.update(label="Done!", state="complete")

        components.html(html_output, height=800, scrolling=True)

        st.download_button(
            label="Download HTML",
            data=html_output,
            file_name=f"{config.slug}-menu.html",
            mime="text/html",
        )

else:
    # Show tabs for saved menus + upload
    tabs = st.tabs(tab_names)

    # Saved menu tabs
    for i, (name, path) in enumerate(saved_menus.items()):
        with tabs[i]:
            html_content = path.read_text(encoding="utf-8")
            components.html(html_content, height=800, scrolling=True)

            col1, col2 = st.columns([1, 5])
            with col1:
                st.download_button(
                    label="Download HTML",
                    data=html_content,
                    file_name=path.name,
                    mime="text/html",
                    key=f"dl_{name}",
                )
            with col2:
                if st.button(f"Delete", key=f"del_{name}", type="secondary"):
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
            file_bytes = uploaded_file.read()
            filename = uploaded_file.name

            with st.status("Processing menu...", expanded=True) as status:
                st.write("Extracting text from document...")
                raw_text = extract_text(file_bytes)

                st.write("Filtering menu content...")
                filtered_text = filter_menu_content(raw_text)

                st.write("Detecting restaurant...")
                config = detect_restaurant(filename, raw_text)
                st.write(f"Detected: **{config.name}**")

                status_placeholder = st.empty()

                def on_progress(tab_name, index, total):
                    status_placeholder.write(f"Parsing tab {index}/{total}: **{tab_name}**...")

                try:
                    parsed_menu, raw_json = parse_menu(
                        filtered_text,
                        model=model_id,
                        api_key=api_key if api_key else None,
                        on_progress=on_progress,
                    )
                except Exception as e:
                    status.update(label="Error", state="error")
                    st.error(f"API Error: {e}")
                    st.stop()

                status_placeholder.empty()

                st.write("Balancing columns...")
                restaurant = balance_menu(
                    parsed_menu,
                    restaurant_name=config.name,
                    slug=config.slug,
                    accent_color=config.accent_color,
                    accent_light=config.accent_light,
                )

                st.write("Rendering HTML preview...")
                html_output = render_html(restaurant)

                # Save to outputs/
                _save_menu(config.slug, html_output)

                status.update(label="Done!", state="complete")

            components.html(html_output, height=800, scrolling=True)

            st.download_button(
                label="Download HTML",
                data=html_output,
                file_name=f"{config.slug}-menu.html",
                mime="text/html",
                key="dl_new",
            )

            st.info("Menu saved! Refresh to see it in the tabs above.")
