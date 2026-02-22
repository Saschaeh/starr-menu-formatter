"""Starr Menu CMS Formatter — Streamlit App."""

import streamlit as st
import streamlit.components.v1 as components

from src.docx_parser import extract_text, filter_menu_content
from src.restaurant_config import detect_restaurant
from src.llm_client import parse_menu
from src.column_balancer import balance_menu
from src.html_renderer import render_html

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

# --- Upload Section ---
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

        # Progress callback for per-tab parsing
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

        status.update(label="Done!", state="complete")

    # --- HTML Preview ---
    st.markdown('<div class="section-heading">Menu Preview</div><hr class="gold-rule">', unsafe_allow_html=True)
    components.html(html_output, height=800, scrolling=True)

    # --- Download ---
    st.download_button(
        label="Download HTML",
        data=html_output,
        file_name=f"{config.slug}-menu.html",
        mime="text/html",
    )
