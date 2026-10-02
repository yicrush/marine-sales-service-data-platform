from .common import (
    extract_common_header,
    find_cell_by_label,
    find_value_by_label,
)


def extract_working_details(sheet):
    details = []

    start_cell = find_cell_by_label(
        sheet,
        "Working details"
    )

    if start_cell is None:
        return details

    row_num = start_cell.row + 1

    while row_num <= sheet.max_row:
        value = sheet.cell(
            row=row_num,
            column=1
        ).value

        if (
            isinstance(value, str)
            and "Estimated expense" in value
        ):
            break

        if value is not None:
            details.append(value)

        row_num += 1

    return details


def extract_expense_lines(sheet):
    expenses = []

    start_cell = find_cell_by_label(
        sheet,
        "Estimated expense"
    )

    if start_cell is None:
        return expenses

    row_num = start_cell.row

    while row_num <= sheet.max_row:
        value = sheet.cell(
            row=row_num,
            column=1
        ).value

        if (
            isinstance(value, str)
            and "REMARKS" in value.upper()
        ):
            break

        if value is not None:
            expenses.append(value)

        row_num += 1

    return expenses


def extract_o_service_details(sheet):
    return {
        "working_place_raw": find_value_by_label(
            sheet,
            "Working place"
        ),
        "service_engineers_raw": find_value_by_label(
            sheet,
            "Number of Service Engineers"
        ),
        "working_details_raw": extract_working_details(sheet),
        "expense_lines_raw": extract_expense_lines(sheet),
        "remarks_raw": find_value_by_label(
            sheet,
            "REMARKS"
        ),
    }


def extract_o_quotation(sheet):
    return {
        "type": "O",
        "header": extract_common_header(sheet),
        "service_details": extract_o_service_details(sheet),
    }
