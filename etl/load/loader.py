"""Atomic PostgreSQL loading of validated schema-v3 Transform records."""

import psycopg
from psycopg import sql
from psycopg.rows import tuple_row

from .schema import LoadError, TABLE_COLUMNS, check_schema, require_idle, schema_name
from .validation import validate_records


def _insert(cursor, schema, table, row, foreign=None, returning=None):
    values = {column: row.get(column) for column in TABLE_COLUMNS[table]}
    values.update(foreign or {})
    query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
        sql.Identifier(schema), sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in values),
        sql.SQL(", ").join(sql.Placeholder() for _ in values),
    )
    if returning:
        query += sql.SQL(" RETURNING {}").format(sql.Identifier(returning))
    cursor.execute(query, tuple(values.values()))
    return cursor.fetchone()[0] if returning else None


def _master(cursor, schema, table, row, key_columns, primary_key, foreign=None):
    values = dict(row)
    values.update(foreign or {})
    condition = sql.SQL(" AND ").join(sql.SQL("{} IS NOT DISTINCT FROM %s").format(sql.Identifier(column))
                                       for column in key_columns)
    cursor.execute(sql.SQL("SELECT {} FROM {}.{} WHERE {} ORDER BY {} LIMIT 2").format(
        sql.Identifier(primary_key), sql.Identifier(schema), sql.Identifier(table), condition,
        sql.Identifier(primary_key),
    ), tuple(values.get(column) for column in key_columns))
    matches = cursor.fetchall()
    if len(matches) > 1:
        raise LoadError(f"Ambiguous existing {table} master records; resolve duplicates before loading")
    if matches:
        return matches[0][0]
    return _insert(cursor, schema, table, row, foreign, primary_key)


def _load_one(cursor, schema, record, existing_policy):
    quotation = record["quotation"]
    reference = quotation["quotation_ref_no"]
    cursor.execute(sql.SQL("SELECT quotation_id FROM {}.quotations WHERE quotation_ref_no = %s FOR UPDATE").format(sql.Identifier(schema)), (reference,))
    existing = cursor.fetchone()
    if existing and existing_policy == "error":
        raise LoadError("A quotation reference already exists; batch rolled back")
    if existing and existing_policy == "skip":
        return {"status": "skipped", "quotation_id": existing[0],
                "quotation_ref_no": reference, "source_sheet_name": quotation.get("source_sheet_name")}

    customer_id = _master(cursor, schema, "customers", record["customer"],
                          ("customer_name",), "customer_id")
    contact_id = None
    if record.get("contact") is not None:
        contact_id = _master(cursor, schema, "contacts", record["contact"],
                             ("customer_id", "contact_name", "telephone", "email"),
                             "contact_id", {"customer_id": customer_id})
    foreign = {"customer_id": customer_id, "contact_id": contact_id}
    if existing:
        quotation_id = existing[0]
        cursor.execute(sql.SQL("""SELECT 1 FROM {}.kit_documents d
                                  JOIN {}.quotation_items i ON i.quotation_item_id = d.kit_quotation_item_id
                                  WHERE i.quotation_id = %s AND d.quotation_id <> %s LIMIT 1""").format(
            sql.Identifier(schema), sql.Identifier(schema)), (quotation_id, quotation_id))
        if cursor.fetchone() is not None:
            raise LoadError("Existing quotation items are referenced by another quotation; resolve those links before replacement")
        values = {column: quotation.get(column) for column in TABLE_COLUMNS["quotations"]}
        values.update(foreign)
        cursor.execute(sql.SQL("UPDATE {}.quotations SET {} WHERE quotation_id = %s").format(
            sql.Identifier(schema), sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(column)) for column in values),
        ), (*values.values(), quotation_id))
        # Remove owned children in dependency order. Master records remain intact.
        for table in ("kit_documents", "quotation_items", "quotation_vessels", "service_details"):
            cursor.execute(sql.SQL("DELETE FROM {}.{} WHERE quotation_id = %s").format(
                sql.Identifier(schema), sql.Identifier(table)), (quotation_id,))
        status = "replaced"
    else:
        quotation_id = _insert(cursor, schema, "quotations", quotation, foreign, "quotation_id")
        status = "inserted"
    for vessel, link in zip(record.get("vessels", []), record.get("quotation_vessels", [])):
        vessel_id = _master(cursor, schema, "vessels", vessel,
                            ("customer_id", "vessel_name", "hull_no"), "vessel_id", {"customer_id": customer_id})
        _insert(cursor, schema, "quotation_vessels", link,
                {"quotation_id": quotation_id, "vessel_id": vessel_id})
    for item in record.get("quotation_items", []):
        _insert(cursor, schema, "quotation_items", item, {"quotation_id": quotation_id})
    if record.get("service_details") is not None:
        _insert(cursor, schema, "service_details", record["service_details"], {"quotation_id": quotation_id})
    for supporting in record.get("kit_documents", []):
        document_id = _insert(cursor, schema, "kit_documents", supporting["document"],
                              {"quotation_id": quotation_id, "kit_quotation_item_id": None}, "kit_document_id")
        for group in supporting.get("groups", []):
            group_id = _insert(cursor, schema, "kit_component_groups", group["group"],
                               {"kit_document_id": document_id}, "kit_component_group_id")
            for component in group.get("components", []):
                _insert(cursor, schema, "kit_components", component, {"kit_component_group_id": group_id})
    return {"status": status, "quotation_id": quotation_id,
            "quotation_ref_no": reference, "source_sheet_name": quotation.get("source_sheet_name")}


def load_records(connection, records, *, schema="public", existing_policy="skip",
                 allow_warnings=False, skip_invalid=False):
    """Validate a batch, then commit all accepted records in one transaction.

    Exact customer/contact/vessel keys are reused without fuzzy matching or master
    updates. Advisory locking serializes this loader within a database/schema;
    external writers still need their own uniqueness constraints/coordination.
    Existing references default to a reported skip. Replace is explicit, preserves
    the quotation ID, and replaces only its owned child rows. Errors roll back the
    entire accepted batch, including records loaded earlier in that batch.
    """
    if existing_policy not in ("skip", "error", "replace"):
        raise ValueError("existing_policy must be skip, error, or replace")
    schema = schema_name(schema)
    accepted, rejected = validate_records(records, allow_warnings=allow_warnings, skip_invalid=skip_invalid)
    require_idle(connection)
    outcomes = []
    if accepted:
        try:
            with connection.transaction():
                with connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"marine-sales-etl:{schema}",))
                    check_schema(connection, schema)
                    for record in accepted:
                        outcomes.append(_load_one(cursor, schema, record, existing_policy))
        except psycopg.Error as exc:
            state = exc.sqlstate or "connection_error"
            raise LoadError(f"Database transaction failed ({state}); verify database state before retrying") from exc
    return {"inserted": sum(row["status"] == "inserted" for row in outcomes),
            "skipped": sum(row["status"] == "skipped" for row in outcomes),
            "replaced": sum(row["status"] == "replaced" for row in outcomes),
            "rejected": len(rejected), "records": outcomes, "rejections": rejected}
