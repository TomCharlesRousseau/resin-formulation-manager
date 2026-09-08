"""OpenBIS sample properties utilities."""

from bs4 import BeautifulSoup


def extract_tables_as_list(
    sample_id, property_name="description", o=None, column_names=None, flatten=False
):
    """
    Extract all HTML tables from a sample property and return them as a list of dictionaries.

    Each table can be returned as nested dict (default) or flattened dict (flatten=True).

    Parameters
    ----------
    sample_id : str
        openBIS sample identifier or permID
    property_name : str
        Name of the property containing the HTML table(s) (default: 'description')
    o : Openbis
        pyBIS Openbis connection object
    column_names : list of str, optional
        Names to use for columns 2..N if <th> headers are absent.
    flatten : bool, default False
        If True, returns each table as a flattened dict: {(row_key, column_name): value}

    Returns
    -------
    list of dict
        Each element corresponds to one table (nested dict or flattened dict).
    """
    sample = o.get_sample(sample_id)
    if sample is None:
        raise ValueError(f"No sample found: {sample_id}")
    html_content = sample.p.get(property_name)

    # Return empty list if property doesn't exist or is None (e.g., Binder has no description table)
    if html_content is None:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []

    all_tables = []

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Detect column names from <th> in first row
        detected_column_names = []
        if rows[0].find_all("th"):
            header_cells = rows[0].find_all("th")
            detected_column_names = [
                cell.get_text().replace("\xa0", " ").strip()
                for cell in header_cells[1:]
            ]
            rows_data = rows[1:]  # skip header row
        else:
            rows_data = rows
            if column_names:
                detected_column_names = column_names
            else:
                detected_column_names = ["value", "unit"]
                n_cols = max(len(r.find_all("td")) for r in rows_data)
                for i in range(len(detected_column_names), max(0, n_cols - 1)):
                    detected_column_names.append(f"col{i + 2}")

        table_dict = {} if not flatten else {}

        for tr in rows_data:
            cells = [
                cell.get_text().replace("\xa0", " ").strip()
                for cell in tr.find_all(["td", "th"])
            ]
            if not any(cells):
                continue
            key = cells[0]
            if not key:
                continue
            remaining = cells[1:]

            if not flatten:
                value_dict = {}
                for idx, val in enumerate(remaining):
                    col_name = (
                        detected_column_names[idx]
                        if idx < len(detected_column_names)
                        else f"col{idx + 2}"
                    )
                    value_dict[col_name] = val
                table_dict[key] = value_dict
            else:
                for idx, val in enumerate(remaining):
                    col_name = (
                        detected_column_names[idx]
                        if idx < len(detected_column_names)
                        else f"col{idx + 2}"
                    )
                    table_dict[(key, col_name)] = val

        if table_dict:
            all_tables.append(table_dict)

    return all_tables


def get_sample_with_properties(sample_id, o=None):
    """
    Fetch a sample and return its properties including $name.

    Parameters
    ----------
    sample_id : str
        OpenBIS sample identifier or permID
    o : Openbis
        pyBIS Openbis connection object

    Returns
    -------
    tuple
        (sample_name, sample_properties_dict, sample_object)
        where sample_name is from sample.props("$name")
        and sample_properties_dict contains all properties from sample.props.all()
    """
    if o is None:
        return None, {}, None

    try:
        sample = o.get_sample(sample_id)
        if sample is None:
            return None, {}, None

        # Get the sample's actual name from OpenBIS
        sample_name = sample.props("$name")

        # Get all properties as a dict
        all_props = sample.props.all()

        return sample_name, all_props, sample
    except Exception as e:
        print(f"Error fetching sample {sample_id}: {e}")
        return None, {}, None
