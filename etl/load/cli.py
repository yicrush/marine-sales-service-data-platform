"""Shared pipeline execution and reports; connection credentials never enter JSON."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import psycopg

from etl.transform import to_jsonable
from .loader import load_records
from .schema import LoadError, initialize_schema, schema_name
from .validation import ValidationError, validate_records


def add_load_arguments(parser):
    parser.add_argument("--database-url-env", default="DATABASE_URL", help="Environment variable containing the PostgreSQL DSN (default DATABASE_URL)")
    parser.add_argument("--schema", default="public", help="Target PostgreSQL schema")
    parser.add_argument("--init-schema", action="store_true", help="Explicitly initialize schema v3 in an empty schema; never drops existing data")
    parser.add_argument("--on-existing", choices=("skip", "error", "replace"), default="skip", help="How to handle an existing quotation reference (default skip)")
    parser.add_argument("--allow-warnings", action="store_true", help="Accept reviewed Transform warnings; validation errors still block loading")
    parser.add_argument("--skip-invalid", action="store_true", help="Reject invalid/ambiguous records and atomically load the remaining records")
    parser.add_argument("--dry-run", action="store_true", help="Extract/transform/validate without connecting to PostgreSQL")
    parser.add_argument("--report", type=Path, help="New JSON report path; default is a unique path under data/processed")


def report_path(value):
    if value is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        value = Path("data/processed") / f"etl-{stamp}.json"
    if value.suffix.lower() != ".json":
        raise ValueError("Report must use a .json extension")
    if value.exists():
        raise ValueError("Report already exists; choose another path to preserve previous results")
    return value


def execute_payload(payload, args, parser):
    """Validate before DB access, write staging/diagnostics, and return exit status.

    The report is opened exclusively before loading to ensure a report path is
    writable. It is a local artifact, not an atomic distributed audit log; callers
    should retain backups and use the reported quotation IDs for database checks.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        parser.exit(2, "Input must be a Transform workbook object with a records list\n")
    try:
        schema_name(args.schema)
        output = report_path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        stream = output.open("x", encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Unable to prepare report: {exc}\n")
    report = {"status": "pending", "stage": "validation", "schema": args.schema,
              "on_existing": args.on_existing, "transformed": to_jsonable(payload), "load": None}
    status = 0
    try:
        accepted, rejected = validate_records(payload["records"], allow_warnings=args.allow_warnings,
                                              skip_invalid=args.skip_invalid)
        if args.dry_run:
            report["status"] = "dry_run"
            report["load"] = {"accepted": len(accepted), "rejected": len(rejected), "rejections": rejected}
            print(f"Dry run: {len(accepted)} accepted, {len(rejected)} rejected; no database writes.")
        elif not accepted:
            report["status"] = "no_records_loaded"
            report["load"] = {"inserted": 0, "skipped": 0, "replaced": 0, "rejected": len(rejected), "records": [], "rejections": rejected}
            print(f"No records loaded; {len(rejected)} rejected.")
        else:
            database_url = os.environ.get(args.database_url_env)
            if not database_url:
                raise LoadError(f"Set {args.database_url_env} securely before loading; --dry-run works without a database")
            report["stage"] = "database"
            try:
                with psycopg.connect(database_url, autocommit=True, connect_timeout=10,
                                     application_name="marine-sales-etl") as connection:
                    if args.init_schema:
                        initialize_schema(connection, args.schema)
                    result = load_records(connection, payload["records"], schema=args.schema,
                                          existing_policy=args.on_existing,
                                          allow_warnings=args.allow_warnings, skip_invalid=args.skip_invalid)
            except psycopg.Error as exc:
                # libpq/server messages can contain private hosts, identifiers or rows.
                raise LoadError(f"PostgreSQL connection/schema operation failed ({exc.sqlstate or 'connection_error'})") from exc
            report["status"] = "committed"
            report["load"] = result
            print(f"Committed: {result['inserted']} inserted, {result['skipped']} skipped, "
                  f"{result['replaced']} replaced, {result['rejected']} rejected.")
        # Explicit filtering is successful but not a full successful import.
        status = 1 if rejected else 0
    except ValidationError as exc:
        report["status"] = "validation_failed"
        report["load"] = {"inserted": 0, "skipped": 0, "replaced": 0,
                          "rejected": len(exc.issues), "rejections": exc.issues}
        print(f"Validation failed for {len(exc.issues)} record(s); no database writes.")
        status = 1
    except (LoadError, ValueError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        print(f"ETL failed: {exc}")
        status = 2
    finally:
        with stream:
            json.dump(to_jsonable(report), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print(f"Saved report: {output}")
    return status
