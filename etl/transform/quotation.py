"""Pure transforms for the current M/O Extract contract and schema v3."""

from copy import deepcopy
import re

from .common import Validation, parse_date, parse_reference, strip_label, text
from .service import service_expenses


def _contact(header):
    name = strip_label(header.get("contact_raw"), r"ATTN")
    details = text(header.get("contact_details_raw")) or ""
    email_match = re.search(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", details)
    phone_match = re.search(r"\bTEL(?:EPHONE)?\.?\s*[:：]\s*(.*?)(?=\s*(?:FAX|E-?MAIL)\s*[:：]|$)", details, re.I)
    phone = text(phone_match[1].strip()) if phone_match else None
    email = email_match[0] if email_match else None
    if name is None:
        # The dictionary specifies no contacts row without ATTN; raw keeps details.
        return None
    return {"contact_name": name, "telephone": phone, "email": email}


def _vessels(header, validation):
    name = strip_label(header.get("vessel_name_raw"), r"VESSEL\s*NAME")
    hull = strip_label(header.get("shipyard_hull_raw"), r"SHIPYARD\s*/\s*HULL\s*NO\.?")
    combined = strip_label(header.get("vessel_hull_raw"), r"VESSEL\s*/\s*HULL\s*NO\.?")
    if combined:
        if name is None and hull is None and "/" not in combined:
            name = combined
        else:
            validation.add("ambiguous_vessel_hull", "vessels", "Combined vessel/hull text requires explicit separation; raw header retained")
    if name is None and hull is None:
        return [], []
    # No master matching or speculative splitting of several names.
    vessel = {"vessel_name": name, "hull_no": hull, "steering_gear_type": None,
              "main_pump_type": None, "servo_pump_type": None}
    link = {"quoted_vessel_name": name, "quoted_hull_no": hull}
    return [vessel], [link]


def _item_type(value):
    if re.search(r"\b(?:kit|kits)\b", value or "", re.I):
        return "KIT"
    if re.search(r"\b(?:service|inspection|overhaul|repair)\b", value or "", re.I):
        return "SERVICE"
    if re.search(r"\b(?:travel|transport|accommodation|expense)\b", value or "", re.I):
        return "EXPENSE"
    # A name alone does not establish a part classification.
    return "UNKNOWN"


def _items(extracted, validation):
    result = []
    for index, raw in enumerate(extracted.get("items", [])):
        path = f"quotation_items[{index}]"
        item_name = text(raw.get("item_raw"))
        description = text(raw.get("description_raw"))
        if item_name is not None:
            raw_text = "ITEM: " + item_name
            if description is not None:
                raw_text += "\nDESCRIPTION: " + description
        else:
            raw_text = description
        quantity, unit = validation.quantity(raw.get("quantity"), f"{path}.quantity")
        supplied_unit = text(raw.get("quantity_unit"))
        if supplied_unit and not isinstance(raw.get("quantity_unit"), str):
            validation.add("invalid_unit", f"{path}.quantity_unit", "Expected a text quantity unit", "error")
            supplied_unit = None
        if supplied_unit and unit and supplied_unit.strip().lower() != unit.lower():
            validation.add("conflicting_unit", f"{path}.quantity_unit", "Quantity text and unit column disagree", "error")
        unit_price = validation.money(raw.get("unit_price"), f"{path}.unit_price")
        quoted_amount = validation.money(raw.get("amount"), f"{path}.quoted_amount")
        base = validation.money(raw.get("base_amount"), f"{path}.base_amount")
        if base is None and text(raw.get("base_amount")) is None and quantity is not None and unit_price is not None:
            base = validation.money(quantity * unit_price, f"{path}.base_amount")
        if base is None and text(raw.get("base_amount")) is None and text(raw.get("discount_rate")) is None:
            base = quoted_amount
        line_no = raw.get("line_no")
        if line_no is None or (isinstance(line_no, str) and re.fullmatch(r"[A-Za-z]+", line_no.strip())):
            line_no = index + 1
            if raw.get("line_no") is not None:
                raw_text = f"LINE: {raw['line_no']}\n" + (raw_text or "")
        kind = raw.get("item_type") or _item_type(raw_text)
        if kind not in {"PART", "KIT", "SERVICE", "EXPENSE", "OTHER", "UNKNOWN"}:
            validation.add("invalid_item_type", f"{path}.item_type", "Unsupported item category", "error")
            kind = "UNKNOWN"
        result.append({
            "line_no": validation.integer(line_no, f"{path}.line_no", positive=True),
            "line_text_raw": raw_text,
            "item_type": kind,
            "item_name": item_name,
            "description": description,
            "part_no": text(raw.get("part_no")),
            "quantity": quantity,
            "quantity_unit": supplied_unit or unit,
            "unit_price": unit_price,
            "base_amount": base,
            "discount_rate": validation.rate(raw.get("discount_rate"), f"{path}.discount_rate"),
            "quoted_amount": quoted_amount,
            "remark": text(raw.get("remark")),
        })
    return result


def _service(raw, validation):
    statement = strip_label(raw.get("service_engineers_raw"), r"Number\s+of\s+Service\s+Engineers") or ""
    for word, number in {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.items():
        statement = re.sub(rf"\b{word}(?=\s+(?:local\s+)?S\s*/\s*E\b)", str(number), statement, flags=re.I)
    statement = re.sub(r"\b(\d+)\s+local\s+(?=S\s*/\s*E\b)", r"\1 ", statement, flags=re.I)
    def count(patterns, field):
        matches = []
        for pattern in patterns:
            matches.extend(re.findall(pattern, statement, re.I))
        distinct = set(matches)
        if len(distinct) == 1:
            return validation.integer(distinct.pop(), f"service_details.{field}")
        if len(distinct) > 1:
            validation.add("ambiguous_service_count", f"service_details.{field}", "Multiple different counts require review")
        return None
    engineers = count((r"\b(\d+)\s*S\s*/\s*E\b", r"\b(\d+)\s*(?:service\s+)?engineers?\b", r"^\s*(\d+)\s*$"), "service_engineer_count")
    workers = count((r"\b(\d+)[\s-]+(?:person\s+)?workers?\b", r"\b(?:shipyard|supporting)\s+(\d+)[\s-]+person\b",
                     r"\b(?:shipyard|supporting)\s+workers?\s+(\d+)[\s-]+person\b"), "supporting_worker_count")
    days = count((r"\b(\d+)\s*(?:working\s+)?days?\b",), "working_days")
    if statement and engineers is None:
        validation.add("unparsed_service_count", "service_details.service_engineer_count", "Service engineer statement could not be parsed reliably")
    scope = [text(value) for value in raw.get("working_details_raw", [])]
    expense = [text(value) for value in raw.get("expense_lines_raw", [])]
    combined = "\n".join(value for value in [statement, *scope, *expense, text(raw.get("remarks_raw"))] if value)
    excluded = re.search(r"\b(?:excluding|excluded?|not\s+including|without)\s+(?:the\s+)?travel(?:ling|ing)?\s+days?\b", combined, re.I)
    positive_text = re.sub(r"\bnot\s+including\s+(?:the\s+)?travel(?:ling|ing)?\s+days?\b", "", combined, flags=re.I)
    included = re.search(r"\b(?:including|included?)\s+(?:the\s+)?travel(?:ling|ing)?\s+days?\b", positive_text, re.I)
    # Do not interpret the 'including' inside 'not including' as positive evidence.
    includes_travel = False if excluded else (True if included else None)
    if excluded and included:
        includes_travel = None
        validation.add("ambiguous_travel_days", "service_details.includes_travel_days", "Source has both included and excluded travel-day statements")
    result = {
        "working_place": strip_label(raw.get("working_place_raw"), r"Working\s+place"),
        "service_engineer_count": engineers,
        "supporting_worker_count": workers,
        "working_days": days,
        "includes_travel_days": includes_travel,
        "working_details": "\n".join(value for value in scope if value) or None,
        "steering_gear_type": text(raw.get("steering_gear_type")),
        "main_pump_type": text(raw.get("main_pump_type")),
        "servo_pump_type": text(raw.get("servo_pump_type")),
    }
    return result


def transform_quotation(extracted, *, source_file_name=None, currency=None,
                        kit_documents=(), discount_rate_is_fraction=False):
    """Normalize an Extract result, retaining source/validation and nested relations.

    ``kit_documents`` contains already transformed, explicitly associated documents.
    No customer deduplication, vessel matching, or database writes happen here.
    ``currency`` must be document evidence or an explicitly confirmed business rule.
    """
    validation = Validation()
    header = extracted.get("header") or {}
    reference = validation.parse(parse_reference, header.get("ref_no_raw"), "quotation.quotation_ref_no")
    kind = extracted.get("type")
    if kind not in ("M", "O"):
        validation.add("invalid_quotation_type", "quotation.quotation_type", "Expected M or O", "error")
    if reference and reference["quotation_type"] != kind:
        validation.add("reference_type_mismatch", "quotation.quotation_type", "Extract type disagrees with quotation reference", "error")
    quotation = reference or {
        "quotation_ref_no": strip_label(header.get("ref_no_raw"), r"REF\.?\s*NO\.?"),
        "quotation_type": kind, "quotation_year": None, "sequence_no": None, "suffix": None,
    }
    customer_name = strip_label(header.get("customer_raw"), r"TO")
    if customer_name is None:
        validation.add("missing_customer", "customer.customer_name", "Customer name is required", "error")
    summary = extracted.get("summary") or {}
    terms = extracted.get("terms") or {}
    total_source = summary.get("quoted_amount")
    pricing_context = None
    if isinstance(total_source, str) and "/" in total_source:
        match = re.fullmatch(r"\s*((?:USD|US\$|KRW|SGD|EUR|GBP|JPY)\s+[\d,.]+)\s*/\s*([A-Za-z ]+)\s*", total_source, re.I)
        if match:
            pricing_context = {
                "displayed_amount_per_unit": validation.money(match[1], "pricing_context.displayed_amount_per_unit"),
                "amount_basis_raw": match[2],
            }
            total_source = None
            validation.add("per_unit_total", "quotation.document_total_amount", "Displayed total is per unit; normalized price retained in pricing_context and aggregate total left unknown")
    quotation.update({
        "quotation_date": validation.parse(parse_date, header.get("date_raw"), "quotation.quotation_date"),
        "subject": strip_label(header.get("subject_raw"), r"Subject"),
        "currency": validation.currency(currency or extracted.get("currency"), "quotation.currency", required=True),
        "document_discount_rate": validation.rate(summary.get("discount_rate"), "quotation.document_discount_rate", fraction=discount_rate_is_fraction),
        "document_discount_amount": validation.money(summary.get("discounted_amount"), "quotation.document_discount_amount"),
        "document_total_amount": validation.money(total_source, "quotation.document_total_amount"),
        "lead_time_text": strip_label(terms.get("lead_time_raw"), r"LEAD\s*TIME"),
        "delivery_terms": strip_label(terms.get("delivery_terms_raw"), r"Delivery\s*Terms"),
        "payment_terms": strip_label(terms.get("payment_terms_raw"), r"PAYMENT\s*TERMS?"),
        "additional_terms": text(terms.get("additional_terms")),
        "source_file_name": source_file_name,
        "source_sheet_name": header.get("sheet_name"),
    })
    vessels, links = _vessels(header, validation)
    items = _items(extracted, validation)
    service_details = None
    if kind == "O":
        raw_service = extracted.get("service_details") or {}
        service_details = _service(raw_service, validation)
        if not items:
            items, service_total = service_expenses(raw_service, validation)
            if quotation["document_total_amount"] is None and text(summary.get("quoted_amount")) is None:
                quotation["document_total_amount"] = service_total
        if not items:
            validation.add("incomplete_service_extract", "quotation_items", "No supported priced expense summaries were extracted; raw expense text is retained")
    if not items:
        validation.add("empty_items", "quotation_items", "Extract supplied no supported priced lines; check the source layout")
    displayed = quotation["document_total_amount"]
    if items and displayed is not None and all(row["quoted_amount"] is not None for row in items):
        line_sum = sum(row["quoted_amount"] for row in items)
        discount = quotation["document_discount_amount"]
        expected = line_sum - (discount if discount is not None else 0)
        if expected != displayed:
            validation.add("document_total_mismatch", "quotation.document_total_amount", "Displayed total differs from line sum minus displayed discount; source values retained")
    documents = deepcopy(list(kit_documents))
    for index, document in enumerate(documents):
        for issue in document.get("issues", []):
            validation.issues.append({**issue, "field": f"kit_documents[{index}].{issue['field']}"})
    return {"quotation": quotation, "customer": {"customer_name": customer_name},
            "contact": _contact(header), "vessels": vessels, "quotation_vessels": links,
            "quotation_items": items, "service_details": service_details,
            "kit_documents": documents, "pricing_context": pricing_context, "raw": deepcopy(extracted),
            "issues": validation.issues, "is_valid": validation.is_valid}
