# =========================
# Imports
# =========================
import streamlit as st
from datetime import date
# from openbis_utils.connection import connect_openbis


from helpers.tabs_materials import (
    apply_button_css,
    tab_connection,
    tab_general_information,
    tab_input_mode,
    tab_ceramic,
    tab_binder_multi,
    tab_solvent,
    tab_disp,
    tab_pi_multi,
    tab_additive,
    tab_summary,
    tab_export_openbis,
)
from helpers.formulation_model import Formulation
from config import VERSION, APP_NAME, get_default_openbis_space


# =========================
# Constants
# =========================
today = date.today()

# Single-item material categories (used for initialization)
SINGLE_ITEM_CATEGORIES = [
    "Ceramic",
    "Solvent",
    "Dispersing Agent",
    "Additive",
]

# All material categories (used for tabs display)
CATEGORIES = [
    "Ceramic",
    "Binder",
    "Solvent",
    "Dispersing Agent",
    "Photo-Initiator",
    "Additive",
]

# =========================
# Helper Functions
# =========================
def init_openbis_state():
    """Initialize OpenBIS connection state"""
    return {
        "connection": {"o": None, "pat_invalid": False},
        "available": {"spaces": [], "projects": [], "collections": []},
    }


def init_ui_state():
    """Initialize UI state"""
    return {
        "input_mode": "Camera",
        "delete_message_binder": "",
        "custom_resin_name": None,
        "first_time_popup_acknowledged": False,
    }


def init_experiment_state():
    """Initialize experiment state with proper nested structure"""
    return {
        "general_info": {
            "purpose": "2PP Feedstocks",
            "place": "FB",
            "openbis_path": {
                "space": get_default_openbis_space(),
                "project": "",
                "collection": "",
                "full_path": "",
            },
        },
        "materials": {
            "Ceramic": {},
            "Solvent": {},
            "Dispersing Agent": {},
            "Additive": {},
            "Binder": {"items": [], "total_mass": 0},
            "Photo-Initiator": {"items": []},
        },
        # Source of truth for formulation data going forward (see CLAUDE.md).
        # `materials` above remains for backward compatibility with existing export code
        # until it is synchronized from `formulation` (Layer 9).
        "formulation": Formulation(),
        "excel_bytes": None,
    }


def safe_tab_call(tab_func, *args):
    """Safely call a tab function and keep sidebar visible even if errors occur"""
    try:
        tab_func(*args)
    except Exception as e:
        # Display error but keep sidebar visible (don't use st.stop())
        st.error(f"❌ Tab error: {str(e)}")
        st.info(
            "💡 The sidebar should still be visible. Try another tab or refresh the page."
        )
        import traceback

        with st.expander("Debug info"):
            st.code(traceback.format_exc())


def main():
    """
    Main Streamlit app for OpenBIS Chemical Data Importer
    """
    # Page configuration
    st.set_page_config(
        page_title="Resin Formulation Manager",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Apply custom CSS for button styling
    apply_button_css()

    # Main title and description
    st.title("Resin Formulation Manager - Multi-Ceramics")
    st.write(
        "Manage resin formulations, track material compositions, and export experimental data to OpenBIS. "
        "Follow the tabs to compose and document your material formulations."
    )

    # =========================
    # SESSION INITIALIZATION
    # =========================
    # Initialize OpenBIS connection state
    if "openbis" not in st.session_state:
        st.session_state["openbis"] = init_openbis_state()

    # Initialize UI state
    if "ui" not in st.session_state:
        st.session_state["ui"] = init_ui_state()

    # Initialize experiment data
    if "experiment" not in st.session_state:
        st.session_state["experiment"] = init_experiment_state()

    # Clean up orphaned keys (old structure that was removed)
    orphaned_keys = [
        "general_purpose",  # Duplicate of experiment.general_info.purpose
        "general_place",  # Duplicate of experiment.general_info.place
        "project_selectbox",  # Duplicate of experiment.general_info.openbis_path.project
        "collection_selectbox",  # Duplicate of experiment.general_info.openbis_path.collection
        "project_dropdown",  # Duplicate of experiment.general_info.openbis_path.project
        "collection_dropdown",  # Duplicate of experiment.general_info.openbis_path.collection
        "experiment_excel_bytes",  # Moved to experiment.excel_bytes
    ]
    for key in orphaned_keys:
        st.session_state.pop(key, None)

    # =========================
    # TABS
    # =========================
    tab_labels = (
        ["🔑 Connection", "Input Mode", "General Information"]
        + CATEGORIES
        + ["Summary", "Export to openbis"]
    )
    tabs = st.tabs(tab_labels)

    # =========================
    # TAB 0 — CONNECTION
    # =========================
    with tabs[0]:
        tab_connection()

    with tabs[1]:
        tab_input_mode()

    with tabs[2]:
        tab_general_information(st.session_state["openbis"]["connection"]["o"])

    # =========================
    # CATEGORY TABS
    # =========================
    TAB_HANDLERS = {
        "Ceramic": tab_ceramic,
        "Binder": tab_binder_multi,
        "Solvent": tab_solvent,
        "Dispersing Agent": tab_disp,
        "Photo-Initiator": tab_pi_multi,
        "Additive": tab_additive,
    }

    for category, tab in zip(CATEGORIES, tabs[3 : 3 + len(CATEGORIES)]):
        with tab:
            TAB_HANDLERS[category](st.session_state["openbis"]["connection"]["o"])

    with tabs[-2]:
        tab_summary(st.session_state["openbis"]["connection"]["o"])

    with tabs[-1]:
        tab_export_openbis(st.session_state["openbis"]["connection"]["o"])

    # =========================
    # CLEANUP: Remove widget key duplicates and button keys after tabs are rendered
    # =========================
    # Remove widget key duplicates that are stored in experiment.materials
    # These widget keys duplicate data stored in the organized structure
    widget_key_patterns = [
        "Binder_",  # e.g., Binder_0_percentage, Binder_1_mass_ist
        "PhotoInitiator_",  # e.g., PhotoInitiator_0_weight_fraction
        "Solvent_volume_ml",  # Duplicate of formulation.solvent.volume_ml
        "Additive_weight_fraction",  # Duplicate of formulation.additive.percentage
    ]
    # Remove ALL button keys - they don't persist state meaningfully
    button_key_pattern = "btn_"

    for key in list(st.session_state.keys()):
        # Remove widget duplicates
        for pattern in widget_key_patterns:
            if pattern in key:
                st.session_state.pop(key, None)
                break
        # Remove all button keys
        if key.startswith(button_key_pattern):
            st.session_state.pop(key, None)

    # =========================
    # SIDEBAR INFORMATION & SETTINGS
    # =========================
    st.sidebar.subheader("ℹ️ How to Use")
    with st.sidebar.expander("📖 Step-by-step guide"):
        st.markdown(
            "**1. Connection**: Connect to your OpenBIS instance\n\n"
            "**2. Input Mode**: Choose how to input your formulation data\n\n"
            "**3. General Info**: Enter experiment-level information\n\n"
            "**4. Materials**: Add details for each material component\n\n"
            "**5. Summary**: Review your complete formulation\n\n"
            "**6. Export**: Save your formulation to OpenBIS\n\n"
        )

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Settings")
    if st.sidebar.button("🔄 Clear Session", help="Start from scratch"):
        st.session_state["experiment"] = init_experiment_state()
        st.session_state["openbis"] = init_openbis_state()
        st.session_state["ui"] = init_ui_state()
        st.success("✨ Session cleared!")
        st.rerun()

    # Debug info (optional, for development)
    st.sidebar.markdown("---")
    if st.sidebar.checkbox("🔍 Show Session State (debug)"):
        st.sidebar.json(st.session_state)

    # =========================
    # FOOTER with Version
    # =========================
    st.markdown("---")
    st.markdown(
        f"<div style='text-align: center; color: gray; font-size: 0.85em; margin-top: 2rem;'>"
        f"{APP_NAME} version {VERSION}"
        f"</div>",
        unsafe_allow_html=True,
    )


# =========================
# Run App
# =========================
if __name__ == "__main__":
    main()
