"""Conservative parsing of explicit O expense summaries, retaining complete text.

Only lettered expense lines with displayed currency amounts become priced rows.
Calculation/detail lines remain in raw data rather than being counted twice.
"""

import re

from .common import text


AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
CURRENCY = r"(?:USD|US\$|KRW|SGD|EUR|GBP|JPY)"


def _prices(line):
    currencies = {value.upper().replace("US$", "USD") for value in re.findall(CURRENCY, line, re.I)}
    if len(currencies) > 1:
        return None
    matches = list(re.finditer(rf"(?<![@\w]){CURRENCY}\s+(?:{CURRENCY}\s+)?({AMOUNT})(?![\d.,])", line, re.I))
    if not matches:
        return None
    arrow = re.search(r"-\s*>|→", line)
    if arrow:
        before = [match for match in matches if match.start() < arrow.start()]
        after = re.match(rf"\s*(?:{CURRENCY}\s+)?({AMOUNT})(?![\d.,])", line[arrow.end():], re.I)
        if len(before) == 1 and after:
            return before[0][1], after[1]
        return None
    if len(matches) == 1:
        return matches[0][1], matches[0][1]
    return None


def service_expenses(raw, validation):
    items = []
    total = None
    for index, value in enumerate(raw.get("expense_lines_raw", [])):
        line = text(value)
        if line is None:
            continue
        prices = _prices(line)
        if re.match(r"\s*\d*[.)]?\s*Estimated\s+expense\b", line, re.I):
            if prices:
                total = validation.money(prices[1], "quotation.document_total_amount")
            continue
        match = re.match(r"\s*([A-Z])[.)]\s*(.+)", line)
        if match is None:
            continue
        description = match[2]
        if re.match(r"(?:Excluded?|Not\s+included)\b", description, re.I):
            continue
        if prices is None:
            validation.add("unparsed_expense", f"raw.service_details.expense_lines_raw[{index}]", "Lettered expense line has no unambiguous displayed price")
            continue
        if re.search(r"\bKIT\b", description, re.I):
            kind = "KIT"
        elif re.search(r"\bSERVICE\b", description, re.I):
            kind = "SERVICE"
        else:
            kind = "EXPENSE"
        path = f"quotation_items[{len(items)}]"
        amount = validation.money(prices[1], f"{path}.quoted_amount")
        base = validation.money(prices[0], f"{path}.base_amount")
        # Do not confuse engineers/days/rate in detail lines with quantity/unit price.
        items.append({"line_no": len(items) + 1, "line_text_raw": line,
                      "item_type": kind, "item_name": None, "description": description,
                      "part_no": None, "quantity": None, "quantity_unit": None,
                      "unit_price": None, "base_amount": base, "discount_rate": None,
                      "quoted_amount": amount, "remark": None})
    return items, total
