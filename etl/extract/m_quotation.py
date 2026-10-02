from .common import (
    extract_common_header,
    find_row_by_exact_value,
    find_value_by_label,
    is_number,
)


def extract_m_items(sheet):
    items = []

    header_row = find_row_by_exact_value(sheet, "No.")

    if header_row is None:
        return items

    row_num = header_row + 1

    while is_number(
        sheet.cell(row=row_num, column=2).value
    ):
        item = {
            "line_no": sheet.cell(
                row=row_num,
                column=2
            ).value,
            "description": sheet.cell(
                row=row_num,
                column=3
            ).value,
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
