from .common import (
    extract_common_header,
    find_row_by_exact_value,
    find_value_by_label,
    is_number,
)


def find_header_column(sheet, header_row, header_name):
    for cell in sheet[header_row]:
        if (
            isinstance(cell.value, str)
            and cell.value.strip().upper() == header_name.upper()
        ):
            return cell.column

    return None


def extract_m_items(sheet):
    items = []

    header_row = find_row_by_exact_value(sheet, "No.")

    if header_row is None:
        return items

    item_col = find_header_column(
        sheet,
        header_row,
        "Item"
    )

    description_col = find_header_column(
        sheet,
        header_row,
        "Description"
    )

    row_num = header_row + 1

    while is_number(
        sheet.cell(row=row_num, column=2).value
    ):
        item_raw = (
            sheet.cell(
                row=row_num,
                column=item_col
            ).value
            if item_col is not None
            else None
        )

        description_raw = (
            sheet.cell(
                row=row_num,
                column=description_col
            ).value
            if description_col is not None
            else None
        )

        item = {
            "line_no": sheet.cell(
                row=row_num,
                column=2
            ).value,

            "item_raw": item_raw,

            "description_raw": description_raw,

            "quantity": sheet.cell(
                row=row_num,
                column=8
            ).value,

            "unit_price": sheet.cell(
                row=row_num,
                column=9
            ).value,

            "amount": sheet.cell(
                row=row_num,
                column=10
            ).value,

            "remark": sheet.cell(
                row=row_num,
                column=11
            ).value,
        }

        items.append(item)
        row_num += 1

    return items


def extract_m_summary(sheet):
    discount_rate = None
    discounted_amount = None
    quoted_amount = None

    for row in sheet.iter_rows():
        for cell in row:

            if cell.column != 8:
                continue

            if not isinstance(cell.value, str):
                continue

            value = cell.value.upper()

            if "DISCOUNT" in value:
                discount_rate = sheet.cell(
                    row=cell.row,
                    column=9
                ).value

                discounted_amount = sheet.cell(
                    row=cell.row,
                    column=10
                ).value

            elif "TOTAL" in value:
                quoted_amount = sheet.cell(
                    row=cell.row,
                    column=10
                ).value

    return {
        "discount_rate": discount_rate,
        "discounted_amount": discounted_amount,
        "quoted_amount": quoted_amount,
    }


def extract_m_terms(sheet):
    return {
        "lead_time_raw": find_value_by_label(
            sheet,
            "LEAD TIME"
        ),
        "delivery_terms_raw": find_value_by_label(
            sheet,
            "Delivery Terms"
        ),
        "payment_terms_raw": find_value_by_label(
            sheet,
            "PAYMENT TERM"
        ),
    }


def extract_m_quotation(sheet):
    return {
        "type": "M",
        "header": extract_common_header(sheet),
        "items": extract_m_items(sheet),
        "summary": extract_m_summary(sheet),
        "terms": extract_m_terms(sheet),
    }