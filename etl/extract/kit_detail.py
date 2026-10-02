from .common import is_number


def extract_kit_detail(sheet):
    groups = []
    current_group = None
    amount_summary = None

    for row_num in range(3, sheet.max_row + 1):

        line_no = sheet.cell(
            row=row_num,
            column=1
        ).value

        part_name = sheet.cell(
            row=row_num,
            column=2
        ).value

        part_no = sheet.cell(
            row=row_num,
            column=3
        ).value

        quantity = sheet.cell(
            row=row_num,
            column=4
        ).value

        quantity_unit = sheet.cell(
            row=row_num,
            column=5
        ).value

        unit_price = sheet.cell(
            row=row_num,
            column=6
        ).value

        amount = sheet.cell(
            row=row_num,
            column=7
        ).value

        # Component row
        if is_number(line_no):
            component = {
                "line_no": line_no,
                "part_name": part_name,
                "part_no": part_no,
                "quantity": quantity,
                "quantity_unit": quantity_unit,
                "unit_price": unit_price,
                "amount": amount,
            }

            if current_group is not None:
                current_group["components"].append(component)

            continue

        # KIT amount summary row
        if (
            isinstance(line_no, str)
            and "AMOUNT" in line_no.upper()
        ):
            amount_summary = {
                "label_raw": line_no,
                "value_raw": unit_price,
            }

            continue

        # Group row
        if (
            line_no is None
            and isinstance(part_name, str)
            and part_name.strip()
        ):
            current_group = {
                "group_name_raw": part_name,
                "group_amount": unit_price,
                "components": [],
            }

            groups.append(current_group)

    return {
        "type": "KIT_DETAIL",
        "sheet_name": sheet.title,
        "title_raw": sheet.cell(
            row=1,
            column=1
        ).value,
        "groups": groups,
        "amount_summary": amount_summary,
    }
