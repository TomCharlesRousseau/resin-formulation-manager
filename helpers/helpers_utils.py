import streamlit as st
import cv2
from helpers.loading import spinner_context


# ---------- CAMERA FUNCTION ----------
def run_camera():
    stframe = st.empty()
    cap = cv2.VideoCapture(0)
    detector = cv2.QRCodeDetector()
    qr_data = None

    while cap.isOpened() and qr_data is None:
        ret, frame = cap.read()
        if not ret:
            st.error("Failed to read from camera.")
            break
        if frame is None or frame.size == 0:
            st.error("Invalid frame received from camera.")
            continue
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        stframe.image(rgb_frame, channels="RGB")
        try:
            data, bbox, _ = detector.detectAndDecode(frame)
        except cv2.error as e:
            st.warning(f"Camera error (may be tablet issue): {str(e)}")
            continue
        if data:
            qr_data = data
            st.success(f"QR/MicroQR Code detected: `{data}`")
            break
    cap.release()
    return qr_data


# ---------- HELPER UI FUNCTIONS ----------
def input_scans(label, scans_key, o, category=None):
    full_list = st.session_state[scans_key]

    # Initialize counter for this category if not done yet
    if category and category not in st.session_state["scan_counters"]:
        st.session_state["scan_counters"][category] = 1

    # Get filtered scans with original indices
    filtered = [
        (idx, scan)
        for idx, scan in enumerate(full_list)
        if category is None or scan.get("category") == category
    ]

    for idx, scan in filtered:
        if not scan["found"]:
            # Use persistent counter
            count = st.session_state["scan_counters"].get(category, 1)
            st.markdown(f"### Add {label} {count}")

            # Increment counter
            st.session_state["scan_counters"][category] = count + 1

            perm_key = f"{scans_key}_perm_{idx}"

            if not scan["permID"]:
                mode = st.session_state.get("input_mode", "Manual input")
                if mode == "Camera":
                    scan["permID"] = run_camera()
                elif mode == "Scanner":
                    scan["permID"] = st.text_input(
                        f"Scan {label} code:", key=f"{scans_key}_scanner_{idx}"
                    )
                else:
                    scan["permID"] = st.text_input(
                        f"Enter {label} permID:", key=f"{scans_key}_manual_{idx}"
                    )
            else:
                scan["permID"] = st.text_input(
                    f"permID {count}", value=scan["permID"], key=perm_key
                )

            # Query openBIS if permID present or changed
            if scan["permID"] and (
                not scan["found"] or scan["permID"] != scan.get("queried_id")
            ):
                try:
                    # Use spinner context for reliable display
                    with spinner_context(f"🔍 Querying openBIS for {label.lower()}..."):
                        s = o.get_samples(permId=scan["permID"], props="$name")
                        df = s.df
                    scan["queried_id"] = scan["permID"]
                    if not df.empty:
                        scan["name"] = df["$NAME"].iloc[0]
                        scan["found"] = True
                        st.success(f"{label} name: {scan['name']}")
                    else:
                        scan["found"] = False
                        st.warning(f"No {label.lower()} found for this permID.")
                except Exception as e:
                    st.error(f"Error while searching: {e}")


# Re-export experiment/business-logic helpers for backward compatibility
