# Extract → Transform

The Transform stage normalizes the existing Extract dictionaries according to
`data_dictionary_v3.md` and `schema_v3.sql`. It does not write to PostgreSQL or
generate primary/foreign keys. Database IDs, customer deduplication, vessel
matching and insert transactions belong to the future Load stage.

## Run locally

From the repository root, use Python 3.12 and `openpyxl` 3.1.5 (the prepared
`.venv` already has it). If creating a new environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install openpyxl==3.1.5
```

Select a quotation using its exact worksheet name, rather than assuming the
workbook contains only M or only O quotations:

```bash
.venv/bin/python -m etl.transform 'data/raw/KP-M-Q-26-000 FROM START HERE.xlsx' \
  --sheet 'quote25-002-1' --output data/processed/m-sample.json

.venv/bin/python -m etl.transform 'data/raw/KP-O-Q-26-000.xlsx' \
  --sheet '26-011' --output data/processed/o-sample.json
```

Omitting `--sheet` transforms all sheets whose references are detected as M/O.
Other sheets are listed in `skipped_sheets`. Use `--strict` to return exit code 1
when validation errors exist; the JSON report is still written for review.
Exit code 0 without `--strict` means the report was produced, not that every
record is suitable for loading. Existing output files are never overwritten.

Only attach KIT and cost sheets whose association with the selected quotation
has been confirmed. Select exactly one quotation when using these options:

```bash
.venv/bin/python -m etl.transform data/raw/your-workbook.xlsx \
  --sheet 'confirmed-quotation-sheet' \
  --kit-sheet 'confirmed-kit-sheet' --cost-sheet 'confirmed-cost-sheet' \
  --kit-currency USD --cost-currency KRW \
  --output data/processed/quotation-with-support.json
```

`--currency`, `--kit-currency`, and `--cost-currency` are overrides for confirmed
business rules, not guesses. Without an override, the workbook reader uses
explicit currency evidence. A bare dollar symbol or a cost worksheet name alone
does not identify a currency.

Input workbooks are read without saving. Keep original workbooks and generated
JSON in the ignored `data/raw` and `data/processed` directories. Output includes
raw source text and may contain confidential customer/contact and price data;
do not commit it. Synthetic tests contain no original business information.

## Python API and output

```python
from etl.transform import transform_quotation, transform_kit_document, to_jsonable

result = transform_quotation(
    extracted_data,
    source_file_name="quotations.xlsx",
    currency="USD",  # confirmed source/business rule
    discount_rate_is_fraction=True,  # only when the source is Excel percent format
)
```

Each record contains `quotation`, `customer`, optional `contact`, parallel
`vessels` / `quotation_vessels` entries, `quotation_items`, optional
`service_details`, and explicitly associated `kit_documents`. Each KIT document
contains `document` and `groups`, with each group containing `group` and
`components`. These nested relationships stand in place of generated database
IDs. Optional `pricing_context` preserves prices displayed per vessel/unit when
an aggregate document total is unknown. `raw` retains an independent copy of the Extract output; inputs are not
mutated. `issues` holds severity, code, field and message. `is_valid` means no
validation **errors** were found; warnings still need review before loading.

Money remains `Decimal` in Python. `to_jsonable` writes money as decimal strings,
not floats, and dates as ISO strings. Parse those strings back to Decimal in Load.

## Rules and current limits

- Blank values become `None`; 0 stays 0. Labels are removed from header/term
  values while original text remains in `raw`.
- Full quotation references and suffixes are preserved. References must contain
  M/O type, a year from 2000 onward, and a positive sequence. Template sequence
  `000` is flagged. Customer/vessel spelling is not corrected or deduplicated.
- ISO dates, datetime/date objects, and supported named-month dates are accepted.
  Ambiguous numeric dates and typos such as `Junly` require review.
- Currency is not silently defaulted to USD. Missing quotation currency is an
  error because the v3 quotation table requires it.
- Integer columns reject fractional quantities, booleans, negatives and overflow.
  Quantity text such as `2 set` and `2(SET)` is split. Ambiguous packaging text and
  supply-unavailable statements remain in `raw` and are flagged.
- Money must fit nonnegative NUMERIC(14,2), with no implicit rounding. Displayed
  amounts and discounts are retained. Base line amount may be quantity × unit
  price when absent; missing component amounts are not calculated. Discrepancies
  between displayed totals and line/component sums produce warnings.
- Excel percentage formatting determines whether a numeric document discount
  such as `0.3` means 30%. The pure API defaults to percentage points unless
  `discount_rate_is_fraction=True` is passed explicitly.
- A displayed amount `USD 15,000 / VESSEL` retains the normalized amount and basis
  in `pricing_context`, leaves aggregate `document_total_amount` as `None`, and
  raises a warning. No vessel count is assumed to calculate a total.
- Item text retains line breaks. Separate Item/Description fields are combined
  with explicit labels. Uncertain categories stay `UNKNOWN`; unfamiliar KIT
  groups stay `OTHERS` with a warning. Part numbers are not inferred.
- Explicit lettered O expense summaries become SERVICE/KIT/EXPENSE lines.
  Supported `before -> after` prices retain both base and final amounts. Detail
  calculation lines are not counted again. Unsupported expense formats stay in
  raw text with warnings rather than receiving guessed prices.
- Service engineer, supporting worker and day counts are parsed only from
  explicit service statements. Travel-day inclusion stays `None` unless stated.
  Master vessel equipment is not inferred from quotation-time service text.
- KIT and cost documents stay separate. A document is not automatically linked
  to an individual KIT quotation item. Model/count parsing requires an explicit
  `(MODEL: 2 sets)` heading. Unknown groups and shifted source columns need review.
- Extract still assumes particular M table and KIT column layouts. Empty item
  extraction, unsupported source layouts, ambiguous metadata and uncached Excel
  formulas are reported. Transform does not recalculate Excel formulas.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_transform*.py' -v
```

These tests use synthetic dictionaries and workbooks. `etl/test_extract.py` is
an older manual runner requiring private files and hardcoded worksheet names;
it is not the Transform automated test suite.
