import re

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


def _has_value(value):
    return value is not None and not (isinstance(value, str) and not value.strip())


def _summary_label(value):
    """Classify labels in the quantity/summary column, never item descriptions."""
    if not isinstance(value, str):
        return None
    token = value.strip()
    if re.match(r"^SUB\s*TOTAL\b", token, re.I):
        return "subtotal"
    if re.match(r"^(?:GRAND\s+)?TOTAL\b|^NET\s+(?:TOTAL|AMOUNT)\b", token, re.I):
        return "total"
    if re.match(r"^DISCOUNT\b", token, re.I):
        return "discount"
    return None


def _footer_row(sheet, row_num):
    # These are standalone footer labels, not arbitrary occurrences in a part
    # description. A numbered "Total repair kit" remains a quoted item.
    footer = re.compile(
        r"^\s*(?:\d+[.)]\s*)?(?:TERMS\s+AND\s+CONDITIONS\b|"
        r"LEAD\s*TIME\b|DELIVERY\s+TERMS\b|PAYMENT\s+TERMS?\b|"
        r"NOTES?\s*[:：]|REMARKS?\s*[:：]|THANK\s+YOU\b|YOURS\s+(?:FAITHFULLY|SINCERELY)\b)",
        re.I,
    )
    return any(isinstance(sheet.cell(row_num, column).value, str)
               and footer.match(sheet.cell(row_num, column).value)
               for column in (1, 2))


def _printed_integer(value):
    """Return only usable whole positive source numbers; invalid ones stay raw."""
    if isinstance(value, bool):
        return None
    if is_number(value):
        try:
            number = int(value)
        except (ValueError, OverflowError):
            return None
        return number if value == number and 0 < number <= 2147483647 else None
    if isinstance(value, str) and re.fullmatch(r"\s*\+?\d+(?:\.0+)?\s*", value):
        try:
            number = int(value.strip().split(".")[0])
        except ValueError:
            return None
        return number if 0 < number <= 2147483647 else None
    return None


def _extract_m_table(sheet):
    """Read M table blocks through headings, separators and unnumbered lines.

    Raw row numbers and section context remain available for Transform. When
    numbering is missing, lettered, or restarts, usable lines receive their
    sequential positions. Invalid source numbers are never repaired silently.
    Intermediate subtotals/repeated headers are not quoted items.
    """
    items = []
    unpriced_rows = []

    header_row = find_row_by_exact_value(sheet, "No.")

    if header_row is None:
        return items, unpriced_rows

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

    heading_parts = []
    after_item = False
    for row_num in range(header_row + 1, sheet.max_row + 1):
        summary_kind = _summary_label(sheet.cell(row_num, 8).value)
        if summary_kind in ("total", "discount") or _footer_row(sheet, row_num):
            break
        if summary_kind == "subtotal":
            unpriced_rows.append({"source_row": row_num,
                                  "cells_raw": [sheet.cell(row_num, column).value
                                                for column in range(1, 12)]})
            continue
        source_no = sheet.cell(row_num, 2).value
        if (isinstance(source_no, str) and source_no.strip().upper() == "NO."
                and isinstance(sheet.cell(row_num, 8).value, str)
                and sheet.cell(row_num, 8).value.strip().upper() in {"QTY", "QUANTITY"}):
            # A second equipment block may repeat the original table header.
            continue
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

        quantity = sheet.cell(row_num, 8).value
        unit_price = sheet.cell(row_num, 9).value
        amount = sheet.cell(row_num, 10).value
        has_commercial_values = any(_has_value(value) for value in (quantity, unit_price, amount))
        numeric_source_no = is_number(source_no) or isinstance(source_no, bool)
        numeric_text_no = (isinstance(source_no, str)
                           and re.fullmatch(r"\s*[+-]?\d+(?:\.\d+)?\s*", source_no) is not None)
        is_item = numeric_source_no or has_commercial_values or (
            numeric_text_no and any(_has_value(value) for value in (item_raw, description_raw))
        )
        if not is_item:
            headings = [sheet.cell(row_num, column).value for column in range(1, 8)
                        if isinstance(sheet.cell(row_num, column).value, str)
                        and sheet.cell(row_num, column).value.strip()]
            if headings:
                unpriced_rows.append({"source_row": row_num,
                                      "cells_raw": [sheet.cell(row_num, column).value
                                                    for column in range(1, 12)]})
                # A/B equipment headings are a supported grouping layout. A
                # description-only unpriced row may instead be a continuation;
                # retain it without inventing a group or a financial line.
                if any(isinstance(sheet.cell(row_num, column).value, str)
                       and sheet.cell(row_num, column).value.strip()
                       for column in (1, 2)):
                    if after_item:
                        heading_parts = []
                    heading_parts.extend(headings)
                    after_item = False
            continue

        item = {
            "line_no": source_no,

            "source_line_no": source_no,

            "source_row": row_num,

            "equipment_heading_raw": "\n".join(heading_parts) or None,

            "item_raw": item_raw,

            "description_raw": description_raw,

            "quantity": quantity,

            "unit_price": unit_price,

            "amount": amount,

            "remark": sheet.cell(
                row=row_num,
                column=11
            ).value,
        }

        items.append(item)
        after_item = True

    source_numbers = [_printed_integer(item["source_line_no"]) for item in items]
    usable_numbers = [number for number in source_numbers if number is not None]
    needs_positions = len(usable_numbers) != len(set(usable_numbers)) or any(
        not _has_value(item["source_line_no"])
        or (isinstance(item["source_line_no"], str)
            and re.fullmatch(r"\s*[A-Za-z]\s*", item["source_line_no"]))
        for item in items
    )
    for position, (item, source_number) in enumerate(zip(items, source_numbers), 1):
        original = item["source_line_no"]
        positional_source = (not _has_value(original)
                             or (isinstance(original, str)
                                 and re.fullmatch(r"\s*[A-Za-z]\s*", original)))
        if needs_positions and (source_number is not None or positional_source):
            item["line_no"] = position
        elif source_number is not None:
            item["line_no"] = source_number

    return items, unpriced_rows


def extract_m_items(sheet):
    return _extract_m_table(sheet)[0]


def extract_m_summary(sheet):
    discount_rate = None
    discounted_amount = None
    quoted_amount = None
    quoted_amount_label_raw = None

    for row in sheet.iter_rows():
        for cell in row:

            if cell.column != 8:
                continue

            if not isinstance(cell.value, str):
                continue

            kind = _summary_label(cell.value)

            if kind == "discount":
                discount_rate = sheet.cell(
                    row=cell.row,
                    column=9
                ).value

                discounted_amount = sheet.cell(
                    row=cell.row,
                    column=10
                ).value

            elif kind == "total":
                quoted_amount_label_raw = cell.value
                quoted_amount = sheet.cell(
                    row=cell.row,
                    column=10
                ).value

    return {
        "discount_rate": discount_rate,
        "discounted_amount": discounted_amount,
        "quoted_amount": quoted_amount,
        "quoted_amount_label_raw": quoted_amount_label_raw,
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
    items, unpriced_rows = _extract_m_table(sheet)
    return {
        "type": "M",
        "header": extract_common_header(sheet),
        "items": items,
        "unpriced_rows_raw": unpriced_rows,
        "summary": extract_m_summary(sheet),
        "terms": extract_m_terms(sheet),
    }
