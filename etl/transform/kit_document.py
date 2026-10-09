"""KIT and internal cost documents remain independent, including discrepancies."""

from copy import deepcopy
import re

from .common import Validation, text


GROUP_PATTERNS = (
    ("MAIN_PUMP", r"\bmain\s+pump\b"),
    ("OIL_BLOCK_VALVE", r"\boil\s+block\s+valve\b"),
    ("ISOLATION_VALVE", r"\bisolation\s+valve\b"),
    ("SERVO_PUMP", r"\bservo\s+pump\b"),
    ("LINE_FILTER", r"\bline\s+filter\b"),
    ("OTHERS", r"\bothers?\b"),
)


def transform_kit_document(extracted, *, source_file_name=None, currency=None):
    """Return a document plus nested groups/components; never fabricate DB IDs."""
    validation = Validation()
    kind = extracted.get("document_type")
    if kind not in ("KIT_DETAIL", "COST_SHEET"):
        validation.add("invalid_document_type", "document.document_type", "Expected KIT_DETAIL or COST_SHEET", "error")
    summary = extracted.get("amount_summary") or {}
    document = {
        "document_type": kind,
        "source_file_name": source_file_name,
        "source_sheet_name": extracted.get("sheet_name"),
        "title_raw": text(extracted.get("title_raw")),
        "currency": validation.currency(currency or extracted.get("currency"), "document.currency"),
        "total_label_raw": text(summary.get("label_raw")),
        "displayed_total_amount": validation.money(summary.get("value_raw"), "document.displayed_total_amount"),
    }
    groups = []
    for index, raw_group in enumerate(extracted.get("groups", [])):
        path = f"groups[{index}]"
        heading = text(raw_group.get("group_name_raw"))
        if heading is None:
            validation.add("missing_group_name", f"{path}.group_name_raw", "Group name is required", "error")
        group_type = None
        for category, pattern in GROUP_PATTERNS:
            if heading and re.search(pattern, heading, re.I):
                group_type = category
                break
        if group_type is None:
            group_type = "OTHERS"
            validation.add("unclassified_group", f"{path}.group_type", "Unrecognized group retained as OTHERS; review source heading")
        model = None
        equipment_quantity = None
        equipment_unit = None
        # Only the explicit '(MODEL: 2 sets)' layout is split into model/count.
        match = re.search(r"\(([^():]+?)\s*:\s*(\d+)\s*([A-Za-z]+)\s*\)", heading or "")
        if match:
            model = match[1].strip()
            equipment_quantity = validation.integer(match[2], f"{path}.equipment_quantity")
            equipment_unit = match[3]
        group = {
            "group_type": group_type,
            "group_name_raw": heading,
            "equipment_model": model,
            "equipment_quantity": equipment_quantity,
            "equipment_unit": equipment_unit,
            "group_amount": validation.money(raw_group.get("group_amount"), f"{path}.group_amount"),
        }
        components = []
        for component_index, raw in enumerate(raw_group.get("components", [])):
            component_path = f"{path}.components[{component_index}]"
            quantity, parsed_unit = validation.quantity(raw.get("quantity"), f"{component_path}.quantity")
            supplied_unit = text(raw.get("quantity_unit"))
            if supplied_unit is not None and not isinstance(raw.get("quantity_unit"), str):
                validation.add("invalid_unit", f"{component_path}.quantity_unit", "Non-text unit may indicate shifted Extract columns", "error")
                supplied_unit = None
            if supplied_unit and parsed_unit and supplied_unit.strip().lower() != parsed_unit.lower():
                validation.add("conflicting_unit", f"{component_path}.quantity_unit", "Quantity text and unit column disagree", "error")
            components.append({
                "line_no": validation.integer(raw.get("line_no"), f"{component_path}.line_no", positive=True),
                "part_name": text(raw.get("part_name")),
                "part_no": text(raw.get("part_no")),
                "quantity": quantity,
                "quantity_unit": supplied_unit or parsed_unit,
                "unit_price": validation.money(raw.get("unit_price"), f"{component_path}.unit_price"),
                # No rule currently authorizes deriving a missing component amount.
                "amount": validation.money(raw.get("amount"), f"{component_path}.amount"),
                "remark": text(raw.get("remark")),
            })
        group_amount = group["group_amount"]
        if components and all(row["amount"] is not None for row in components) and group_amount is not None:
            if sum(row["amount"] for row in components) != group_amount:
                validation.add("group_total_mismatch", f"{path}.group_amount", "Displayed group amount differs from component sum; displayed value retained")
        groups.append({"group": group, "components": components})
    if not any(group["components"] for group in groups):
        validation.add("empty_components", "groups", "Extract supplied no component rows; check source layout")
    return {"document": document, "groups": groups, "raw": deepcopy(extracted),
            "issues": validation.issues, "is_valid": validation.is_valid}
