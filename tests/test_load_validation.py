"""Pure preflight tests with synthetic records and no database dependency."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import json
import unittest

from etl.load.validation import ValidationError, validate_records
from etl.transform import to_jsonable, transform_kit_document, transform_quotation


def record_fixture(sequence=1):
    kit = transform_kit_document({
        "document_type": "KIT_DETAIL", "sheet_name": "invented kit",
        "title_raw": "Invented KIT", "amount_summary": {"label_raw": "Amount", "value_raw": "12.00"},
        "groups": [{"group_name_raw": "Main pump (MODEL-1: 2 sets)", "group_amount": "12.00",
                    "components": [{"line_no": 1, "part_name": "O-Ring", "part_no": "001-A",
                                    "quantity": "4 pcs", "quantity_unit": "pcs", "unit_price": "3.00", "amount": "12.00"}]}],
    }, currency="USD")
    return transform_quotation({
        "type": "M",
        "header": {"sheet_name": "invented quote", "customer_raw": "TO : Invented Marine",
                   "ref_no_raw": f"REF. NO. : KP-M-Q-26-{sequence:03d}", "date_raw": "2026-01-06",
                   "contact_raw": "ATTN : Invented Contact", "vessel_name_raw": "VESSEL NAME : INVENTED VESSEL"},
        "items": [{"line_no": 1, "item_raw": "Invented part", "description_raw": "Original text\n002-B",
                   "quantity": 2, "unit_price": "10.00", "amount": "20.00", "part_no": "002-B"}],
        "summary": {"quoted_amount": "20.00"},
    }, source_file_name="invented.xlsx", currency="USD", kit_documents=[kit])


def set_path(record, path, value):
    current = record
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def source_issue(severity="warning"):
    return {"severity": severity, "code": "invented_issue", "field": "raw", "message": "Review invented source"}


def rejected_codes(rejected):
    return {issue["code"] for record in rejected for issue in record["issues"]}


class LoadValidationTests(unittest.TestCase):
    def rejected(self, record, **options):
        accepted, rejected = validate_records([record], skip_invalid=True, **options)
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)
        return rejected

    def test_transform_record_and_json_round_trip_are_accepted(self):
        record = record_fixture()
        accepted, rejected = validate_records([record])
        self.assertEqual(rejected, [])
        self.assertEqual(accepted[0]["quotation"]["quotation_date"], date(2026, 1, 6))
        self.assertEqual(accepted[0]["quotation_items"][0]["quoted_amount"], Decimal("20.00"))
        json_record = json.loads(json.dumps(to_jsonable(record)))
        normalized, _ = validate_records([json_record])
        self.assertEqual(normalized, accepted)
        component = normalized[0]["kit_documents"][0]["groups"][0]["components"][0]
        self.assertEqual(component["unit_price"], Decimal("3.00"))
        self.assertEqual(component["part_no"], "001-A")

    def test_input_metadata_and_raw_are_preserved_without_aliasing(self):
        record = record_fixture()
        record["custom_metadata"] = {"label": "Metadata has no SQL role"}
        before = deepcopy(record)
        accepted, _ = validate_records([record])
        self.assertEqual(record, before)
        self.assertEqual(accepted[0]["raw"], before["raw"])
        self.assertEqual(accepted[0]["issues"], before["issues"])
        self.assertEqual(accepted[0]["is_valid"], before["is_valid"])
        accepted[0]["raw"]["header"]["customer_raw"] = "Modified"
        accepted[0]["kit_documents"][0]["raw"]["title_raw"] = "Modified"
        accepted[0]["custom_metadata"]["label"] = "Modified"
        self.assertEqual(record, before)

    def test_warning_blocks_by_default_and_requires_explicit_allow(self):
        record = record_fixture()
        record["issues"] = [source_issue()]
        with self.assertRaises(ValidationError) as context:
            validate_records([record])
        self.assertEqual(context.exception.issues[0]["index"], 0)
        self.assertEqual(context.exception.issues[0]["source_sheet_name"], "invented quote")
        accepted, rejected = validate_records([record], allow_warnings=True)
        self.assertEqual(rejected, [])
        self.assertEqual(accepted[0]["issues"], record["issues"])

    def test_allow_warnings_cannot_bypass_source_errors_or_invalid_flag(self):
        for case in ("error", "false_flag"):
            with self.subTest(case=case):
                record = record_fixture()
                if case == "error":
                    record["issues"] = [source_issue("error")]
                    record["is_valid"] = True
                else:
                    record["is_valid"] = False
                    record["issues"] = []
                self.rejected(record, allow_warnings=True)

    def test_nested_kit_source_issues_are_checked_when_root_omits_them(self):
        for severity in ("warning", "error"):
            with self.subTest(severity=severity):
                record = record_fixture()
                record["kit_documents"][0]["issues"] = [source_issue(severity)]
                rejected = self.rejected(record)
                self.assertTrue(any(issue["field"] == "kit_documents[0].raw" for issue in rejected[0]["issues"]))
                if severity == "warning":
                    accepted, _ = validate_records([record], allow_warnings=True)
                    self.assertEqual(len(accepted), 1)
                else:
                    self.rejected(record, allow_warnings=True)

    def test_nested_kit_invalid_flag_is_not_trusted_when_root_is_valid(self):
        record = record_fixture()
        record["kit_documents"][0]["is_valid"] = False
        self.assertIn("invalid_transform", rejected_codes(self.rejected(record, allow_warnings=True)))

    def test_generated_ids_and_unknown_row_fields_are_rejected(self):
        for path in (
            ("customer", "customer_id"), ("quotation", "customer_id"),
            ("quotation", "quotation_id"), ("contact", "contact_id"),
            ("vessels", 0, "vessel_id"), ("quotation_vessels", 0, "vessel_id"),
            ("quotation_items", 0, "quotation_item_id"),
            ("kit_documents", 0, "document", "kit_quotation_item_id"),
            ("kit_documents", 0, "groups", 0, "group", "kit_document_id"),
            ("kit_documents", 0, "groups", 0, "components", 0, "unexpected"),
        ):
            with self.subTest(path=path):
                record = record_fixture()
                set_path(record, path, 42)
                self.assertIn("unknown_field", rejected_codes(self.rejected(record)))

    def test_required_fields_are_not_supplied_from_database_defaults(self):
        for path, value in (
            (("customer", "customer_name"), None), (("customer", "customer_name"), " "),
            (("quotation", "quotation_ref_no"), None), (("quotation", "currency"), None),
            (("quotation", "quotation_type"), "X"),
            (("quotation_items", 0, "item_type"), None),
            (("kit_documents", 0, "document", "document_type"), None),
            (("kit_documents", 0, "groups", 0, "group", "group_name_raw"), " "),
        ):
            with self.subTest(path=path, value=value):
                record = record_fixture()
                set_path(record, path, value)
                self.rejected(record)

    def test_enum_values_and_currency_must_be_normalized(self):
        for path, value in (
            (("quotation", "currency"), "usd"), (("quotation", "currency"), "US Dollars"),
            (("quotation_items", 0, "item_type"), "part"),
            (("kit_documents", 0, "document", "document_type"), "INVOICE"),
            (("kit_documents", 0, "groups", 0, "group", "group_type"), "UNKNOWN"),
        ):
            with self.subTest(path=path):
                record = record_fixture()
                set_path(record, path, value)
                self.rejected(record)

    def test_numbers_dates_and_lists_cannot_be_used_as_text(self):
        for path, value in (
            (("customer", "customer_name"), 42), (("contact", "telephone"), 650000000),
            (("quotation_items", 0, "part_no"), 12), (("quotation_items", 0, "remark"), ["text"]),
            (("vessels", 0, "vessel_name"), True), (("quotation", "subject"), "Bad\x00text"),
        ):
            with self.subTest(path=path):
                record = record_fixture()
                set_path(record, path, value)
                self.rejected(record)

    def test_nullable_fields_and_zero_values_are_preserved(self):
        record = record_fixture()
        record["contact"] = None
        record["quotation"]["quotation_date"] = None
        record["quotation"]["quotation_year"] = None
        record["quotation"]["sequence_no"] = None
        record["quotation_items"][0].update({"quantity": "0", "unit_price": "0.00", "quoted_amount": None, "remark": " "})
        record["kit_documents"][0]["document"]["currency"] = None
        accepted, _ = validate_records([record])
        self.assertIsNone(accepted[0]["contact"])
        self.assertIsNone(accepted[0]["quotation"]["quotation_date"])
        item = accepted[0]["quotation_items"][0]
        self.assertEqual(item["quantity"], 0)
        self.assertEqual(item["unit_price"], Decimal("0.00"))
        self.assertIsNone(item["remark"])

    def test_integer_fraction_bool_negative_and_overflow_are_rejected(self):
        for value in (True, "1.5", -1, "2147483648", float("inf")):
            with self.subTest(value=value):
                record = record_fixture()
                record["quotation_items"][0]["quantity"] = value
                self.rejected(record)
        record = record_fixture()
        record["quotation_items"][0]["quantity"] = "2.0"
        accepted, _ = validate_records([record])
        self.assertEqual(accepted[0]["quotation_items"][0]["quantity"], 2)

    def test_line_numbers_are_positive_and_equipment_counts_nonnegative(self):
        record = record_fixture()
        record["quotation_items"][0]["line_no"] = 0
        self.rejected(record)
        record = record_fixture()
        record["kit_documents"][0]["groups"][0]["group"]["equipment_quantity"] = -1
        self.rejected(record)

    def test_monetary_limits_precision_and_finite_values(self):
        for value in ("-0.01", "1000000000000", "0.001", "NaN", float("nan"), True, "USD 10", "1,000"):
            with self.subTest(value=value):
                record = record_fixture()
                record["quotation"]["document_total_amount"] = value
                self.rejected(record)
        record = record_fixture()
        record["quotation"]["document_total_amount"] = "999999999999.99"
        accepted, _ = validate_records([record])
        self.assertEqual(accepted[0]["quotation"]["document_total_amount"], Decimal("999999999999.99"))

    def test_discount_rates_do_not_accept_percent_labels_or_out_of_range(self):
        for value in ("100.01", "-1", "10%", "0.001", True):
            with self.subTest(value=value):
                record = record_fixture()
                record["quotation_items"][0]["discount_rate"] = value
                self.rejected(record)

    def test_load_dates_use_only_normalized_iso_or_date_objects(self):
        for value in ("01/06/2026", "6 January 2026", "2026-02-30", datetime(2026, 1, 6), 45200):
            with self.subTest(value=value):
                record = record_fixture()
                record["quotation"]["quotation_date"] = value
                self.rejected(record)
        record = record_fixture()
        record["quotation"]["quotation_date"] = date(2026, 1, 6)
        self.assertEqual(validate_records([record])[0][0]["quotation"]["quotation_date"], date(2026, 1, 6))

    def test_reference_and_segment_consistency_are_checked_independently(self):
        for field, value in (("quotation_year", 2025), ("sequence_no", 2), ("quotation_type", "O"), ("suffix", "02"), ("quotation_ref_no", "KP-M-Q-26-000")):
            with self.subTest(field=field):
                record = record_fixture()
                record["quotation"][field] = value
                self.rejected(record)
        record = record_fixture()
        record["quotation"]["quotation_ref_no"] = "KP-M-Q-26-001-02-A"
        record["quotation"]["suffix"] = "02-A"
        self.assertEqual(validate_records([record])[0][0]["quotation"]["suffix"], "02-A")

    def test_nested_shape_errors_reject_without_crashing(self):
        for path, value in (
            (("quotation",), []), (("customer",), None), (("contact",), "contact"),
            (("vessels",), {}), (("quotation_vessels",), None), (("quotation_items",), "items"),
            (("quotation_items", 0), None), (("kit_documents",), {}), (("kit_documents", 0), None),
            (("kit_documents", 0, "document"), []), (("kit_documents", 0, "groups"), {}),
            (("kit_documents", 0, "groups", 0), "group"),
            (("kit_documents", 0, "groups", 0, "components"), "components"),
            (("service_details",), []),
        ):
            with self.subTest(path=path):
                record = record_fixture()
                set_path(record, path, value)
                self.assertIn("invalid_shape", rejected_codes(self.rejected(record)))

    def test_vessel_link_length_and_duplicate_natural_key_are_rejected(self):
        record = record_fixture()
        record["quotation_vessels"] = []
        self.assertIn("vessel_link_mismatch", rejected_codes(self.rejected(record)))
        record = record_fixture()
        record["vessels"].append(deepcopy(record["vessels"][0]))
        record["quotation_vessels"].append(deepcopy(record["quotation_vessels"][0]))
        self.assertIn("duplicate_vessel", rejected_codes(self.rejected(record)))

    def test_empty_vessel_and_contact_masters_are_not_created(self):
        record = record_fixture()
        record["vessels"][0].update({"vessel_name": None, "hull_no": None})
        self.assertIn("empty_master", rejected_codes(self.rejected(record)))
        record = record_fixture()
        record["contact"] = {"contact_name": None, "telephone": " ", "email": None}
        self.assertIn("empty_master", rejected_codes(self.rejected(record)))
        record["contact"]["email"] = "invented@example.test"
        accepted, _ = validate_records([record])
        self.assertIsNone(accepted[0]["contact"]["contact_name"])
        self.assertEqual(accepted[0]["contact"]["email"], "invented@example.test")

    def test_service_counts_and_boolean_are_validated(self):
        record = record_fixture()
        record["service_details"] = {"service_engineer_count": "2", "supporting_worker_count": "0", "working_days": 7, "includes_travel_days": False}
        accepted, _ = validate_records([record])
        self.assertEqual(accepted[0]["service_details"]["service_engineer_count"], 2)
        self.assertIs(accepted[0]["service_details"]["includes_travel_days"], False)
        for field, value in (("includes_travel_days", "false"), ("includes_travel_days", 0), ("working_days", -1), ("service_engineer_count", True)):
            with self.subTest(field=field):
                candidate = deepcopy(record)
                candidate["service_details"][field] = value
                self.rejected(candidate)

    def test_duplicate_batch_references_reject_every_copy(self):
        first, second, third = record_fixture(), record_fixture(), record_fixture(2)
        second["quotation_items"][0]["unit_price"] = -1
        before = deepcopy([first, second, third])
        accepted, rejected = validate_records([first, second, third], skip_invalid=True)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["quotation"]["quotation_ref_no"], "KP-M-Q-26-002")
        self.assertEqual([row["index"] for row in rejected], [0, 1])
        self.assertTrue(all(any(issue["code"] == "duplicate_reference" for issue in row["issues"]) for row in rejected))
        self.assertEqual([first, second, third], before)

    def test_default_batch_validation_does_not_return_partial_acceptance(self):
        first, second = record_fixture(), record_fixture(2)
        second["quotation"]["currency"] = None
        with self.assertRaises(ValidationError) as context:
            validate_records([first, second])
        self.assertEqual([row["index"] for row in context.exception.issues], [1])
        accepted, rejected = validate_records([first, second], skip_invalid=True)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)

    def test_issue_metadata_must_have_a_recognized_severity_and_shape(self):
        for field, value in (("issues", {}), ("issues", [None]), ("issues", [{"severity": "info"}]), ("is_valid", "true")):
            with self.subTest(field=field):
                record = record_fixture()
                record[field] = value
                self.rejected(record, allow_warnings=True)

    def test_bad_batch_shapes_and_non_boolean_options_fail(self):
        for records in (None, {}, "records"):
            with self.subTest(records=records), self.assertRaises(ValidationError):
                validate_records(records)
        for value in ("false", 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_records([record_fixture()], allow_warnings=value)
        self.assertEqual(validate_records((record_fixture(),))[1], [])

    def test_empty_batch_is_an_explicit_failure_even_when_skipping_invalid(self):
        for skip_invalid in (False, True):
            with self.subTest(skip_invalid=skip_invalid), self.assertRaises(ValidationError) as context:
                validate_records([], skip_invalid=skip_invalid)
            self.assertIn("empty_batch", rejected_codes(context.exception.issues))


if __name__ == "__main__":
    unittest.main()
