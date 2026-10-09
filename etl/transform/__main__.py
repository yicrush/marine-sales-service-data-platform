"""Run Extract -> Transform locally; output includes confidential source data."""

import argparse
import json
from pathlib import Path
import sys

from .serialization import to_jsonable
from .workbook import transform_workbook


def main(argv=None):
    parser = argparse.ArgumentParser(description="Transform quotation Excel sheets into schema-v3 staging JSON")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sheet", action="append", dest="sheet_names", help="Exact quotation sheet name; repeat to select several. Default: all M/O sheets")
    parser.add_argument("--currency", help="Explicit confirmed quotation currency; otherwise use unambiguous sheet evidence")
    parser.add_argument("--kit-sheet", action="append", default=[], dest="kit_sheet_names", help="KIT sheet associated explicitly with the one selected quotation")
    parser.add_argument("--cost-sheet", action="append", default=[], dest="cost_sheet_names", help="Cost sheet associated explicitly with the one selected quotation")
    parser.add_argument("--kit-currency", help="Confirmed KIT currency")
    parser.add_argument("--cost-currency", help="Confirmed cost currency")
    parser.add_argument("--output", type=Path, help="Default: data/processed/<workbook>.transformed.json")
    parser.add_argument("--strict", action="store_true", help="Write the report and return exit code 1 if any record has validation errors")
    args = parser.parse_args(argv)
    output = args.output or Path("data/processed") / f"{args.workbook.stem}.transformed.json"
    if output.suffix.lower() != ".json":
        parser.error("Output must be a .json file")
    if output.exists():
        parser.error("Output already exists; choose another --output path to preserve previous results")
    try:
        result = transform_workbook(args.workbook, sheet_names=args.sheet_names,
                                    currency=args.currency, kit_sheet_names=args.kit_sheet_names,
                                    cost_sheet_names=args.cost_sheet_names,
                                    kit_currency=args.kit_currency, cost_currency=args.cost_currency)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Transform failed: {exc}\n")
    records = result["records"]
    if not records:
        parser.exit(2, "No quotation sheets were found or selected\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting a report or an uploaded workbook.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(to_jsonable(result), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    errors = sum(issue["severity"] == "error" for record in records for issue in record["issues"])
    warnings = sum(issue["severity"] == "warning" for record in records for issue in record["issues"])
    print(f"Transformed {len(records)} quotation(s); {errors} error(s), {warnings} warning(s).")
    print(f"Saved: {output}")
    return 1 if args.strict and errors else 0


if __name__ == "__main__":
    sys.exit(main())
