"""Synthetic schema-v3 regression tests; no confidential workbooks are needed."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import json
import unittest

from etl.transform import to_jsonable, transform_kit_document, transform_quotation
from etl.transform.common import (
    ParseError,
    Validation,
    parse_date,
    parse_decimal,
    parse_integer,
    parse_quantity,
    parse_reference,
    strip_label,
)


def quotation_fixture(kind="M"):
    """Model the existing Extract dictionary, with invented business text."""
    result = {
        "type": kind,
        "header": {
            "sheet_name": "synthetic quote",
            "customer_raw": "TO : Example Marine",
            "contact_raw": "ATTN : A. Contact",
            "contact_details_raw": "TEL : +65 6000 0000 FAX : +65 6000 0001 E-MAIL : contact@example.test",
            "date_raw": "DATE : 6 January 2026",
            "ref_no_raw": f"REF. NO. : KP-{kind}-Q-26-001-02",
            "vessel_name_raw": "VESSEL NAME : EXAMPLE VESSEL",
            "shipyard_hull_raw": "SHIPYARD/HULL NO. : H-001",
            "subject_raw": "Subject : Spares\nfor example equipment",
        },
        "items": [{
            "line_no": 1,
            "item_raw": "Example part",
            "description_raw": "Original specification\nP.No.001-A",
            "part_no": "001-A",
            "quantity": "2 pcs",
            "unit_price": "10.00",
            "amount": "20.00",
            "remark": "Preserve capitalization.",
        }],
        "summary": {"discount_rate": None, "discounted_amount": None, "quoted_amount": "20.00"},
        "terms": {
            "lead_time_raw": "LEAD TIME : 2~3 weeks after firm order",
            "delivery_terms_raw": "Delivery Terms : Ex-work Korea",
            "payment_terms_raw": "PAYMENT TERM : 30 Days after Invoice date",
        },
    }
    if kind == "O":
        result["service_details"] = {
            "working_place_raw": "1. Working place : EXAMPLE PORT",
            "service_engineers_raw": "Number of Service Engineers : 2 service engineers + 1 worker for 8 days including travelling days",
            "working_details_raw": ["A. Inspection", "B. Original service scope"],
            "expense_lines_raw": ["Estimated expense : separately quoted"],
            "remarks_raw": None,
        }
    return result


def kit_fixture(kind="KIT_DETAIL"):
    return {
        "document_type": kind,
        "sheet_name": "synthetic detail" if kind == "KIT_DETAIL" else "synthetic cost",
        "title_raw": "Original KIT heading\nEXAMPLE VESSEL",
        "amount_summary": {"label_raw": "Amount (100,DISCOUNTED)", "value_raw": "120.00"},
        "groups": [{
            "group_name_raw": "For No.1 & No.2 Main pump (LV-260: 2 sets)",
            "group_amount": "12.00",
            "components": [{
                "line_no": 1,
                "part_name": "O-Ring",
                "part_no": "P.No.001-A",
                "quantity": "4 pcs",
                "quantity_unit": "pcs",
                "unit_price": "3.00",
                "amount": "12.00",
            }],
        }],
    }


def issue_codes(result):
    return {issue["code"] for issue in result["issues"]}


class ScalarParserTests(unittest.TestCase):
    def test_dates_use_explicit_order_and_named_months(self):
        for source in (
            date(2026, 1, 6),
            datetime(2026, 1, 6, 12, 30),
            "2026-01-06",
            "DATE : 6th January 2026",
            "Jan 6, 2026",
        ):
            with self.subTest(source=source):
                self.assertEqual(parse_date(source), "2026-01-06")
        self.assertEqual(parse_date("25/01/2026"), "2026-01-25")
        self.assertEqual(parse_date("01/25/2026"), "2026-01-25")

    def test_ambiguous_or_impossible_dates_are_rejected(self):
        for source in ("01/06/2026", "31/02/2026", "2026-02-30", "not a date"):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_date(source)
        self.assertIsNone(parse_date(" "))

    def test_reference_preserves_suffix_and_leading_zeros_in_raw(self):
        result = parse_reference("REF. NO. : KP-M-Q-26-001-02-A")
        self.assertEqual(result, {
            "quotation_ref_no": "KP-M-Q-26-001-02-A",
            "quotation_type": "M",
            "quotation_year": 2026,
            "sequence_no": 1,
            "suffix": "02-A",
        })
        self.assertIsNone(parse_reference("KP-O-Q-2026-12")["suffix"])

    def test_reference_rejects_zero_sequence_and_unknown_types(self):
        for source in ("KP-M-Q-26-000", "KP-X-Q-26-001", "KP-M-Q-1999-001", None):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_reference(source)

    def test_decimal_retains_exact_values_and_zero(self):
        self.assertEqual(parse_decimal("USD 1,234.50"), Decimal("1234.50"))
        self.assertEqual(parse_decimal(0), Decimal("0"))
        self.assertEqual(parse_decimal(0.1), Decimal("0.1"))
        self.assertIsNone(parse_decimal(" "))
        for source in (True, float("nan"), float("inf"), "1,23", "1.234,56"):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_decimal(source)

    def test_integer_and_quantity_reject_fractional_and_overflow(self):
        self.assertEqual(parse_integer("2.0"), 2)
        self.assertEqual(parse_quantity("0 pcs"), (0, "pcs"))
        self.assertEqual(parse_quantity("2 Sets"), (2, "Sets"))
        for source in (True, "1.5", "2147483648"):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_integer(source)
        with self.assertRaises(ParseError):
            parse_quantity("2.5 pcs")

    def test_schema_money_rejects_negative_precision_and_range(self):
        validation = Validation()
        self.assertEqual(validation.money("999999999999.99", "amount"), Decimal("999999999999.99"))
        self.assertEqual(validation.money(0, "amount"), Decimal("0"))
        for source in ("-0.01", "1000000000000", "0.001"):
            with self.subTest(source=source):
                self.assertIsNone(validation.money(source, "amount"))
        self.assertFalse(validation.is_valid)

    def test_label_removal_does_not_change_unlabelled_prefix_words(self):
        self.assertEqual(strip_label("TO : TORM", r"TO"), "TORM")
        self.assertEqual(strip_label("TORM", r"TO"), "TORM")
        self.assertEqual(strip_label("Subjective repair", r"Subject"), "Subjective repair")


class QuotationTransformTests(unittest.TestCase):
    def test_m_quotation_has_schema_fields_and_preserved_text(self):
        result = transform_quotation(quotation_fixture(), source_file_name="synthetic.xlsx", currency="USD")
        self.assertTrue(result["is_valid"], result["issues"])
        self.assertEqual(result["customer"], {"customer_name": "Example Marine"})
        self.assertEqual(result["contact"]["telephone"], "+65 6000 0000")
        self.assertEqual(result["contact"]["email"], "contact@example.test")
        quotation = result["quotation"]
        self.assertEqual(quotation["quotation_date"], "2026-01-06")
        self.assertEqual(quotation["source_file_name"], "synthetic.xlsx")
        self.assertEqual(quotation["source_sheet_name"], "synthetic quote")
        self.assertEqual(quotation["lead_time_text"], "2~3 weeks after firm order")
        self.assertEqual(quotation["document_total_amount"], Decimal("20.00"))
        item = result["quotation_items"][0]
        self.assertEqual(item["part_no"], "001-A")
        self.assertEqual(item["line_text_raw"], "ITEM: Example part\nDESCRIPTION: Original specification\nP.No.001-A")
        self.assertEqual(item["base_amount"], Decimal("20.00"))
        self.assertIsNone(item["discount_rate"])
        self.assertIsNone(result["service_details"])
        self.assertEqual(result["quotation_vessels"][0]["quoted_hull_no"], "H-001")

    def test_combined_description_and_letter_line_are_preserved(self):
        source = quotation_fixture()
        source["items"][0]["item_raw"] = None
        source["items"][0]["line_no"] = "A"
        result = transform_quotation(source, currency="USD")
        item = result["quotation_items"][0]
        self.assertEqual(item["line_no"], 1)
        self.assertEqual(item["line_text_raw"], "LINE: A\nOriginal specification\nP.No.001-A")
        self.assertIsNone(item["item_name"])

    def test_input_and_attached_documents_are_not_mutated_or_aliased(self):
        source = quotation_fixture()
        document = transform_kit_document(kit_fixture(), currency="USD")
        before_source, before_document = deepcopy(source), deepcopy(document)
        first = transform_quotation(source, currency="USD", kit_documents=[document])
        second = transform_quotation(source, currency="USD", kit_documents=[document])
        self.assertEqual(source, before_source)
        self.assertEqual(document, before_document)
        self.assertEqual(first, second)
        first["raw"]["header"]["customer_raw"] = "Changed"
        first["kit_documents"][0]["document"]["title_raw"] = "Changed"
        self.assertEqual(source, before_source)
        self.assertEqual(document, before_document)

    def test_displayed_totals_are_kept_when_recalculation_disagrees(self):
        source = quotation_fixture()
        source["summary"].update({"quoted_amount": "999.00", "discounted_amount": "3.00", "discount_rate": "10%"})
        result = transform_quotation(source, currency="USD")
        self.assertTrue(result["is_valid"], result["issues"])
        self.assertEqual(result["quotation"]["document_total_amount"], Decimal("999.00"))
        self.assertEqual(result["quotation"]["document_discount_amount"], Decimal("3.00"))
        self.assertEqual(result["quotation"]["document_discount_rate"], Decimal("10"))
        self.assertIn("document_total_mismatch", issue_codes(result))

    def test_discount_fraction_requires_explicit_flag(self):
        source = quotation_fixture()
        source["summary"]["discount_rate"] = 0.1
        normal = transform_quotation(source, currency="USD")
        fractional = transform_quotation(source, currency="USD", discount_rate_is_fraction=True)
        self.assertEqual(normal["quotation"]["document_discount_rate"], Decimal("0.1"))
        self.assertEqual(fractional["quotation"]["document_discount_rate"], Decimal("10"))
        source["summary"]["discount_rate"] = "10%"
        self.assertEqual(transform_quotation(source, currency="USD", discount_rate_is_fraction=True)["quotation"]["document_discount_rate"], Decimal("10"))

    def test_empty_base_amount_still_allows_authorized_calculation(self):
        source = quotation_fixture()
        source["items"][0]["base_amount"] = " "
        source["items"][0]["amount"] = "17.00"
        result = transform_quotation(source, currency="USD")
        self.assertEqual(result["quotation_items"][0]["base_amount"], Decimal("20.00"))
        self.assertEqual(result["quotation_items"][0]["quoted_amount"], Decimal("17.00"))

    def test_missing_currency_required_customer_and_bad_reference_are_invalid(self):
        result = transform_quotation(quotation_fixture())
        self.assertFalse(result["is_valid"])
        self.assertIsNone(result["quotation"]["currency"])
        self.assertIn("missing_currency", issue_codes(result))
        source = quotation_fixture()
        source["header"]["customer_raw"] = "TO : "
        source["header"]["ref_no_raw"] = "REF. NO. : KP-M-Q-26-000"
        result = transform_quotation(source, currency="USD")
        self.assertFalse(result["is_valid"])
        self.assertIn("missing_customer", issue_codes(result))
        self.assertIn("invalid_value", issue_codes(result))
        self.assertEqual(result["raw"]["header"]["ref_no_raw"], source["header"]["ref_no_raw"])

    def test_fractional_quantities_and_negative_money_are_not_coerced(self):
        source = quotation_fixture()
        source["items"][0].update({"quantity": "1.5 pcs", "unit_price": "-1.00"})
        result = transform_quotation(source, currency="USD")
        self.assertFalse(result["is_valid"])
        self.assertIsNone(result["quotation_items"][0]["quantity"])
        self.assertIsNone(result["quotation_items"][0]["unit_price"])

    def test_o_service_counts_and_travel_days(self):
        result = transform_quotation(quotation_fixture("O"), currency="USD")
        service = result["service_details"]
        self.assertEqual(service["working_place"], "EXAMPLE PORT")
        self.assertEqual(service["service_engineer_count"], 2)
        self.assertEqual(service["supporting_worker_count"], 1)
        self.assertEqual(service["working_days"], 8)
        self.assertIs(service["includes_travel_days"], True)
        self.assertEqual(service["working_details"], "A. Inspection\nB. Original service scope")

    def test_excluded_or_unknown_travel_days(self):
        for phrase, expected in (("excluding travelling days", False), ("not including traveling days", False), ("", None)):
            with self.subTest(phrase=phrase):
                source = quotation_fixture("O")
                source["service_details"]["service_engineers_raw"] = "Number of Service Engineers : 2 engineers for 8 days " + phrase
                service = transform_quotation(source, currency="USD")["service_details"]
                self.assertIs(service["includes_travel_days"], expected)

    def test_conflicting_travel_statements_remain_unknown(self):
        source = quotation_fixture("O")
        source["service_details"]["remarks_raw"] = "working days excluding travelling days"
        result = transform_quotation(source, currency="USD")
        self.assertIsNone(result["service_details"]["includes_travel_days"])
        self.assertIn("ambiguous_travel_days", issue_codes(result))

    def test_spelled_engineer_count_and_shipyard_worker_count(self):
        source = quotation_fixture("O")
        source["service_details"]["service_engineers_raw"] = "Number of Service Engineers : Two local S/E + shipyard 1-person for 7 working days"
        service = transform_quotation(source, currency="USD")["service_details"]
        self.assertEqual(service["service_engineer_count"], 2)
        self.assertEqual(service["supporting_worker_count"], 1)
        self.assertEqual(service["working_days"], 7)
        self.assertIsNone(service["includes_travel_days"])

    def test_conflicting_or_shifted_quotation_units_are_invalid(self):
        for unit in (12000, "set"):
            with self.subTest(unit=unit):
                source = quotation_fixture()
                source["items"][0]["quantity_unit"] = unit
                self.assertFalse(transform_quotation(source, currency="USD")["is_valid"])

    def test_o_expense_summaries_preserve_displayed_discounts_and_skip_details(self):
        source = quotation_fixture("O")
        source.pop("items")
        source.pop("summary")
        source["service_details"]["expense_lines_raw"] = [
            "5. Estimated expense : USD 1,900 -> USD 1,700",
            "A. SERVICE fee : USD 1,200 -> USD 1,000",
            "(USD 100 / day x 2 engineers x 6 days = USD 1,200)",
            "B. KIT : USD 700",
            "C. Excluded accommodation : USD 200",
        ]
        result = transform_quotation(source, currency="USD")
        self.assertTrue(result["is_valid"], result["issues"])
        self.assertEqual(result["quotation"]["document_total_amount"], Decimal("1700"))
        self.assertIsNone(result["quotation"]["document_discount_rate"])
        self.assertIsNone(result["quotation"]["document_discount_amount"])
        self.assertEqual(len(result["quotation_items"]), 2)
        first, second = result["quotation_items"]
        self.assertEqual(first["item_type"], "SERVICE")
        self.assertEqual(first["base_amount"], Decimal("1200"))
        self.assertEqual(first["quoted_amount"], Decimal("1000"))
        self.assertIsNone(first["discount_rate"])
        self.assertIsNone(first["quantity"])
        self.assertEqual(second["item_type"], "KIT")
        self.assertEqual(second["quoted_amount"], Decimal("700"))
        self.assertNotIn("document_total_mismatch", issue_codes(result))
        self.assertEqual(result["raw"]["service_details"]["expense_lines_raw"], source["service_details"]["expense_lines_raw"])

    def test_o_malformed_money_is_never_partially_parsed(self):
        for amount in ("1,23", "12,34", "1,234,56"):
            with self.subTest(amount=amount):
                source = quotation_fixture("O")
                source.pop("items")
                source.pop("summary")
                source["service_details"]["expense_lines_raw"] = ["A. SERVICE : USD " + amount]
                result = transform_quotation(source, currency="USD")
                self.assertEqual(result["quotation_items"], [])
                self.assertIn("unparsed_expense", issue_codes(result))

    def test_o_cross_currency_arrow_is_not_interpreted_as_discount(self):
        source = quotation_fixture("O")
        source.pop("items")
        source.pop("summary")
        source["service_details"]["expense_lines_raw"] = ["A. SERVICE USD 100 -> KRW 15000"]
        result = transform_quotation(source, currency="USD")
        self.assertEqual(result["quotation_items"], [])
        self.assertIn("unparsed_expense", issue_codes(result))


class KitTransformTests(unittest.TestCase):
    def test_kit_models_counts_and_source_values(self):
        source = kit_fixture()
        before = deepcopy(source)
        result = transform_kit_document(source, source_file_name="synthetic.xlsx", currency="USD")
        self.assertTrue(result["is_valid"], result["issues"])
        self.assertEqual(source, before)
        document = result["document"]
        self.assertEqual(document["title_raw"], "Original KIT heading\nEXAMPLE VESSEL")
        self.assertEqual(document["total_label_raw"], "Amount (100,DISCOUNTED)")
        self.assertEqual(document["displayed_total_amount"], Decimal("120.00"))
        group = result["groups"][0]["group"]
        self.assertEqual(group["group_type"], "MAIN_PUMP")
        self.assertEqual(group["equipment_model"], "LV-260")
        self.assertEqual(group["equipment_quantity"], 2)
        self.assertEqual(group["equipment_unit"], "sets")
        self.assertEqual(result["groups"][0]["components"][0]["quantity"], 4)

    def test_kit_and_cost_keep_discrepancies_and_currencies_separate(self):
        detail_source, cost_source = kit_fixture(), kit_fixture("COST_SHEET")
        cost_source["groups"][0]["components"][0].update({"part_no": "P.No.999-B", "quantity": "5 pcs", "unit_price": "10000", "amount": "50000"})
        detail = transform_kit_document(detail_source, currency="USD")
        cost = transform_kit_document(cost_source, currency="KRW")
        result = transform_quotation(quotation_fixture(), currency="USD", kit_documents=[detail, cost])
        first, second = result["kit_documents"]
        self.assertEqual(first["document"]["document_type"], "KIT_DETAIL")
        self.assertEqual(second["document"]["document_type"], "COST_SHEET")
        self.assertEqual(first["document"]["currency"], "USD")
        self.assertEqual(second["document"]["currency"], "KRW")
        self.assertEqual(first["groups"][0]["components"][0]["part_no"], "P.No.001-A")
        self.assertEqual(second["groups"][0]["components"][0]["part_no"], "P.No.999-B")

    def test_displayed_group_total_is_not_overwritten(self):
        source = kit_fixture()
        source["groups"][0]["group_amount"] = "99.00"
        result = transform_kit_document(source, currency="USD")
        self.assertEqual(result["groups"][0]["group"]["group_amount"], Decimal("99.00"))
        self.assertIn("group_total_mismatch", issue_codes(result))

    def test_component_amount_is_not_derived_without_an_authorized_rule(self):
        source = kit_fixture()
        source["groups"][0]["components"][0]["amount"] = None
        result = transform_kit_document(source, currency="USD")
        self.assertIsNone(result["groups"][0]["components"][0]["amount"])

    def test_optional_kit_currency_is_unknown_with_warning(self):
        result = transform_kit_document(kit_fixture())
        self.assertIsNone(result["document"]["currency"])
        self.assertTrue(result["is_valid"])
        self.assertIn("missing_currency", issue_codes(result))

    def test_shifted_columns_and_conflicting_units_are_invalid(self):
        for unit in (12000, "set"):
            with self.subTest(unit=unit):
                source = kit_fixture()
                source["groups"][0]["components"][0]["quantity_unit"] = unit
                result = transform_kit_document(source, currency="USD")
                self.assertFalse(result["is_valid"])
        self.assertEqual(transform_kit_document(kit_fixture(), currency="USD")["groups"][0]["components"][0]["part_no"], "P.No.001-A")

    def test_invalid_attached_document_prevents_valid_quotation(self):
        source = kit_fixture()
        source["groups"][0]["components"][0]["quantity"] = "2.5 pcs"
        document = transform_kit_document(source, currency="USD")
        result = transform_quotation(quotation_fixture(), currency="USD", kit_documents=[document])
        self.assertFalse(result["is_valid"])
        self.assertTrue(any(issue["field"].startswith("kit_documents[0].") and issue["severity"] == "error" for issue in result["issues"]))


class SerializationTests(unittest.TestCase):
    def test_json_keeps_decimal_precision_and_dates(self):
        source = {"amount": Decimal("123456789012.30"), "zero": Decimal("0.00"), "nested": (Decimal("0.10"), date(2026, 1, 6))}
        result = to_jsonable(source)
        self.assertEqual(result, {"amount": "123456789012.30", "zero": "0.00", "nested": ["0.10", "2026-01-06"]})
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(source["amount"], Decimal("123456789012.30"))

    def test_json_can_serialize_raw_nonfinite_values_without_nonstandard_tokens(self):
        source = quotation_fixture()
        source["items"][0]["amount"] = float("nan")
        result = transform_quotation(source, currency="USD")
        self.assertFalse(result["is_valid"])
        json.dumps(to_jsonable(result), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
