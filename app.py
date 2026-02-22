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

# --- Sidebar ---
st.sidebar.title("Settings")

model_choice = st.sidebar.selectbox(
    "Claude Model",
    options=[
        ("claude-sonnet-4-5-20250514", "Sonnet 4.5 (Recommended)"),
        ("claude-haiku-4-5-20251001", "Haiku 4.5 (Faster / Cheaper)"),
    ],
    format_func=lambda x: x[1],
    index=0,
)
model_id = model_choice[0]

api_key = st.sidebar.text_input(
    "Anthropic API Key",
    type="password",
    help="Leave blank to use ANTHROPIC_API_KEY environment variable or Streamlit secrets.",
)

# Try to get API key from Streamlit secrets if not provided
if not api_key:
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", None)
    except Exception:
        api_key = None

debug_mode = st.sidebar.toggle("Debug Mode", value=False)

# --- Main ---
st.title("Starr Menu CMS Formatter")
st.markdown("Upload a restaurant menu `.docx` file to get a CMS-ready HTML preview.")

uploaded_file = st.file_uploader(
    "Choose a .docx file",
    type=["docx"],
    help="Upload a Starr Restaurants menu document",
)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name

    with st.status("Processing menu...", expanded=True) as status:
        # Step 1: Extract text
        st.write("Extracting text from document...")
        raw_text = extract_text(file_bytes)

        # Step 2: Filter menu content
        st.write("Filtering menu content...")
        filtered_text = filter_menu_content(raw_text)

        # Step 3: Detect restaurant
        st.write("Detecting restaurant...")
        config = detect_restaurant(filename, raw_text)
        st.write(f"Detected: **{config.name}**")

        # Step 4: Call Claude API
        st.write(f"Parsing with Claude ({model_id.split('-')[1].title()})...")
        try:
            parsed_menu, raw_json = parse_menu(
                filtered_text,
                model=model_id,
                api_key=api_key if api_key else None,
            )
        except Exception as e:
            status.update(label="Error", state="error")
            st.error(f"API Error: {e}")
            st.stop()

        # Step 5: Balance columns
        st.write("Balancing columns...")
        restaurant = balance_menu(
            parsed_menu,
            restaurant_name=config.name,
            slug=config.slug,
            accent_color=config.accent_color,
            accent_light=config.accent_light,
        )

        # Step 6: Render HTML
        st.write("Rendering HTML preview...")
        html_output = render_html(restaurant)

        status.update(label="Done!", state="complete")

    # --- Summary ---
    st.divider()
    cols = st.columns(len(restaurant.tabs) + 1)
    cols[0].metric("Tabs", len(restaurant.tabs))
    for i, tab in enumerate(restaurant.tabs):
        item_count = sum(
            len(item.name) > 0
            for col in tab.columns
            for sec in col.sections
            for item in sec.items
        )
        col_count = len(tab.columns)
        cols[i + 1].metric(
            tab.label,
            f"{item_count} items",
            f"{col_count} col{'s' if col_count > 1 else ''}",
        )

    # --- HTML Preview ---
    st.subheader("Preview")
    components.html(html_output, height=800, scrolling=True)

    # --- Download ---
    st.download_button(
        label="Download HTML",
        data=html_output,
        file_name=f"{config.slug}-menu.html",
        mime="text/html",
    )

    # --- Debug Mode ---
    if debug_mode:
        st.divider()
        st.subheader("Debug Info")

        with st.expander("Extracted Text (Raw)", expanded=False):
            st.text(raw_text)

        with st.expander("Filtered Text (Sent to LLM)", expanded=False):
            st.text(filtered_text)

        with st.expander("LLM Raw JSON Response", expanded=False):
            st.code(raw_json, language="json")

        with st.expander("Parsed Restaurant Model", expanded=False):
            st.json(restaurant.model_dump())
