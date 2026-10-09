"""Explicit, non-destructive initialization and compatibility checks for v3."""

from pathlib import Path
import re

from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row


class LoadError(RuntimeError):
    """An atomic load could not be completed; source/connection secrets are omitted."""


TABLE_COLUMNS = {
    "customers": ("customer_name",),
    "contacts": ("contact_name", "telephone", "email"),
    "vessels": ("vessel_name", "hull_no", "steering_gear_type", "main_pump_type", "servo_pump_type"),
    "quotations": ("quotation_ref_no", "quotation_type", "quotation_year", "sequence_no", "suffix",
                   "quotation_date", "subject", "currency", "document_discount_rate",
                   "document_discount_amount", "document_total_amount", "lead_time_text",
                   "delivery_terms", "payment_terms", "additional_terms", "source_file_name", "source_sheet_name"),
    "quotation_vessels": ("quoted_vessel_name", "quoted_hull_no"),
    "quotation_items": ("line_no", "line_text_raw", "item_type", "item_name", "description", "part_no",
                        "quantity", "quantity_unit", "unit_price", "base_amount", "discount_rate", "quoted_amount", "remark"),
    "kit_documents": ("document_type", "source_file_name", "source_sheet_name", "title_raw", "currency",
                      "total_label_raw", "displayed_total_amount"),
    "kit_component_groups": ("group_type", "group_name_raw", "equipment_model", "equipment_quantity", "equipment_unit", "group_amount"),
    "kit_components": ("line_no", "part_name", "part_no", "quantity", "quantity_unit", "unit_price", "amount", "remark"),
    "service_details": ("working_place", "service_engineer_count", "supporting_worker_count", "working_days",
                        "includes_travel_days", "working_details", "steering_gear_type", "main_pump_type", "servo_pump_type"),
}

PRIMARY_KEYS = {
    "customers": "customer_id", "contacts": "contact_id", "vessels": "vessel_id",
    "quotations": "quotation_id", "quotation_items": "quotation_item_id",
    "kit_documents": "kit_document_id", "kit_component_groups": "kit_component_group_id",
    "kit_components": "kit_component_id",
}

FOREIGN_KEYS = {
    "contacts": ("customer_id",), "vessels": ("customer_id",),
    "quotations": ("customer_id", "contact_id"),
    "quotation_vessels": ("quotation_id", "vessel_id"),
    "quotation_items": ("quotation_id",),
    "kit_documents": ("quotation_id", "kit_quotation_item_id"),
    "kit_component_groups": ("kit_document_id",), "kit_components": ("kit_component_group_id",),
    "service_details": ("quotation_id",),
}

REQUIRED_VALUES = {
    "customers": {"customer_id", "customer_name", "created_at"},
    "contacts": {"contact_id", "customer_id"}, "vessels": {"vessel_id", "customer_id"},
    "quotations": {"quotation_id", "quotation_ref_no", "quotation_type", "customer_id", "currency"},
    "quotation_vessels": {"quotation_id", "vessel_id"},
    "quotation_items": {"quotation_item_id", "quotation_id", "item_type"},
    "kit_documents": {"kit_document_id", "quotation_id", "document_type"},
    "kit_component_groups": {"kit_component_group_id", "kit_document_id", "group_type", "group_name_raw"},
    "kit_components": {"kit_component_id", "kit_component_group_id"},
    "service_details": {"quotation_id"},
}

FK_TARGETS = {
    ("contacts", "customer_id"): ("customers", "customer_id"),
    ("vessels", "customer_id"): ("customers", "customer_id"),
    ("quotations", "customer_id"): ("customers", "customer_id"),
    ("quotations", "contact_id"): ("contacts", "contact_id"),
    ("quotation_vessels", "quotation_id"): ("quotations", "quotation_id"),
    ("quotation_vessels", "vessel_id"): ("vessels", "vessel_id"),
    ("quotation_items", "quotation_id"): ("quotations", "quotation_id"),
    ("kit_documents", "quotation_id"): ("quotations", "quotation_id"),
    ("kit_documents", "kit_quotation_item_id"): ("quotation_items", "quotation_item_id"),
    ("kit_component_groups", "kit_document_id"): ("kit_documents", "kit_document_id"),
    ("kit_components", "kit_component_group_id"): ("kit_component_groups", "kit_component_group_id"),
    ("service_details", "quotation_id"): ("quotations", "quotation_id"),
}


def schema_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
        raise ValueError("Schema must be an ASCII identifier of at most 63 characters")
    if value.lower().startswith("pg_") or value.lower() == "information_schema":
        raise ValueError("System schemas cannot be used for ETL")
    return value


def require_idle(connection):
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise LoadError("Use an idle connection so ETL can own and commit its transaction")


def check_schema(connection, schema="public"):
    """Verify all required tables/columns and the unique quotation reference."""
    schema = schema_name(schema)
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute("""SELECT table_name, column_name, data_type, numeric_precision, numeric_scale,
                                 character_maximum_length, is_identity, column_default, is_nullable
                          FROM information_schema.columns
                          WHERE table_schema = %s""", (schema,))
        present = {}
        for table, column, *details in cursor.fetchall():
            present.setdefault(table, {})[column] = details
        for table, columns in TABLE_COLUMNS.items():
            required = set(columns) | set(FOREIGN_KEYS.get(table, ())) | REQUIRED_VALUES[table]
            if table in PRIMARY_KEYS:
                required.add(PRIMARY_KEYS[table])
            if not required.issubset(present.get(table, {})):
                raise LoadError("Database schema is missing v3 tables/columns; initialize an empty schema explicitly or migrate it separately")
            for column in required:
                data_type, precision, scale, length, identity, default, nullable = present[table][column]
                if column.endswith("_id") or column in {"quotation_year", "sequence_no", "line_no", "quantity", "equipment_quantity", "service_engineer_count", "supporting_worker_count", "working_days"}:
                    valid = data_type == "integer"
                elif column.endswith("_amount") or column in {"unit_price", "amount"}:
                    valid = data_type == "numeric" and precision == 14 and scale == 2
                elif column.endswith("_rate"):
                    valid = data_type == "numeric" and precision == 5 and scale == 2
                elif column == "currency":
                    valid = data_type == "character" and length == 3
                elif column in {"quotation_date", "created_at"}:
                    valid = data_type == "date"
                elif column == "includes_travel_days":
                    valid = data_type == "boolean"
                else:
                    valid = data_type == "text"
                if not valid:
                    raise LoadError(f"Schema column {table}.{column} has an incompatible type; migrate it separately")
                if column in REQUIRED_VALUES[table] and nullable != "NO":
                    raise LoadError(f"Schema column {table}.{column} must be NOT NULL")
                if PRIMARY_KEYS.get(table) == column and identity != "YES" and default is None:
                    raise LoadError(f"Schema {table} primary key must be generated by PostgreSQL")
        cursor.execute("""SELECT c.relname, ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY keys(num, ord)
                                  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = keys.num ORDER BY keys.ord)
                          FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                          JOIN pg_namespace n ON n.oid = c.relnamespace
                          WHERE n.nspname = %s AND k.contype = 'p'""", (schema,))
        primary = {table: columns for table, columns in cursor.fetchall()}
        for table in TABLE_COLUMNS:
            columns = ["quotation_id", "vessel_id"] if table == "quotation_vessels" else [PRIMARY_KEYS.get(table, "quotation_id")]
            if primary.get(table) != columns:
                raise LoadError(f"Schema {table} has an incompatible primary key")
        cursor.execute("""SELECT source.relname, sa.attname, target.relname, ta.attname, tn.nspname
                          FROM pg_constraint k JOIN pg_class source ON source.oid = k.conrelid
                          JOIN pg_namespace sn ON sn.oid = source.relnamespace
                          JOIN pg_class target ON target.oid = k.confrelid
                          JOIN pg_namespace tn ON tn.oid = target.relnamespace
                          JOIN LATERAL unnest(k.conkey, k.confkey) keys(src, dst) ON TRUE
                          JOIN pg_attribute sa ON sa.attrelid = source.oid AND sa.attnum = keys.src
                          JOIN pg_attribute ta ON ta.attrelid = target.oid AND ta.attnum = keys.dst
                          WHERE sn.nspname = %s AND k.contype = 'f' AND k.convalidated""", (schema,))
        foreign = {(table, column): (target, target_column, target_schema)
                   for table, column, target, target_column, target_schema in cursor.fetchall()}
        for key, target in FK_TARGETS.items():
            if foreign.get(key) != (*target, schema):
                raise LoadError(f"Schema {key[0]}.{key[1]} has a missing or incompatible foreign key")
        cursor.execute("""SELECT 1 FROM pg_index i
                          JOIN pg_class c ON c.oid = i.indrelid
                          JOIN pg_namespace n ON n.oid = c.relnamespace
                          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0]
                          WHERE n.nspname = %s AND c.relname = 'quotations'
                            AND a.attname = 'quotation_ref_no' AND i.indisunique AND i.indisvalid
                            AND i.indnkeyatts = 1 AND i.indpred IS NULL AND i.indexprs IS NULL""", (schema,))
        if cursor.fetchone() is None:
            raise LoadError("Schema requires a unique quotation_ref_no index")


def initialize_schema(connection, schema="public"):
    """Create v3 once, or verify an existing installation; never drop/alter data.

    A partially initialized or unrelated populated schema is rejected. The SQL
    source remains the repository's unchanged database/schema_v3.sql.
    """
    schema = schema_name(schema)
    require_idle(connection)
    script = (Path(__file__).resolve().parents[2] / "database/schema_v3.sql").read_text(encoding="utf-8")
    script = re.sub(r"^\s*(?:BEGIN|COMMIT);\s*$", "", script, flags=re.M)
    with connection.transaction():
        with connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"marine-sales-etl:{schema}",))
            cursor.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
                              WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')""", (schema,))
            objects = {row[0] for row in cursor.fetchall()}
            if objects:
                if not set(TABLE_COLUMNS).issubset(objects):
                    raise LoadError("Initialization requires an empty schema; existing objects were preserved")
                check_schema(connection, schema)
                return
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute(script)
            check_schema(connection, schema)
