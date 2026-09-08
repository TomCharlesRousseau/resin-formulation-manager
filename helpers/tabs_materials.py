import streamlit as st

# from helpers.streamlit_widgets import select_perm_id

import pandas as pd
from config import get_default_openbis_url, get_default_openbis_space
from helpers.openbis_connection import connect_with_pat, get_username_from_token
from io import BytesIO, StringIO
from datetime import datetime
from openpyxl.styles import PatternFill
from helpers.helpers_utils import run_camera
from helpers.export_openbis import (
    build_experimental_step_name,
)
from helpers.material_helpers import (
    get_openbis_table,
    extract_property_value,
    build_dataframe_from_rows,
    extract_openbis_rows,
    collect_parent_materials,
    fetch_ceramic_suspension_properties,
)
from helpers.loading import animate_progress
from helpers.user_prefs import (
    should_show_first_time_popup,
    dismiss_first_time_popup_permanently,
)
from helpers.formulation_model import (
    Ceramic,
    Binder,
    PhotoInitiator,
    Solvent,
    Additive,
    DispersingAgent,
)
from helpers.formulation_calculations import (
    calculate_ceramic_suspension_masses,
    calculate_individual_ceramic_masses,
    calculate_total_ceramic_mass,
    calculate_binder_masses,
    calculate_photo_initiator_masses,
    calculate_additive_mass,
    calculate_dispersing_agent_addition,
    sync_formulation_to_materials_dict,
    FRACTION_SUM_TOLERANCE,
)


def apply_button_css():
    """Apply CSS to align delete buttons with input fields. Call after st.set_page_config()"""
    st.markdown(
        """
    <style>
    button {
        padding: 6px 8px !important;
        min-height: 40px !important;
        height: 40px !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def get_sample_display_name(o, perm_id):
    """
    Get the display name for a sample, preferring alias over $name.

    Parameters:
    - o: openBIS client object
    - perm_id: sample permId

    Returns:
    - alias if available, otherwise $name, otherwise "Unknown"
    """
    try:
        sample = o.get_sample(perm_id)
        # Try to get alias first
        alias = getattr(sample.props, "alias", None)
        if alias:
            return alias
        # Fallback to $name
        return sample.props("$name")
    except Exception:
        return "Unknown"


@st.dialog("Welcome")
def _show_first_time_popup():
    st.write("First time using the UI? \n Please verify calculations!")
    dont_remind = st.checkbox("Don't remind me again")
    if st.button("Ok"):
        if dont_remind:
            dismiss_first_time_popup_permanently()
        st.session_state["ui"]["first_time_popup_acknowledged"] = True
        st.rerun()


def tab_connection():
    """
    Connection tab: Connect to OpenBIS using a Personal Access Token (PAT).

    The token is entered directly in the browser and kept only in
    st.session_state for the duration of this session — it is never written
    to disk, keyring, or logs.
    """

    st.header("🔐 Connection")
    # Default values (from Streamlit secrets if configured; blank otherwise)
    default_url = get_default_openbis_url()

    # --- Connection Status ---
    st.subheader("Status")

    if st.session_state.get("openbis", {}).get("connection", {}).get("o"):
        st.success("✅ Connected to OpenBIS")
    else:
        st.warning("⚠️ Not connected")

    # --- Inputs ---
    st.subheader("Login")
    url = st.text_input("OpenBIS URL", value=default_url)
    token = st.text_input(
        "Personal Access Token",
        type="password",
        help=(
            "Paste your openBIS Personal Access Token here. It is kept only "
            "for this browser session and is never saved to disk."
        ),
    )

    with st.expander("ℹ️ How do I get a Personal Access Token?"):
        st.markdown(
            "1. Open your openBIS instance and log in.\n"
            "2. Click the **TOOL** button in the top toolbar.\n"
            "3. Select **User Profile**.\n"
            "4. Copy the Personal Access Token: **openBIS session token**\n"
            "5. Paste it into the field above."
        )
        if url.strip():
            st.link_button("Open openBIS", url.strip())

    # --- Connection Button ---
    if st.button("🔐 Connect to OpenBIS", use_container_width=True, key="btn_connect"):
        if should_show_first_time_popup() and not st.session_state["ui"].get(
            "first_time_popup_acknowledged"
        ):
            _show_first_time_popup()
        else:
            _connect_to_openbis(url, token)


def _connect_to_openbis(url, token):
    """Actually perform the OpenBIS connection (separate from the button handler so the
    first-time popup can intercept the first click without connecting yet)."""
    try:
        with st.spinner("🔐 Connecting to openBIS..."):
            o = connect_with_pat(url, token)
            st.session_state["openbis"]["connection"]["o"] = o
            st.session_state["openbis"]["connection"]["pat_invalid"] = False

            userid = get_username_from_token(o) or ""

            with animate_progress("Space detection in progress"):
                all_spaces = [s.code for s in o.get_spaces()]
                matching_spaces = (
                    [s for s in all_spaces if userid.lower() in s.lower()]
                    if userid
                    else []
                )

        # Display results after spinner completes
        # Store all available spaces for later selection
        st.session_state["openbis"]["available"]["spaces"] = all_spaces
        # Store personal/matching space for auto-selection in General Information tab
        personal_space = matching_spaces[0] if matching_spaces else None
        st.session_state["openbis"]["available"]["personal_space"] = personal_space

        if matching_spaces:
            user_space = matching_spaces[0]
            st.session_state["experiment"]["general_info"]["openbis_path"][
                "space"
            ] = user_space
            st.success("✅ Connected to openBIS")
            st.info(f"Home space auto-detected: `{user_space}`")
            st.balloons()
        else:
            # If no personal space found, user will select from dropdown in General Information tab
            st.success("✅ Connected to openBIS")
            st.info("📍 Select your space in the General Information tab")
            st.balloons()

    except ValueError as e:
        st.session_state["openbis"]["connection"]["pat_invalid"] = True
        st.error(f"❌ {e}")
    except Exception as exc:
        st.session_state["openbis"]["connection"]["pat_invalid"] = True
        st.error(f"❌ Connection error ({type(exc).__name__}). Please try again.")


def tab_input_mode():
    st.header("Input Mode")

    mode = st.radio(
        "Select permID input mode",
        options=["Camera", "Manual", "Scanner"],
        index=["Camera", "Manual", "Scanner"].index(
            st.session_state.get("ui", {}).get("input_mode", "Camera")
        ),
    )

    # Store in UI state
    st.session_state["ui"]["input_mode"] = mode

    if mode == "Camera":
        st.info("Camera mode active: webcam will be used to scan QR/MicroQR codes.")
    elif mode == "Scanner":
        st.info("Scanner mode active: use barcode/QR scanner (keyboard input).")
    else:
        st.info("Manual mode active: type permID manually.")


def tab_general_information(o):
    """
    General Information tab: display date, purpose of resin, place, and scan equipment.
    """
    st.header("General Information")

    # Check connection first
    if o is None:
        st.warning("Please connect to openBIS first (Connection tab).")
        return

    # Get experiment dict
    exp = st.session_state["experiment"]
    gen_info = exp["general_info"]

    # Ensure openbis_path structure exists
    if "openbis_path" not in gen_info:
        gen_info["openbis_path"] = {
            "space": "",
            "project": "",
            "collection": "",
            "full_path": "",
        }

    # --- Display current date ---
    current_date = datetime.now().strftime("%Y-%m-%d")
    st.info(f"📅 **Date: {current_date}**")

    # --- Purpose of Resin ---
    purpose_options = [
        "2PP Feedstocks",
        "Xolography Feedstocks",
        "UV Feedstocks",
        "2PP-UV-Kombi Feedstocks",
        "Other",
    ]
    purpose_value = gen_info.get("purpose") or "2PP Feedstocks"
    purpose = st.radio(
        "Purpose of the resin",
        options=purpose_options,
        index=purpose_options.index(purpose_value),
    )
    gen_info["purpose"] = purpose

    # --- Place ---
    place_options = ["FB", "UE", "AH", "Other"]
    place_value = gen_info.get("place") or "FB"
    place = st.radio(
        "Place",
        options=place_options,
        index=place_options.index(place_value),
    )
    gen_info["place"] = place

    # --- OpenBIS Location Selection (Space → Project → Collection) ---
    st.subheader("🗂️ OpenBIS Location")

    # --- Space Selection ---
    available_spaces = (
        st.session_state.get("openbis", {}).get("available", {}).get("spaces", [])
    )
    personal_space = st.session_state.get("openbis", {}).get("available", {}).get("personal_space")
    current_space = gen_info["openbis_path"].get("space", "")

    # Build space options with custom ordering:
    # 1. The configured default space (get_default_openbis_space()) at the top, if set
    # 2. Personal/home space next (for easy access)
    # 3. Other spaces sorted alphabetically
    default_space = get_default_openbis_space()
    space_options = []

    # Add the configured default space at the top if available
    if default_space and default_space in available_spaces:
        space_options.append(default_space)

    # Add personal space next if different from the default
    if personal_space and personal_space != default_space and personal_space not in space_options:
        space_options.append(personal_space)

    # Add remaining spaces in alphabetical order
    other_spaces = sorted([s for s in available_spaces if s not in space_options])
    space_options.extend(other_spaces)

    # Determine which space to select
    # Priority: personal_space > current_space > configured default
    space_to_select = personal_space or current_space or default_space
    
    if space_options:
        # Find the index of the space to select
        selected_index = space_options.index(space_to_select) if space_to_select in space_options else 0
        
        selected_space = st.selectbox(
            "Space",
            options=space_options,
            index=selected_index,
            help="Select the OpenBIS space to work with",
        )

        if selected_space != current_space:
            gen_info["openbis_path"]["space"] = selected_space
            # Reset project and collection when space changes
            st.session_state["openbis"]["available"]["projects"] = []
            st.session_state["openbis"]["available"]["collections"] = []
            gen_info["openbis_path"]["project"] = ""
            gen_info["openbis_path"]["collection"] = ""
            st.rerun()

        user_space = selected_space
    else:
        st.error(
            "⚠️ No space found. Please connect to openBIS first on the Connection tab."
        )
        return

    # Fetch projects if space is selected and not cached
    if user_space and not st.session_state["openbis"]["available"].get("projects", []):
        try:
            projects = o.get_projects(space=user_space)
            st.session_state["openbis"]["available"]["projects"] = [
                proj.code for proj in projects
            ]
        except Exception as e:
            st.error(f"Failed to fetch projects: {e}")
            st.session_state["openbis"]["available"]["projects"] = []

    # --- Project and Collection Selection (2 columns) ---
    col1, col2 = st.columns([1, 1])

    # --- Project Selection ---
    with col1:
        project_options = st.session_state["openbis"]["available"]["projects"] or [
            "(No projects)"
        ]
        current_project = gen_info["openbis_path"].get("project", "")
        selected_project = st.selectbox(
            "Project",
            options=project_options,
            index=(
                project_options.index(current_project)
                if current_project in project_options
                else 0
            ),
        )

        if selected_project != "(No projects)" and selected_project != current_project:
            gen_info["openbis_path"]["project"] = selected_project
            st.session_state["openbis"]["available"]["collections"] = []
            gen_info["openbis_path"]["collection"] = ""
            st.rerun()

    # Fetch collections if project is selected
    current_project = gen_info["openbis_path"].get("project", "")
    if (
        user_space
        and current_project
        and not st.session_state["openbis"]["available"].get("collections", [])
    ):
        try:
            experiments = o.get_experiments(
                space=user_space,
                project=current_project,
            )
            st.session_state["openbis"]["available"]["collections"] = [
                exp.code for exp in experiments
            ]
        except Exception as e:
            st.error(f"Failed to fetch collections: {e}")
            st.session_state["openbis"]["available"]["collections"] = []

    # --- Collection Selection ---
    with col2:
        collection_options = st.session_state["openbis"]["available"][
            "collections"
        ] or ["(No collections)"]
        current_collection = gen_info["openbis_path"].get("collection", "")
        selected_collection = st.selectbox(
            "Collection",
            options=collection_options,
            index=(
                collection_options.index(current_collection)
                if current_collection in collection_options
                else 0
            ),
            disabled=not current_project,
        )

        if (
            selected_collection != "(No collections)"
            and selected_collection != current_collection
        ):
            gen_info["openbis_path"]["collection"] = selected_collection
            st.rerun()

    # --- Display Selected Path ---
    space = gen_info["openbis_path"].get("space", "")
    project = gen_info["openbis_path"].get("project", "")
    collection = gen_info["openbis_path"].get("collection", "")

    if space and project and collection:
        full_path = f"/{space}/{project}/{collection}"
        st.success(f"✅ **Selected Path:** `{full_path}`")
        gen_info["openbis_path"]["full_path"] = full_path
    elif space:
        st.info("Select Project and Collection to complete the path")

    # --- Scan Equipment ---
    equipment_perm_id = select_perm_id(
        category="Equipment",
        current_perm_id=gen_info.get("equipment_perm_id", ""),
        key="equipment",
    )

    if equipment_perm_id:
        gen_info["equipment_perm_id"] = equipment_perm_id
        equipment_name = get_sample_display_name(o, equipment_perm_id)

        # Display equipment name with delete button inline
        col_equip_name, col_equip_delete = st.columns([4, 1])
        with col_equip_name:
            st.subheader(f"Equipment: {equipment_name}")
        with col_equip_delete:
            if st.button("🗑️", key="btn_delete_equipment", help="Delete equipment"):
                gen_info.pop("equipment_perm_id", None)
                gen_info.pop("equipment_name", None)
                st.success("✅ Equipment deleted")
                st.rerun()

        gen_info["equipment_name"] = equipment_name
    else:
        st.info("No equipment selected.")


def select_perm_id(category: str, current_perm_id: str | None, key: str):
    """
    Unified permID selection using global input_mode.
    Supports Manual, Camera, and Scanner modes with camera close/cancel button.

    Args:
        category: Material category name (e.g., "Ceramic", "Equipment")
        current_perm_id: Current perm_id value (from experiment dict)
        key: Unique key for UI state (camera_active, etc.) - only used for camera control

    Returns:
        Selected perm_id or None. Caller must save result to experiment dict.
        Does NOT create any session_state entries.
    """
    mode = st.session_state.get("ui", {}).get("input_mode", "Manual")
    perm_id = current_perm_id

    if mode == "Camera":
        # Check if camera is currently active (UI state only)
        camera_active = st.session_state.get(f"{key}_camera_active", False)

        if not camera_active:
            # Show "Scan" button
            if st.button(f"Scan {category} QR", key=f"{key}_camera_btn"):
                st.session_state[f"{key}_camera_active"] = True
                st.rerun()
        else:
            # Camera is active - show message, then close button below, then camera feed
            st.info("📷 Camera active — scanning for QR or MicroQR code")

            # Show close button below message
            if st.button(
                "❌ Close Camera", key=f"{key}_close_btn", help="Close camera"
            ):
                st.session_state[f"{key}_camera_active"] = False
                st.rerun()

            # Try to scan
            scanned_perm_id = run_camera()
            if scanned_perm_id:
                perm_id = scanned_perm_id
                st.session_state[f"{key}_camera_active"] = False
                # Caller will handle storage to experiment dict and rerun

        # Get stored perm_id from UI state if it exists
        if st.session_state.get(f"{key}_stored_perm_id"):
            perm_id = st.session_state.get(f"{key}_stored_perm_id")

    else:  # Manual mode
        # NO key parameter = widget doesn't create session_state entry
        # Value is returned directly, caller decides where to store it
        perm_id = st.text_input(
            f"{category} permID",
            value=current_perm_id or "",
        )

    return perm_id or None


def tab_ceramic(o):
    """
    Ceramic tab - dynamic multi-ceramic UI backed by formulation.ceramics.

    Ceramic 1 is the reference: the user weighs and enters its suspension mass; all other
    suspension masses are calculated from it (see CLAUDE.md Layer 2/7).
    """
    if o is None:
        st.warning("Please connect to openBIS first.")
        return

    st.header("Ceramic")

    exp = st.session_state["experiment"]
    formulation = exp["formulation"]

    if st.button("+ Add Ceramic", key="btn_add_ceramic"):
        formulation.ceramics.append(Ceramic())
        st.rerun()

    if not formulation.ceramics:
        st.info('No ceramics added yet. Click "+ Add Ceramic" to begin.')
        sync_formulation_to_materials_dict(formulation, exp["materials"])
        return

    col_left, col_right = st.columns([1, 1])

    with col_left:
        for i, ceramic in enumerate(formulation.ceramics):
            is_reference = i == 0
            label = f"Ceramic {i + 1}" + (" (reference)" if is_reference else "")
            with st.expander(label, expanded=True):
                col_select, col_delete = st.columns([4, 1])
                with col_select:
                    perm_id = select_perm_id(
                        category=label,
                        current_perm_id=ceramic.perm_id or "",
                        key=f"ceramic_select_{i}",
                    )
                with col_delete:
                    if st.button("🗑️", key=f"btn_delete_ceramic_{i}", help="Delete ceramic"):
                        formulation.ceramics.pop(i)
                        if is_reference:
                            # The reference's suspension mass drove every other calculation;
                            # once it's gone those masses are no longer valid.
                            for remaining in formulation.ceramics:
                                remaining.suspension_mass = None
                                remaining.ceramic_mass = None
                        st.rerun()

                if not perm_id:
                    st.info("No ceramic selected.")
                    continue

                ceramic.perm_id = perm_id
                ceramic.name = get_sample_display_name(o, perm_id)
                st.caption(f"Selected: {ceramic.name}")

                # Ws,i and Wd,i are properties of the commercial suspension itself, already
                # known from OpenBIS — fetch (and cache per perm_id) rather than ask the user.
                openbis_cache = st.session_state.setdefault("_ceramic_openbis_cache", {})
                if perm_id not in openbis_cache:
                    openbis_cache[perm_id] = fetch_ceramic_suspension_properties(perm_id, o)
                suspension_props = openbis_cache[perm_id]

                ceramic.ceramic_fraction_in_suspension = suspension_props[
                    "ceramic_fraction_in_suspension"
                ]
                ceramic.disp_fraction_in_suspension = suspension_props[
                    "disp_fraction_in_suspension"
                ]

                col_fields, col_table = st.columns([1, 1])

                with col_fields:
                    ceramic.ceramic_fraction = (
                        st.number_input(
                            "Ceramic fraction (relative to total ceramic content) [%]",
                            min_value=0.0,
                            max_value=100.0,
                            step=1.0,
                            key=f"ceramic_{i}_fraction",
                        )
                        / 100.0
                    )

                    if ceramic.ceramic_fraction_in_suspension is not None:
                        st.metric(
                            "Ceramic fraction in suspension (from OpenBIS)",
                            f"{ceramic.ceramic_fraction_in_suspension * 100:.2f} %",
                        )
                    else:
                        st.warning(
                            "⚠️ \"Weight fraction charge\" not found on this sample in "
                            "OpenBIS — cannot calculate suspension masses."
                        )

                    if ceramic.disp_fraction_in_suspension is not None:
                        st.metric(
                            "Dispersing-agent fraction (from OpenBIS)",
                            f"{ceramic.disp_fraction_in_suspension * 100:.2f} %",
                        )
                    else:
                        st.warning(
                            "⚠️ \"Weight fraction disp. Susp.\" not found on this sample in "
                            "OpenBIS — cannot calculate dispersing-agent addition."
                        )

                    if is_reference:
                        ceramic.suspension_mass = st.number_input(
                            "Mass of suspension to weigh (user input) [g]",
                            min_value=0.0,
                            step=0.001,
                            format="%.4f",
                            key=f"ceramic_{i}_mass",
                        )
                        st.caption(
                            "Every other ceramic's suspension mass is calculated from this "
                            "one — see \"⚖️ Suspension masses to weigh\" on the right."
                        )

                with col_table:
                    st.caption("OpenBIS sample properties")
                    table_rows = extract_openbis_rows(suspension_props["table"])
                    if table_rows:
                        st.dataframe(build_dataframe_from_rows(table_rows), hide_index=True)
                    else:
                        st.info("No OpenBIS properties found for this sample.")

    with col_right:
        st.subheader("✅ Checks")
        total_fraction = sum(c.ceramic_fraction or 0.0 for c in formulation.ceramics)
        if abs(total_fraction - 1.0) > FRACTION_SUM_TOLERANCE:
            st.warning(f"⚠️ Ceramic fractions sum to {total_fraction * 100:.2f}% (should be 100%).")
        else:
            st.success("✅ Ceramic fractions sum to 100%.")

        reference = formulation.ceramics[0]
        masses_calculated = False
        if reference.suspension_mass and reference.suspension_mass > 0:
            try:
                calculate_ceramic_suspension_masses(formulation, reference.suspension_mass)
                calculate_individual_ceramic_masses(formulation)
                st.success("✅ Suspension masses calculated.")
                masses_calculated = True
            except ValueError as e:
                st.error(f"⚠️ {e}")
        else:
            st.info("Enter the reference suspension mass (Ceramic 1) to calculate the others.")

        st.subheader("📋 Summary")
        if masses_calculated:
            summary_rows = [
                {
                    "Ceramic": f"{i + 1}" + (f" — {ceramic.name}" if ceramic.name else ""),
                    "Weigh out [g]": f"{ceramic.suspension_mass:.4f}",
                    "Source": "user input" if i == 0 else "calculated",
                    "Ceramic contained [g]": f"{ceramic.ceramic_mass:.4f}",
                }
                for i, ceramic in enumerate(formulation.ceramics)
            ]
            st.dataframe(
                pd.DataFrame(summary_rows),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "\"Weigh out\" is the suspension mass to physically weigh for each "
                "ceramic. \"Ceramic contained\" is the resulting ceramic mass — informational, "
                "not something to weigh separately."
            )

            total_ceramic_mass = sum(c.ceramic_mass for c in formulation.ceramics)
            total_suspension_mass = sum(c.suspension_mass for c in formulation.ceramics)
            col_total_ceramic, col_total_suspension = st.columns(2)
            with col_total_ceramic:
                st.metric("Total ceramic mass (solids only) [g]", f"{total_ceramic_mass:.4f}")
            with col_total_suspension:
                st.metric(
                    "Total suspension mass (sum of all weigh-outs) [g]",
                    f"{total_suspension_mass:.4f}",
                )
            st.caption(
                "These are different quantities — do not confuse them. \"Total ceramic mass\" "
                "is the sum of the \"Ceramic contained\" column (pure ceramic solids only). "
                "\"Total suspension mass\" is the sum of the \"Weigh out\" column (every "
                "suspension you'll physically weigh, across all ceramics) — it's larger because "
                "each suspension also contains solvent/dispersant/etc. besides the ceramic."
            )
        else:
            st.caption("Not available yet — see Checks above.")

    sync_formulation_to_materials_dict(formulation, exp["materials"])


def tab_binder_multi(o):
    """
    Binder tab - Refactored to use material_helpers
    """
    if o is None:
        st.warning("Please connect to openBIS first.")
        return

    st.header("Binders")

    # Display persistent delete message if it exists
    if st.session_state["ui"].get("delete_message_binder"):
        st.warning(st.session_state["ui"]["delete_message_binder"])
        # Keep the message visible for this render, will clear on next action

    col_left, col_right = st.columns([1, 1])

    exp = st.session_state["experiment"]
    formulation = exp["formulation"]
    binders = formulation.binders

    # --- LEFT COLUMN: user inputs ---
    with col_left:
        st.subheader("🎯 Total binder amount")
        formulation.binder_to_ceramic_ratio = (
            st.number_input(
                "Binder : ceramic mass ratio [%]",
                min_value=0.0,
                step=1.0,
                key="binder_to_ceramic_ratio",
                help=(
                    "E.g. 20% means: for every 1 g of total ceramic (from the Ceramic tab), "
                    "add 0.2 g of binder in total, before splitting it across the binders below "
                    "by their own percentage."
                ),
            )
            / 100.0
        )

        if st.button("Add Binder"):
            st.session_state["ui"]["delete_message_binder"] = ""  # Clear delete message
            binders.append(Binder())

        for i, binder in enumerate(binders):
            label = f"Binder {i + 1}"
            with st.expander(label, expanded=True):
                col_select, col_delete = st.columns([4, 1])
                with col_select:
                    binder_perm_id = select_perm_id(
                        category=label,
                        current_perm_id=binder.perm_id or "",
                        key=f"binder_select_{i}",
                    )
                with col_delete:
                    if st.button("🗑️", key=f"btn_delete_binder_{i}", help="Delete binder"):
                        binders.pop(i)
                        st.session_state["ui"]["delete_message_binder"] = (
                            "⚠️ Binder deleted! Please verify all remaining input fields below."
                        )
                        st.rerun()

                if not binder_perm_id:
                    st.info("No binder selected.")
                    continue

                binder.perm_id = binder_perm_id
                binder.name = get_sample_display_name(o, binder_perm_id)
                st.caption(f"Selected: {binder.name}")

                # No OpenBIS property is ever read for a binder, so there is no "OpenBIS
                # sample properties" table here (unlike ceramic/PI) — it would always be empty.
                binder.percentage = (
                    st.number_input(
                        "Binder percentage (relative to total binder mass) (%)",
                        min_value=0.0,
                        max_value=100.0,
                        step=1.0,
                        key=f"Binder_{i}_percentage",
                    )
                    / 100.0
                )

                binder.mass_measured = st.number_input(
                    "Measured mass (g)",
                    min_value=0.0,
                    step=0.001,
                    format="%.4f",
                    key=f"Binder_{i}_mass_ist",
                )

    # --- RIGHT COLUMN: calculations & display ---
    with col_right:
        st.subheader("✅ Checks")

        if not formulation.ceramics or not formulation.ceramics[0].perm_id:
            st.info("No ceramic selected. Set up ceramics on the Ceramic tab first.")
            return

        reference = formulation.ceramics[0]
        mc_total = None
        if reference.suspension_mass:
            try:
                mc_total = calculate_total_ceramic_mass(formulation, reference.suspension_mass)
            except ValueError as e:
                st.error(f"⚠️ Cannot compute total ceramic mass: {e}")
        if mc_total is None:
            st.info(
                "Enter the reference suspension mass (Ceramic 1, on the Ceramic tab) to "
                "calculate binder masses."
            )
            return

        total_percentage = sum(b.percentage or 0.0 for b in binders)
        if abs(total_percentage - 1.0) > FRACTION_SUM_TOLERANCE:
            st.warning(f"⚠️ Sum of binder percentages is {total_percentage * 100:.2f}% (should be 100%).")
        else:
            st.success("✅ Binder percentages sum to 100%.")

        masses_calculated = False
        if binders and formulation.binder_to_ceramic_ratio:
            try:
                total_binder_mass = calculate_binder_masses(formulation, mc_total)
                masses_calculated = True
                st.success("✅ Binder masses calculated.")
            except ValueError as e:
                st.error(f"⚠️ {e}")

        st.subheader("📋 Summary")

        if masses_calculated:
            summary_rows = [
                {
                    "Binder": f"{i + 1}" + (f" — {binder.name}" if binder.name else ""),
                    "Percentage": f"{binder.percentage * 100:.2f} %",
                    "Target mass [g]": f"{binder.mass_target:.4f}",
                    "Measured mass [g]": (
                        f"{binder.mass_measured:.4f}" if binder.mass_measured else "—"
                    ),
                }
                for i, binder in enumerate(binders)
                if binder.perm_id
            ]
            st.dataframe(
                pd.DataFrame(summary_rows),
                hide_index=True,
                use_container_width=True,
            )
            st.metric("Total target mass of all binders [g]", f"{total_binder_mass:.4f}")
        else:
            st.caption("Not available yet — add a binder on the left.")

    sync_formulation_to_materials_dict(formulation, exp["materials"])


def tab_solvent(o):
    """
    Solvent tab - single-instance, backed by formulation.solvent.
    """
    if o is None:
        st.warning("Please connect to openBIS first.")
        return

    st.header("Solvent")
    col_left, col_right = st.columns([1, 1])

    exp = st.session_state["experiment"]
    formulation = exp["formulation"]

    with col_left:
        current_perm_id = formulation.solvent.perm_id if formulation.solvent else ""
        solvent_perm_id = select_perm_id(
            category="Solvent",
            current_perm_id=current_perm_id,
            key="solvent",
        )
        if not solvent_perm_id:
            st.info("No solvent selected.")
            formulation.solvent = None
            sync_formulation_to_materials_dict(formulation, exp["materials"])
            return

        solvent_name = get_sample_display_name(o, solvent_perm_id)
        if formulation.solvent is None or formulation.solvent.perm_id != solvent_perm_id:
            formulation.solvent = Solvent(perm_id=solvent_perm_id, name=solvent_name)
        else:
            formulation.solvent.name = solvent_name

        # Display material name with delete button inline
        col_name, col_delete = st.columns([4, 1])
        with col_name:
            st.subheader(f"Solvent: {solvent_name}")
        with col_delete:
            if st.button("🗑️", key="btn_delete_solvent", help="Delete solvent"):
                formulation.solvent = None
                st.success("✅ Solvent deleted")
                st.rerun()

        # No OpenBIS property is ever read for a solvent, so there is no "OpenBIS sample
        # properties" table here (unlike ceramic/PI) — it would always be empty.
        formulation.solvent.volume_ml = st.number_input(
            "Solvent volume (mL)",
            min_value=0.0,
            step=0.1,
            key="Solvent_volume_ml",
        )

    with col_right:
        st.subheader("✅ Checks")
        st.success("✅ Solvent selected.")

        st.subheader("📋 Summary")
        st.metric("Solvent volume [mL]", f"{formulation.solvent.volume_ml or 0:.2f}")

    sync_formulation_to_materials_dict(formulation, exp["materials"])


def tab_disp(o):
    """
    Dispersing Agent tab - single-instance, backed by formulation.dispersing_agent.

    Wd,i (each ceramic's dispersing-agent fraction) is already auto-fetched per ceramic on the
    Ceramic tab (from that ceramic's own OpenBIS "Weight fraction disp. Susp." property) — this
    tab only needs its own sample's "Concentration disp. Agent" to convert a mass into a volume.
    """
    if o is None:
        st.warning("Please connect to openBIS first.")
        return

    st.header("Dispersing Agent")
    col_left, col_right = st.columns([1, 1])

    exp = st.session_state["experiment"]
    formulation = exp["formulation"]

    with col_left:
        current_perm_id = (
            formulation.dispersing_agent.perm_id if formulation.dispersing_agent else ""
        )
        disp_perm_id = select_perm_id(
            category="Dispersing Agent",
            current_perm_id=current_perm_id,
            key="disp",
        )
        if not disp_perm_id:
            st.info("No dispersing agent selected.")
            formulation.dispersing_agent = None
            sync_formulation_to_materials_dict(formulation, exp["materials"])
            return

        disp_name = get_sample_display_name(o, disp_perm_id)
        if (
            formulation.dispersing_agent is None
            or formulation.dispersing_agent.perm_id != disp_perm_id
        ):
            formulation.dispersing_agent = DispersingAgent(perm_id=disp_perm_id, name=disp_name)
        else:
            formulation.dispersing_agent.name = disp_name

        # Display material name with delete button inline
        col_name, col_delete = st.columns([4, 1])
        with col_name:
            st.subheader(f"Dispersing Agent: {disp_name}")
        with col_delete:
            if st.button("🗑️", key="btn_delete_disp", help="Delete dispersing agent"):
                formulation.dispersing_agent = None
                st.success("✅ Dispersing Agent deleted")
                st.rerun()

        # Concentration is a property of the sample itself — fetch (and cache per perm_id)
        # rather than ask the user, same pattern as ceramic/PI/additive.
        disp_openbis_cache = st.session_state.setdefault("_disp_openbis_cache", {})
        if disp_perm_id not in disp_openbis_cache:
            table = get_openbis_table(disp_perm_id, o)
            disp_openbis_cache[disp_perm_id] = {
                "table": table,
                "concentration_mg_per_ml": extract_property_value(
                    table, "Concentration disp. Agent"
                ),
            }
        formulation.dispersing_agent.concentration_mg_per_ml = disp_openbis_cache[disp_perm_id][
            "concentration_mg_per_ml"
        ]

        col_fields, col_table = st.columns([1, 1])

        with col_fields:
            formulation.dispersing_agent.target_disp_fraction = (
                st.number_input(
                    "Target dispersing-agent weight fraction, relative to total ceramic (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    key="disp_target_fraction",
                )
                / 100.0
            )

            if formulation.dispersing_agent.concentration_mg_per_ml is not None:
                st.metric(
                    "Concentration (from OpenBIS) [mg/mL]",
                    f"{formulation.dispersing_agent.concentration_mg_per_ml:.2f}",
                )
            else:
                st.warning(
                    "⚠️ \"Concentration disp. Agent\" not found on this sample in OpenBIS — "
                    "volume cannot be calculated (mass still can)."
                )

        with col_table:
            st.caption("OpenBIS sample properties")
            table_rows = extract_openbis_rows(disp_openbis_cache[disp_perm_id]["table"])
            if table_rows:
                st.dataframe(build_dataframe_from_rows(table_rows), hide_index=True)
            else:
                st.info("No OpenBIS properties found for this sample.")

    with col_right:
        st.subheader("✅ Checks")

        if not formulation.ceramics or not formulation.ceramics[0].perm_id:
            st.info("No ceramic selected. Set up ceramics on the Ceramic tab first.")
            return

        reference = formulation.ceramics[0]
        if not reference.suspension_mass:
            st.info(
                "Enter the reference suspension mass (Ceramic 1, on the Ceramic tab) to "
                "calculate the dispersing-agent addition."
            )
            return

        addition_calculated = False
        try:
            calculate_dispersing_agent_addition(formulation, reference.suspension_mass)
            addition_calculated = True
            if formulation.dispersing_agent.mass_to_add:
                st.success("✅ Dispersing-agent addition calculated.")
            else:
                st.success("✅ Target already met — no dispersing agent needs to be added.")
        except ValueError as e:
            st.error(f"⚠️ {e}")

        st.subheader("📋 Summary")

        if addition_calculated:
            da = formulation.dispersing_agent
            st.metric("Current dispersing-agent fraction", f"{da.current_disp_fraction * 100:.2f} %")
            st.metric("Mass to add [g]", f"{da.mass_to_add:.4f}")
            st.metric("Volume to add [µL]", f"{da.volume:.2f}" if da.volume is not None else "—")
        else:
            st.caption("Not available yet — see Checks above.")

    sync_formulation_to_materials_dict(formulation, exp["materials"])


def tab_pi_multi(o):
    """
    Photo-Initiator tab - dynamic multi-PI UI backed by formulation.photo_initiators.
    """
    if o is None:
        st.warning("Please connect to openBIS first.")
        return

    st.header("Photo-Initiators")

    # Display persistent delete message if it exists
    if st.session_state.get("delete_message_pi"):
        st.warning(st.session_state["delete_message_pi"])
        # Keep the message visible for this render, will clear on next action

    col_left, col_right = st.columns([1, 1])

    exp = st.session_state["experiment"]
    formulation = exp["formulation"]
    pis = formulation.photo_initiators

    # --- LEFT COLUMN: user inputs ---
    with col_left:
        if st.button("Add Photo-Initiator"):
            st.session_state["delete_message_pi"] = ""  # Clear delete message
            pis.append(PhotoInitiator())

        # Concentration is a property of the sample itself — fetch (and cache per perm_id)
        # rather than ask the user, same pattern as the ceramic suspension properties.
        pi_openbis_cache = st.session_state.setdefault("_pi_openbis_cache", {})

        for i, pi in enumerate(pis):
            label = f"Photo-Initiator {i + 1}"
            with st.expander(label, expanded=True):
                col_select, col_delete = st.columns([4, 1])
                with col_select:
                    pi_perm_id = select_perm_id(
                        category=label,
                        current_perm_id=pi.perm_id or "",
                        key=f"pi_select_{i}",
                    )
                with col_delete:
                    if st.button(
                        "🗑️", key=f"btn_delete_pi_{i}", help="Delete photo-initiator"
                    ):
                        pis.pop(i)
                        st.session_state["delete_message_pi"] = (
                            "⚠️ Photo-Initiator deleted! Please verify all remaining input fields below."
                        )
                        st.rerun()

                if not pi_perm_id:
                    st.info("No photo-initiator selected.")
                    continue

                pi.perm_id = pi_perm_id
                pi.name = get_sample_display_name(o, pi_perm_id)
                st.caption(f"Selected: {pi.name}")

                if pi_perm_id not in pi_openbis_cache:
                    table = get_openbis_table(pi_perm_id, o)
                    pi_openbis_cache[pi_perm_id] = {
                        "table": table,
                        "concentration_mg_per_ml": extract_property_value(
                            table, "Concentration PI"
                        ),
                    }
                pi.concentration_mg_per_ml = pi_openbis_cache[pi_perm_id][
                    "concentration_mg_per_ml"
                ]

                col_fields, col_table = st.columns([1, 1])

                with col_fields:
                    pi.percentage = (
                        st.number_input(
                            "Weight fraction relative to total binder mass (%)",
                            min_value=0.0,
                            max_value=100.0,
                            step=1.0,
                            key=f"PhotoInitiator_{i}_weight_fraction",
                        )
                        / 100.0
                    )

                    if pi.concentration_mg_per_ml is not None:
                        st.metric(
                            "Concentration (from OpenBIS) [mg/mL]",
                            f"{pi.concentration_mg_per_ml:.2f}",
                        )
                    else:
                        st.warning(
                            "⚠️ \"Concentration PI\" not found on this sample in OpenBIS — "
                            "volume cannot be calculated (mass still can)."
                        )

                with col_table:
                    st.caption("OpenBIS sample properties")
                    table_rows = extract_openbis_rows(pi_openbis_cache[pi_perm_id]["table"])
                    if table_rows:
                        st.dataframe(build_dataframe_from_rows(table_rows), hide_index=True)
                    else:
                        st.info("No OpenBIS properties found for this sample.")

    # --- RIGHT COLUMN: calculations & display ---
    with col_right:
        st.subheader("✅ Checks")

        total_binder_mass = exp["materials"].get("Binder", {}).get("total_mass")
        if not total_binder_mass:
            st.info("No binder data available. Add binders and set their masses first.")
            return
        st.success(f"✅ Total binder mass available: {total_binder_mass:.4f} g")

        masses_calculated = False
        if pis:
            try:
                calculate_photo_initiator_masses(formulation, total_binder_mass)
                masses_calculated = True
                st.success("✅ Photo-initiator masses calculated.")
            except ValueError as e:
                st.error(f"⚠️ {e}")

        st.subheader("📋 Summary")

        if masses_calculated:
            summary_rows = [
                {
                    "Photo-Initiator": f"{i + 1}" + (f" — {pi.name}" if pi.name else ""),
                    "Percentage (of binder mass)": f"{pi.percentage * 100:.2f} %",
                    "Target mass [mg]": f"{pi.mass_target:.4f}",
                    "Target volume [µL]": (
                        f"{pi.volume:.2f}" if pi.volume is not None else "—"
                    ),
                }
                for i, pi in enumerate(pis)
                if pi.perm_id
            ]
            st.dataframe(
                pd.DataFrame(summary_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Not available yet — add a photo-initiator on the left.")

    sync_formulation_to_materials_dict(formulation, exp["materials"])


def tab_additive(o):
    """
    Additive tab - single-instance, backed by formulation.additive.
    """
    if o is None:
        st.warning("Please connect to openBIS first.")
        return

    st.header("Additive")
    col_left, col_right = st.columns([1, 1])

    exp = st.session_state["experiment"]
    formulation = exp["formulation"]

    with col_left:
        current_perm_id = formulation.additive.perm_id if formulation.additive else ""
        add_perm_id = select_perm_id(
            category="Additive",
            current_perm_id=current_perm_id,
            key="add",
        )
        if not add_perm_id:
            st.info("No additive selected.")
            formulation.additive = None
            sync_formulation_to_materials_dict(formulation, exp["materials"])
            return

        add_name = get_sample_display_name(o, add_perm_id)
        if formulation.additive is None or formulation.additive.perm_id != add_perm_id:
            formulation.additive = Additive(perm_id=add_perm_id, name=add_name)
        else:
            formulation.additive.name = add_name

        # Display material name with delete button inline
        col_name, col_delete = st.columns([4, 1])
        with col_name:
            st.subheader(f"Additive: {add_name}")
        with col_delete:
            if st.button("🗑️", key="btn_delete_additive", help="Delete additive"):
                formulation.additive = None
                st.success("✅ Additive deleted")
                st.rerun()

        # Concentration is a property of the sample itself — fetch (and cache per perm_id)
        # rather than ask the user, same pattern as ceramic/PI.
        additive_openbis_cache = st.session_state.setdefault("_additive_openbis_cache", {})
        if add_perm_id not in additive_openbis_cache:
            table = get_openbis_table(add_perm_id, o)
            additive_openbis_cache[add_perm_id] = {
                "table": table,
                "concentration_mg_per_ml": extract_property_value(table, "Concentration AD"),
            }
        formulation.additive.concentration_mg_per_ml = additive_openbis_cache[add_perm_id][
            "concentration_mg_per_ml"
        ]

        col_fields, col_table = st.columns([1, 1])

        with col_fields:
            formulation.additive.percentage = (
                st.number_input(
                    "Weight fraction relative to total binder mass (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    key="Additive_weight_fraction",
                )
                / 100.0
            )

            if formulation.additive.concentration_mg_per_ml is not None:
                st.metric(
                    "Concentration (from OpenBIS) [mg/mL]",
                    f"{formulation.additive.concentration_mg_per_ml:.2f}",
                )
            else:
                st.warning(
                    "⚠️ \"Concentration AD\" not found on this sample in OpenBIS — "
                    "volume cannot be calculated (mass still can)."
                )

        with col_table:
            st.caption("OpenBIS sample properties")
            table_rows = extract_openbis_rows(additive_openbis_cache[add_perm_id]["table"])
            if table_rows:
                st.dataframe(build_dataframe_from_rows(table_rows), hide_index=True)
            else:
                st.info("No OpenBIS properties found for this sample.")

    with col_right:
        st.subheader("✅ Checks")

        total_binder_mass = exp["materials"].get("Binder", {}).get("total_mass")
        if not total_binder_mass:
            st.info("No binder data available. Add binders and set their masses first.")
            return
        st.success(f"✅ Total binder mass available: {total_binder_mass:.4f} g")

        mass_calculated = False
        try:
            calculate_additive_mass(formulation, total_binder_mass)
            mass_calculated = True
            st.success("✅ Additive mass calculated.")
        except ValueError as e:
            st.error(f"⚠️ {e}")

        st.subheader("📋 Summary")

        if mass_calculated:
            st.metric("Target mass [mg]", f"{formulation.additive.mass_target:.4f}")
            st.metric(
                "Target volume [µL]",
                f"{formulation.additive.volume:.2f}" if formulation.additive.volume is not None else "—",
            )
        else:
            st.caption("Not available yet — see Checks above.")

    sync_formulation_to_materials_dict(formulation, exp["materials"])


def tab_summary(o):
    st.header("Summary")

    experiment = st.session_state.get("experiment", {})
    dfs = []

    # --- Add General Information at the top ---
    gen_info = experiment.get("general_info", {})
    if gen_info:
        gen_info_rows = [
            ("Purpose", gen_info.get("purpose"), ""),
            ("Place", gen_info.get("place"), ""),
        ]
        if gen_info.get("equipment_name"):
            gen_info_rows.append(("Equipment", gen_info.get("equipment_name"), ""))

        df_gen_info = pd.DataFrame(gen_info_rows, columns=["property", "value", "unit"])
        df_gen_info.insert(0, "category", "General Information")
        dfs.append(df_gen_info)

    # --- Add Material IDs section (using helper) ---
    parents, parents_with_names = collect_parent_materials(experiment)

    # Convert to summary format with names
    material_ids_rows = []
    for parent_id, category, name in parents_with_names:
        material_ids_rows.append((category, parent_id, ""))
        material_ids_rows.append((f"{category} Name", name, ""))

    if material_ids_rows:
        df_material_ids = pd.DataFrame(
            material_ids_rows, columns=["property", "value", "unit"]
        )
        df_material_ids.insert(0, "category", "Material IDs")
        dfs.append(df_material_ids)

    SUMMARY_ORDER = [
        "Ceramic",
        "Binder",
        "Solvent",
        "Dispersing Agent",
        "Photo-Initiator",
        "Additive",
    ]

    # Handle both single-item materials (flat) and multi-item materials (with items array)
    materials = experiment.get("materials", {})
    for category in SUMMARY_ORDER:
        if category in materials:
            material = materials[category]
            # Check if material has a dataframe
            if isinstance(material, dict) and "df" in material:
                df_copy = (
                    material["df"].copy()
                    if isinstance(material["df"], pd.DataFrame)
                    else pd.read_csv(StringIO(material["df"]))
                )
                df_copy.insert(0, "category", category)
                dfs.append(df_copy)

    if not dfs:
        st.info("No data available yet.")
        return

    final_df = pd.concat(dfs, ignore_index=True)

    # Display resin name above the table
    resin_name = build_experimental_step_name(experiment, o)
    st.markdown(f"### 🧪 Suggested Experimental Step: **{resin_name}**")

    # Allow user to customize experimental step name
    with st.expander("✏️ Customize Experimental Step (Optional)"):
        custom_resin_name = st.text_input(
            "Custom Experimental Step Name",
            value=st.session_state.get("ui", {}).get("custom_resin_name") or resin_name,
            help="Leave empty to use the suggested name",
            key="custom_resin_name_input",
        )
        if custom_resin_name and custom_resin_name != resin_name:
            st.session_state["ui"]["custom_resin_name"] = custom_resin_name
            display_resin_name = custom_resin_name
        else:
            st.session_state["ui"]["custom_resin_name"] = None
            display_resin_name = resin_name

        st.caption(f"**Final Experimental Step Name:** `{display_resin_name}`")

    st.subheader("Experiment Data")
    st.dataframe(final_df)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Format all float values in the dataframe with comma and max 3 decimal places
        from helpers.experiment import format_float_value

        formatted_df = final_df.copy()
        for col in formatted_df.columns:
            formatted_df[col] = formatted_df[col].apply(format_float_value)

        # Write the dataframe starting at row 3 to leave room for date and resin name
        formatted_df.to_excel(writer, index=False, sheet_name="Experiment", startrow=2)

        # Get the worksheet
        worksheet = writer.sheets["Experiment"]

        # Add date at the top (row 1)
        date_str = datetime.now().strftime("%Y-%m-%d")
        worksheet["A1"] = f"Date: {date_str}"

        # Add experimental step name (row 2) - use custom if provided
        final_exp_step_name = (
            st.session_state.get("ui", {}).get("custom_resin_name") or resin_name
        )
        worksheet["A2"] = f"Experimental Step: {final_exp_step_name}"

        # Category to hex color mapping
        category_colors = {
            "General Information": "E8E8E8",  # Light grey
            "Material IDs": "D3D3D3",  # Darker grey
            "Ceramic": "FFA500",  # Orange
            "Binder": "A9A9A9",  # Grey
            "Solvent": "FFFFE0",  # Light yellow
            "Dispersing Agent": "87CEEB",  # Sky blue
            "Photo-Initiator": "FFB6C1",  # Light pink
            "Additive": "E6E6FA",  # Lavender
        }

        # Apply colors to data rows (starting from row 4, since row 3 has headers)
        for row_num, (idx, row) in enumerate(formatted_df.iterrows(), start=4):
            category = row.get("category", "")
            color = category_colors.get(category, "FFFFFF")

            # Apply background color to all cells in the row
            for col_num in range(1, len(formatted_df.columns) + 1):
                cell = worksheet.cell(row=row_num, column=col_num)
                cell.fill = PatternFill(
                    start_color=color, end_color=color, fill_type="solid"
                )

    output.seek(0)

    # Store Excel bytes in session state for later use in export
    st.session_state["experiment"]["excel_bytes"] = output.getvalue()

    st.download_button(
        "Download Excel",
        data=output,
        file_name="experiment_summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def tab_export_openbis(o):
    st.header("Export to openBIS")

    if o is None:
        st.warning("Not connected to openBIS.")
        return

    experiment = st.session_state.get("experiment", {})
    gen_info = experiment.get("general_info", {})

    # Check if collection is selected
    if not gen_info.get("openbis_path", {}).get("full_path"):
        st.error(
            "❌ Please select a Space, Project, and Collection in the General Information tab first."
        )
        return

    collection_path = gen_info.get("openbis_path", {}).get("full_path")
    st.markdown("### Target collection")
    st.code(collection_path)

    # ===== 1. EXPERIMENTAL STEP CODE (Primary - Simple format: RES_purpose_date_counter) =====
    purpose_map = {
        "2PP Feedstocks": "2PP",
        "Xolography Feedstocks": "XOL",
        "UV Feedstocks": "UV",
        "2PP-UV-Kombi Feedstocks": "2PPUV",
        "Other": "OTH",
    }
    purpose = gen_info.get("purpose", "Other")
    purpose_abbr = purpose_map.get(purpose, "OTH")
    date_str = datetime.now().strftime("%Y%m%d")

    # Auto-increment counter to find unique experimental step code
    counter = 1
    exp_step_code = None
    max_attempts = 100

    while counter <= max_attempts:
        test_code = f"RES_{purpose_abbr}_{date_str}_{counter:03d}"
        # Check for both the base code and the _EXP suffixed version
        try:
            o.get_sample(f"{collection_path}/{test_code}_EXP")
            counter += 1
            continue
        except Exception:
            pass

        try:
            o.get_sample(f"{collection_path}/{test_code}")
            counter += 1
        except Exception:
            # Code doesn't exist, we found a unique code
            exp_step_code = test_code
            break

    if exp_step_code is None:
        st.error(
            f"❌ Could not generate unique experimental step code after {max_attempts} attempts!"
        )
        return

    st.info(f"📝 **Suggested Experimental Step Code:** `{exp_step_code}_EXP`")

    # Allow user to customize experimental step code
    with st.expander("✏️ Customize Experimental Step Code (Optional)"):
        custom_exp_step_code = st.text_input(
            "Custom Experimental Step Code",
            value=st.session_state.get("custom_exp_step_code", exp_step_code),
            help="Leave empty to use the suggested code",
            key="custom_exp_step_code_input",
        )
        if custom_exp_step_code and custom_exp_step_code != exp_step_code:
            st.session_state["custom_exp_step_code"] = custom_exp_step_code
            final_exp_step_code = custom_exp_step_code
        else:
            st.session_state.pop("custom_exp_step_code", None)
            final_exp_step_code = exp_step_code

        st.caption(f"**Final Experimental Step Code:** `{final_exp_step_code}_EXP`")

    # ===== 2. EXPERIMENTAL STEP CODE with suffix =====
    # Add _EXP suffix to base code for the experimental step
    final_exp_step_code_with_suffix = f"{final_exp_step_code}_EXP"

    # ===== 3. SAMPLE CODE (Derived from Base Code + _SAMPLE) =====
    # Sample code = base code + "_SAMPLE"
    # (No additional counter needed - if exp_step_code is unique, so is sample_code)
    suggested_sample_code = f"{exp_step_code}_SAMPLE"

    st.info(f"🧪 **Suggested Sample Code:** `{suggested_sample_code}`")

    # Allow user to customize sample code
    with st.expander("✏️ Customize Sample Code (Optional)"):
        custom_sample_code = st.text_input(
            "Custom Sample Code",
            value=st.session_state.get("custom_sample_code", suggested_sample_code),
            help="Leave empty to use the suggested code",
            key="custom_sample_code_input",
        )
        if custom_sample_code and custom_sample_code != suggested_sample_code:
            st.session_state["custom_sample_code"] = custom_sample_code
            final_sample_code = custom_sample_code
        else:
            st.session_state.pop("custom_sample_code", None)
            final_sample_code = suggested_sample_code

        st.caption(f"**Final Sample Code:** `{final_sample_code}`")

    # --- Collect parent materials (using helper) ---
    parents, parents_with_names = collect_parent_materials(experiment)

    # Display collected parents
    if parents:
        st.markdown("### Parent Materials (to be linked)")
        st.caption(f"Total: {len(parents)} parent samples")
        with st.expander("View parent permIDs"):
            for i, (parent_id, category, name) in enumerate(parents_with_names, 1):
                st.text(f"{i}. {category} - {name}")
                st.caption(f"   {parent_id}")
    else:
        st.warning(
            "⚠️ No parent materials selected. Sample will be created without parents."
        )

    # --- Validate binder percentages before export ---
    binder_data = experiment.get("materials", {}).get("Binder", {})
    total_binder_percentage = binder_data.get("total_percentage", 0)
    binder_items = binder_data.get("items", [])

    ceramic = experiment.get("materials", {}).get("Ceramic", {})
    ceramic_perm_id = ceramic.get("perm_id")

    # Check prerequisites
    missing_items = []
    if not ceramic_perm_id:
        missing_items.append("✗ Ceramic material not selected")
    if not binder_items:
        missing_items.append("✗ No binder added")
    if binder_items and total_binder_percentage != 100.0:
        missing_items.append(
            f"✗ Binder percentages sum to {total_binder_percentage:.2f}% (need 100%)"
        )

    binder_percentage_valid = not missing_items

    if not binder_percentage_valid:
        st.error("❌ Cannot export - please fix:")
        for item in missing_items:
            st.error(f"   {item}")

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button(
            "Export to openBIS", key="btn_export", disabled=not binder_percentage_valid
        ):
            try:
                excel_bytes = st.session_state["experiment"].get("excel_bytes")
                from helpers.openbis_operations import (
                    create_sample_and_attach_summary,
                )

                # Try to create sample, with auto-retry if code already exists
                exp_code_to_use = final_exp_step_code_with_suffix
                sample_code_to_use = final_sample_code
                retry_count = 0
                max_retries = 10
                sample = None

                while retry_count <= max_retries and sample is None:
                    try:
                        with st.spinner(
                            "Creating sample and uploading dataset on openBIS..."
                        ):
                            sample, ds, export_path = create_sample_and_attach_summary(
                                o=o,
                                experiment=experiment,
                                collection_path=collection_path,
                                exp_step_code=exp_code_to_use,
                                sample_code=sample_code_to_use,
                                parents=parents,
                                excel_bytes=excel_bytes,
                                purpose=purpose,
                            )
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" in error_str and retry_count < max_retries:
                            # Auto-increment and retry
                            retry_count += 1
                            # Extract the base code and increment the counter
                            parts = final_exp_step_code.rsplit("_", 1)
                            if len(parts) == 2 and parts[1].isdigit():
                                base = parts[0]
                                counter = int(parts[1]) + retry_count
                                exp_code_to_use = f"{base}_{counter:03d}_EXP"
                                sample_code_to_use = f"{base}_{counter:03d}_SAMPLE"
                            else:
                                raise  # Can't auto-increment, raise original error
                        else:
                            raise  # Not a duplicate error, raise as is

                if sample is None:
                    raise Exception("Failed to create sample after multiple retries")

                # Display success messages
                actual_exp_code = exp_code_to_use.replace("_EXP", "")
                if actual_exp_code != final_exp_step_code:
                    st.warning(
                        f"⚠️ Code `{final_exp_step_code}` already existed, automatically incremented to: **{actual_exp_code}**"
                    )

                st.success(
                    f"✅ Experimental step successfully created: **{actual_exp_code}**"
                )
                st.success(f"✅ Sample successfully created: **{sample.code}**")

                if parents:
                    st.success(f"🔗 Linked to {len(parents)} parent materials")

                if ds:
                    st.success(f"📊 Dataset added to sample: **{ds.code}**")
                    if export_path:
                        st.success(f"💾 Excel saved to: **{export_path}**")
                    st.balloons()
                else:
                    st.info("No Excel dataset was attached.")

            except Exception as e:
                st.error(f"❌ Export failed: {e}")

    with col2:
        if st.button("❌ Cancel", key="btn_export_cancel"):
            st.info("Export cancelled.")


