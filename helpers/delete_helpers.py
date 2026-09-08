"""Delete button and clearing utilities for materials."""

import streamlit as st


def add_delete_button(category: str, key: str, on_delete_callback=None):
    """
    Add a delete button for a material category.

    Args:
        category: Name of the material (e.g., "Ceramic", "Solvent")
        key: Unique key for the button
        on_delete_callback: Optional function to call when delete is clicked

    Returns:
        True if delete was clicked, False otherwise
    """
    if st.button("🗑️", key=key, help=f"Delete {category}"):
        if on_delete_callback:
            on_delete_callback()
        return True
    return False
