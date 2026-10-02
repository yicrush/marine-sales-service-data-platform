from numbers import Real


def find_cell_by_label(sheet, label):
    for row in sheet.iter_rows():
        for cell in row:
            if (
                isinstance(cell.value, str)
                and label.upper() in cell.value.upper()
            ):
                return cell

    return None


def find_value_by_label(sheet, label):
    cell = find_cell_by_label(sheet, label)

    if cell is None:
        return None

    return cell.value


def find_value_by_label_in_column(sheet, label, column):
    for row in sheet.iter_rows():
        cell = row[column - 1]

        if (
            isinstance(cell.value, str)
            and label.upper() in cell.value.upper()
        ):
            return cell.value

    return None


def find_row_by_exact_value(sheet, value):
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value == value:
                return cell.row

    return None


def is_number(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def extract_common_header(sheet):
    subject = find_value_by_label(sheet, "Subject :")

    # M quotations usually do not have a "Subject :" label.
    if subject is None:
        subject = sheet.cell(row=13, column=1).value

    return {
        "sheet_name": sheet.title,
        "customer_raw": find_value_by_label(sheet, "TO :"),
        "contact_raw": find_value_by_label(sheet, "ATTN :"),
        "date_raw": find_value_by_label(sheet, "DATE :"),
        "ref_no_raw": find_value_by_label(sheet, "REF. NO."),
        "vessel_name_raw": find_value_by_label(sheet, "VESSEL NAME"),
        "shipyard_hull_raw": find_value_by_label(
            sheet,
            "SHIPYARD/HULL NO"
        ),
        "vessel_hull_raw": find_value_by_label(
            sheet,
            "VESSEL / HULL NO."
        ),
        "subject_raw": subject,
        "contact_details_raw": find_value_by_label_in_column(
            sheet,
            "TEL",
            1
        ),
    }


def detect_sheet_type(sheet):
    ref_no = find_value_by_label(sheet, "REF. NO.")

    if isinstance(ref_no, str):
        if "-M-Q-" in ref_no:
            return "M"

        if "-O-Q-" in ref_no:
            return "O"

    no_cell = find_cell_by_label(sheet, "No.")
    parts_name_cell = find_cell_by_label(sheet, "Parts name")

    if no_cell is not None and parts_name_cell is not None:
        return "KIT_DETAIL"

    return "UNKNOWN"
