"""
Inspect all properties of a sample to find alias fields.
Usage: python inspect_sample_props.py <perm_id>
"""

import sys
from getpass import getpass

from config import get_default_openbis_url
from helpers.openbis_connection import connect_with_pat


def inspect_sample(perm_id):
    """Fetch and display all properties for a sample."""
    token = getpass("Personal Access Token: ")
    try:
        o = connect_with_pat(get_default_openbis_url(), token)
    except ValueError as e:
        print(f"Failed to connect to OpenBIS: {e}")
        return

    try:
        sample = o.get_sample(perm_id)
        if sample is None:
            print(f"No sample found: {perm_id}")
            return

        print(f"\n{'=' * 70}")
        print(f"Sample: {perm_id}")
        print(
            f"Name ($name): {sample.props('$name') if sample.props('$name') else 'N/A'}"
        )
        print(f"{'=' * 70}\n")

        all_props = sample.props.all()

        if not all_props:
            print("No properties found for this sample")
            return

        print("All Properties:")
        print("-" * 70)

        for field_name, value in sorted(all_props.items()):
            # Skip internal fields for readability
            if field_name.startswith("$"):
                continue

            # Truncate long values
            if isinstance(value, str) and len(value) > 60:
                display_value = value[:57] + "..."
            else:
                display_value = value

            print(f"  {field_name:40} = {display_value}")

        print(f"\n{'=' * 70}")
        print("Total properties:", len([p for p in all_props if not p.startswith("$")]))
        print(f"{'=' * 70}\n")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_sample_props.py <perm_id>")
        print("Example: python inspect_sample_props.py 20250818171845267-17703")
        sys.exit(1)

    perm_id = sys.argv[1]
    inspect_sample(perm_id)
