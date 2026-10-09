"""Validate an entire Transform batch before any PostgreSQL writes.

Database rows have explicit field allowlists and never accept caller-supplied IDs.
Transform metadata (including raw source data) is preserved, but is not a SQL row.
JSON decimal strings and ISO dates are normalized for psycopg without rounding.
"""

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from etl.transform.common import ParseError, parse_reference


class ValidationError(ValueError):
    """A batch was rejected before writing; ``issues`` contains rejected records."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Batch validation rejected {len(issues)} record(s); no writes were performed")


# Field kinds: text, required text, enum, integer, money, rate, date, boolean.
CUSTOMER = {"customer_name": "required_text"}
CONTACT = dict.fromkeys(("contact_name", "telephone", "email"), "text")
VESSEL = dict.fromkeys(("vessel_name", "hull_no", "steering_gear_type", "main_pump_type", "servo_pump_type"), "text")
VESSEL_LINK = dict.fromkeys(("quoted_vessel_name", "quoted_hull_no"), "text")
QUOTATION = {
    "quotation_ref_no": "required_text", "quotation_type": {"M", "O"},
    "quotation_year": "year", "sequence_no": "positive_int", "suffix": "text",
    "quotation_date": "date", "subject": "text", "currency": "required_currency",
    "document_discount_rate": "rate", "document_discount_amount": "money",
    "document_total_amount": "money", "lead_time_text": "text",
    "delivery_terms": "text", "payment_terms": "text", "additional_terms": "text",
    "source_file_name": "text", "source_sheet_name": "text",
}
ITEM = {
    "line_no": "positive_int", "line_text_raw": "text",
    "item_type": {"PART", "KIT", "SERVICE", "EXPENSE", "OTHER", "UNKNOWN"},
    "item_name": "text", "description": "text", "part_no": "text",
    "quantity": "nonnegative_int", "quantity_unit": "text", "unit_price": "money",
    "base_amount": "money", "discount_rate": "rate", "quoted_amount": "money", "remark": "text",
}
DOCUMENT = {
    "document_type": {"KIT_DETAIL", "COST_SHEET"}, "source_file_name": "text",
    "source_sheet_name": "text", "title_raw": "text", "currency": "currency",
    "total_label_raw": "text", "displayed_total_amount": "money",
}
GROUP = {
    "group_type": {"MAIN_PUMP", "OIL_BLOCK_VALVE", "ISOLATION_VALVE", "SERVO_PUMP", "LINE_FILTER", "OTHERS"},
    "group_name_raw": "required_text", "equipment_model": "text",
    "equipment_quantity": "nonnegative_int", "equipment_unit": "text", "group_amount": "money",
}
COMPONENT = {
    "line_no": "positive_int", "part_name": "text", "part_no": "text",
    "quantity": "nonnegative_int", "quantity_unit": "text", "unit_price": "money", "amount": "money", "remark": "text",
}
SERVICE = {
    "working_place": "text", "service_engineer_count": "nonnegative_int",
    "supporting_worker_count": "nonnegative_int", "working_days": "nonnegative_int",
    "includes_travel_days": "boolean", "working_details": "text",
    "steering_gear_type": "text", "main_pump_type": "text", "servo_pump_type": "text",
}


def _issue(code, field, message):
    return {"severity": "error", "code": code, "field": field, "message": message}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Expected a number or normalized decimal string")
    if isinstance(value, str) and not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        raise ValueError("Expected a normalized decimal string without currency labels or separators")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if not number.is_finite():
        raise ValueError("Expected a finite number")
    return number


def _scalar(value, kind):
    required = kind in ("required_text", "required_currency") if isinstance(kind, str) else True
    if value is None:
        if required:
            raise ValueError("Required value is missing")
        return None
    if isinstance(kind, set):
        if not isinstance(value, str) or value not in kind:
            raise ValueError("Unsupported enum value")
        return value
    if kind in ("text", "required_text", "currency", "required_currency"):
        if not isinstance(value, str):
            raise ValueError("Expected text; identifiers are not converted from numbers")
        if "\x00" in value:
            raise ValueError("PostgreSQL text cannot contain a NUL character")
        if not value.strip():
            if required:
                raise ValueError("Required text is blank")
            return None
        if kind in ("currency", "required_currency") and not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Expected a normalized three-letter uppercase currency")
        return value
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Expected a boolean or null")
        return value
    if kind == "date":
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        raise ValueError("Expected a date or normalized ISO YYYY-MM-DD string")
    number = _number(value)
    if kind in ("year", "positive_int", "nonnegative_int"):
        if number != number.to_integral_value():
            raise ValueError("Fractional value is incompatible with an INTEGER column")
        minimum = {"year": 2000, "positive_int": 1, "nonnegative_int": 0}[kind]
        if not minimum <= number <= 2147483647:
            raise ValueError("Integer is outside the permitted PostgreSQL range")
        return int(number)
    if kind in ("money", "rate"):
        maximum = Decimal("100") if kind == "rate" else Decimal("999999999999.99")
        if not 0 <= number <= maximum:
            raise ValueError("Percentage or monetary value is outside its schema range")
        if number != number.quantize(Decimal("0.01")):
            raise ValueError("More than two decimal places would require rounding")
        return number
    raise ValueError("Unsupported validator field kind")


def _row(value, spec, path, issues):
    if not isinstance(value, dict):
        issues.append(_issue("invalid_shape", path, "Expected a database-row object"))
        return {}
    for key in value.keys() - spec.keys():
        issues.append(_issue("unknown_field", f"{path}.{key}", "Unknown row field or caller-supplied database ID is not permitted"))
    result = {}
    for key, kind in spec.items():
        try:
            result[key] = _scalar(value.get(key), kind)
        except (ValueError, TypeError, InvalidOperation) as exc:
            issues.append(_issue("invalid_value", f"{path}.{key}", str(exc)))
            result[key] = None
    return result


def _list(value, path, issues):
    if not isinstance(value, list):
        issues.append(_issue("invalid_shape", path, "Expected a list"))
        return []
    return value


def _source_issues(wrapper, path, issues):
    supplied = wrapper.get("issues", [])
    if not isinstance(supplied, list):
        issues.append(_issue("invalid_shape", f"{path}issues", "Transform issues must be a list"))
    else:
        for index, issue in enumerate(supplied):
            if (not isinstance(issue, dict)
                    or issue.get("severity") not in ("warning", "error")
                    or any(not isinstance(issue.get(key), str) for key in ("code", "field", "message"))):
                issues.append(_issue("invalid_shape", f"{path}issues[{index}]", "Invalid Transform validation issue"))
                continue
            forwarded = deepcopy(issue)
            forwarded["field"] = path + forwarded["field"]
            if forwarded not in issues:
                issues.append(forwarded)
    if "is_valid" in wrapper:
        if not isinstance(wrapper["is_valid"], bool):
            issues.append(_issue("invalid_shape", f"{path}is_valid", "Transform is_valid must be a boolean"))
        elif not wrapper["is_valid"]:
            issues.append(_issue("invalid_transform", f"{path}is_valid", "Transform marked this record invalid"))


def _record(value):
    issues = []
    if not isinstance(value, dict):
        return {}, [_issue("invalid_shape", "record", "Expected a transformed quotation object")]
    result = deepcopy(value)
    _source_issues(value, "", issues)
    result["quotation"] = _row(value.get("quotation"), QUOTATION, "quotation", issues)
    result["customer"] = _row(value.get("customer"), CUSTOMER, "customer", issues)
    contact = value.get("contact")
    result["contact"] = _row(contact, CONTACT, "contact", issues) if contact is not None else None
    if result["contact"] is not None and not any(result["contact"].values()):
        issues.append(_issue("empty_master", "contact", "Contact requires at least a name, telephone or email; otherwise use null"))
    for key, spec in (("vessels", VESSEL), ("quotation_vessels", VESSEL_LINK), ("quotation_items", ITEM)):
        rows = _list(value.get(key, []), key, issues)
        result[key] = [_row(row, spec, f"{key}[{index}]", issues) for index, row in enumerate(rows)]
    if len(result["vessels"]) != len(result["quotation_vessels"]):
        issues.append(_issue("vessel_link_mismatch", "quotation_vessels", "Vessels and quotation links must have matching order and length"))
    seen_vessels = set()
    for index, vessel in enumerate(result["vessels"]):
        key = (vessel.get("vessel_name"), vessel.get("hull_no"))
        if key == (None, None):
            issues.append(_issue("empty_master", f"vessels[{index}]", "Vessel requires a name or hull number; unknown vessels must not create master rows"))
        if key in seen_vessels:
            issues.append(_issue("duplicate_vessel", f"vessels[{index}]", "Repeated vessel natural key would create a duplicate quotation/vessel link"))
        seen_vessels.add(key)
    service = value.get("service_details")
    result["service_details"] = _row(service, SERVICE, "service_details", issues) if service is not None else None
    documents = _list(value.get("kit_documents", []), "kit_documents", issues)
    result["kit_documents"] = []
    for index, document in enumerate(documents):
        path = f"kit_documents[{index}]"
        if not isinstance(document, dict):
            issues.append(_issue("invalid_shape", path, "Expected a transformed KIT document object"))
            continue
        normalized = deepcopy(document)
        _source_issues(document, path + ".", issues)
        normalized["document"] = _row(document.get("document"), DOCUMENT, path + ".document", issues)
        groups = _list(document.get("groups", []), path + ".groups", issues)
        normalized["groups"] = []
        for group_index, group in enumerate(groups):
            group_path = f"{path}.groups[{group_index}]"
            if not isinstance(group, dict):
                issues.append(_issue("invalid_shape", group_path, "Expected a KIT group/components object"))
                continue
            group_result = deepcopy(group)
            group_result["group"] = _row(group.get("group"), GROUP, group_path + ".group", issues)
            components = _list(group.get("components", []), group_path + ".components", issues)
            group_result["components"] = [_row(component, COMPONENT, f"{group_path}.components[{component_index}]", issues)
                                          for component_index, component in enumerate(components)]
            normalized["groups"].append(group_result)
        result["kit_documents"].append(normalized)
    quotation = result["quotation"]
    reference = quotation.get("quotation_ref_no")
    if reference is not None:
        try:
            parsed = parse_reference(reference)
            if parsed["quotation_ref_no"] != reference:
                issues.append(_issue("invalid_reference", "quotation.quotation_ref_no", "Reference must already be normalized without its source label"))
            for key in ("quotation_type", "quotation_year", "sequence_no", "suffix"):
                actual = quotation.get(key)
                if (actual is not None or key in ("quotation_type", "suffix")) and actual != parsed[key]:
                    issues.append(_issue("reference_mismatch", "quotation." + key, "Normalized reference segments disagree with the complete reference"))
        except (ParseError, ValueError, TypeError) as exc:
            issues.append(_issue("invalid_reference", "quotation.quotation_ref_no", str(exc)))
    return result, issues


def validate_records(records, *, allow_warnings=False, skip_invalid=False):
    """Return accepted normalized copies and indexed rejects, or fail the batch.

    Errors always reject a record; warnings reject unless explicitly allowed.
    Every occurrence of a duplicated batch reference rejects, including invalid
    copies. With ``skip_invalid=False`` any rejection raises before writes.
    """
    if not isinstance(allow_warnings, bool) or not isinstance(skip_invalid, bool):
        raise ValueError("allow_warnings and skip_invalid must be explicit booleans")
    if isinstance(records, (str, bytes, dict)):
        raise ValidationError([{"index": None, "source_sheet_name": None, "issues": [_issue("invalid_shape", "records", "Expected an iterable of quotation records")]}])
    try:
        supplied = list(records)
    except TypeError as exc:
        raise ValidationError([{"index": None, "source_sheet_name": None, "issues": [_issue("invalid_shape", "records", "Expected an iterable of quotation records")]}]) from exc
    if not supplied:
        raise ValidationError([{"index": None, "source_sheet_name": None, "issues": [_issue("empty_batch", "records", "No quotation records were supplied; select a supported quotation source")]}])
    checked = [_record(record) for record in supplied]
    references = defaultdict(list)
    for index, record in enumerate(supplied):
        quotation = record.get("quotation") if isinstance(record, dict) else None
        reference = quotation.get("quotation_ref_no") if isinstance(quotation, dict) else None
        if isinstance(reference, str) and reference.strip():
            references[reference].append(index)
    for indices in references.values():
        if len(indices) > 1:
            for index in indices:
                checked[index][1].append(_issue("duplicate_reference", "quotation.quotation_ref_no", "Every copy of a repeated batch reference is rejected; choose one source explicitly"))
    accepted, rejected = [], []
    for index, (record, issues) in enumerate(checked):
        blocked = any(issue["severity"] == "error" or not allow_warnings for issue in issues)
        if blocked:
            source = record.get("quotation", {}).get("source_sheet_name")
            rejected.append({"index": index, "source_sheet_name": source if isinstance(source, str) else None, "issues": issues})
        else:
            accepted.append(record)
    if rejected and not skip_invalid:
        raise ValidationError(rejected)
    return accepted, rejected
