"""A single local command for Extract -> Transform -> PostgreSQL Load."""

import argparse
from pathlib import Path
import sys

from etl.load.cli import add_load_arguments, execute_payload
from etl.transform.workbook import transform_workbook


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run quotation Excel Extract -> Transform -> Load")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sheet", action="append", dest="sheet_names", help="Exact quotation sheet; repeat to select several. Default all detected M/O sheets")
    parser.add_argument("--currency", help="Confirmed quotation currency override")
    parser.add_argument("--kit-sheet", action="append", default=[], dest="kit_sheet_names", help="Explicitly associated KIT sheet; requires one selected quotation")
    parser.add_argument("--cost-sheet", action="append", default=[], dest="cost_sheet_names", help="Explicitly associated cost sheet; requires one selected quotation")
    parser.add_argument("--kit-currency", help="Confirmed KIT currency override")
    parser.add_argument("--cost-currency", help="Confirmed cost currency override")
    add_load_arguments(parser)
    args = parser.parse_args(argv)
    if args.report and args.report.exists():
        parser.error("Report already exists; select a new --report path")
    try:
        payload = transform_workbook(args.workbook, sheet_names=args.sheet_names,
                                     currency=args.currency, kit_sheet_names=args.kit_sheet_names,
                                     cost_sheet_names=args.cost_sheet_names,
                                     kit_currency=args.kit_currency, cost_currency=args.cost_currency)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Extract/Transform failed: {exc}\n")
    return execute_payload(payload, args, parser)


if __name__ == "__main__":
    sys.exit(main())
