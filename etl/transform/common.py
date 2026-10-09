"""Strict scalar parsers used by the quotation transforms (no workbook I/O)."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


class ParseError(ValueError):
    """A source value cannot be represented reliably in schema v3."""


def text(value):
    """Preserve spelling, punctuation and line breaks; blank values become None."""
    if value is None:
        return None
    result = str(value)
    return result if result.strip() else None


def strip_label(value, label):
    value = text(value)
    if value is None:
        return None
    # Business headings may have a numbered prefix (e.g. "1. Working place:").
    pattern = rf"^\s*(?:\d+[.)]\s*)?{label}(?=\s|[:：]|$)\s*[:：]?\s*"
    return text(re.sub(pattern, "", value, count=1, flags=re.I).strip())


def parse_decimal(value):
    if text(value) is None:
        return None
    if isinstance(value, bool):
        raise ParseError("Boolean is not a numeric value")
    token = str(value).strip()
    token = re.sub(r"^(?:USD|US\$|KRW|SGD|EUR|GBP|JPY|\$|₩)\s*", "", token, flags=re.I)
    token = re.sub(r"\s*(?:USD|KRW|SGD|EUR|GBP|JPY)$", "", token, flags=re.I)
    # Commas must be thousands separators; do not reinterpret decimal commas.
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", token):
        raise ParseError("Expected an unambiguous decimal number")
    try:
        result = Decimal(token.replace(",", ""))
    except InvalidOperation as exc:
        raise ParseError("Invalid decimal number") from exc
    if not result.is_finite():
        raise ParseError("Expected a finite number")
    return result


def parse_integer(value):
    number = parse_decimal(value)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise ParseError("Fractional value is incompatible with an INTEGER column")
    if not -2147483648 <= number <= 2147483647:
        raise ParseError("Value exceeds PostgreSQL INTEGER range")
    return int(number)


def parse_quantity(value):
    """Return (whole-number quantity, optional unit), retaining unit spelling."""
    if text(value) is None:
        return None, None
    if isinstance(value, str):
        parenthesized = re.fullmatch(r"\s*([+-]?[\d,]+(?:\.\d+)?)\s*\(([A-Za-z]+)\)\s*", value)
        if parenthesized:
            return parse_integer(parenthesized[1]), parenthesized[2]
        match = re.fullmatch(r"\s*([+-]?[\d,]+(?:\.\d+)?)\s*([A-Za-z]+\.?)?\s*", value)
        if match is None:
            raise ParseError("Expected a quantity optionally followed by a unit")
        return parse_integer(match[1]), text(match[2])
    return parse_integer(value), None


def parse_date(value):
    if text(value) is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    token = strip_label(value, r"DATE")
    if token is None:
        return None
    token = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", token, flags=re.I)
    token = re.sub(r"\s+", " ", token).strip()
    token = re.sub(r"\s*([./-])\s*", r"\1", token)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d %b %Y", "%d %B %Y",
                "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d.%b.%Y", "%d/%b/%Y",
                "%d-%B-%Y", "%d.%B.%Y", "%d/%B/%Y"):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            pass
    # Day/month order is not guessed when both components could be months.
    match = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", token)
    if match:
        first, second, year = map(int, match.groups())
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        else:
            raise ParseError("Ambiguous numeric date; use an ISO date or a named month")
        try:
            return date(year, month, day).isoformat()
        except ValueError as exc:
            raise ParseError("Invalid calendar date") from exc
    raise ParseError("Unrecognized date format")


def parse_reference(value):
    reference = strip_label(value, r"REF\.?\s*NO\.?")
    if reference is None:
        raise ParseError("Quotation reference is required")
    match = re.fullmatch(r"[A-Za-z]+-([MO])-Q-(\d{2}|\d{4})-(\d+)(?:-(.+))?", reference, re.I)
    if match is None:
        raise ParseError("Unrecognized quotation reference format")
    kind, year, sequence, suffix = match.groups()
    year = int(year) + (2000 if len(year) == 2 else 0)
    sequence = parse_integer(sequence)
    if sequence <= 0 or year < 2000:
        raise ParseError("Reference must contain a year >= 2000 and a positive sequence")
    return {"quotation_ref_no": reference, "quotation_type": kind.upper(),
            "quotation_year": year, "sequence_no": sequence, "suffix": suffix}


class Validation:
    """Collect field-level issues without discarding the source record."""

    def __init__(self):
        self.issues = []

    def add(self, code, field, message, severity="warning"):
        self.issues.append({"severity": severity, "code": code, "field": field, "message": message})

    def parse(self, parser, value, field):
        try:
            return parser(value)
        except (ParseError, TypeError, ValueError) as exc:
            self.add("invalid_value", field, str(exc), "error")
            return None

    def integer(self, value, field, positive=False):
        result = self.parse(parse_integer, value, field)
        if result is not None and result < (1 if positive else 0):
            self.add("out_of_range", field, "Expected a positive integer" if positive else "Expected a nonnegative integer", "error")
            return None
        return result

    def money(self, value, field):
        result = self.parse(parse_decimal, value, field)
        if result is not None:
            if result < 0 or result >= Decimal("1000000000000"):
                self.add("out_of_range", field, "Amount must fit nonnegative NUMERIC(14,2)", "error")
                return None
            if result != result.quantize(Decimal("0.01")):
                self.add("excess_precision", field, "Amount has more than two decimal places; rounding requires review", "error")
                return None
        return result

    def quantity(self, value, field):
        result = self.parse(parse_quantity, value, field)
        if result is None:
            return None, None
        quantity, unit = result
        if quantity is not None and quantity < 0:
            self.add("out_of_range", field, "Quantity cannot be negative", "error")
            return None, unit
        return quantity, unit

    def rate(self, value, field, fraction=False):
        percent = isinstance(value, str) and value.strip().endswith("%")
        result = self.parse(parse_decimal, value.strip()[:-1] if percent else value, field)
        if result is not None:
            if fraction and not percent:
                result *= 100
            if result < 0 or result > 100 or result != result.quantize(Decimal("0.01")):
                self.add("out_of_range", field, "Discount must fit a percentage from 0 to 100 with two decimal places", "error")
                return None
        return result

    def currency(self, value, field, required=False):
        result = text(value)
        if result is None:
            self.add("missing_currency", field, "Currency requires explicit document evidence or a confirmed business rule", "error" if required else "warning")
            return None
        result = result.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", result):
            self.add("invalid_currency", field, "Expected a three-letter currency code", "error")
            return None
        return result

    @property
    def is_valid(self):
        return not any(issue["severity"] == "error" for issue in self.issues)
