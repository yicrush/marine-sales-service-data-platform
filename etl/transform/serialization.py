"""JSON conversion that preserves exact decimals rather than emitting floats."""

from datetime import date, datetime
from decimal import Decimal


def to_jsonable(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, float):
        # Raw non-finite values must not produce nonstandard JSON tokens.
        import math
        if not math.isfinite(value):
            return str(value)
    return value
