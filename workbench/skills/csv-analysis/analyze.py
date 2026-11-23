import csv
import io
import json
import math
import operator
import sys
from decimal import Decimal, InvalidOperation, localcontext

COMPARISONS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}
MAX_GROUPS = 200


def _read_csv(contents):
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = contents.decode("gb18030")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    headers = next((row for row in reader if row), [])
    if not 1 <= len(headers) <= 128:
        raise ValueError("CSV must have a header and between 1 and 128 columns.")
    return headers, reader


def _rows(reader, width):
    for row in reader:
        if not row or (len(row) == 1 and not row[0].strip() and width > 1):
            continue
        if len(row) != width:
            raise ValueError(
                f"CSV row ending at line {reader.line_num} has the wrong number of columns."
            )
        yield row


def profile_csv(contents):
    headers, reader = _read_csv(contents)
    columns = [
        {
            "name": " ".join(header.split())[:100] or f"Column {index}",
            "filled": 0,
            "numeric": 0,
            "min": None,
            "max": None,
        }
        for index, header in enumerate(headers, 1)
    ]
    rows = 0
    for row in _rows(reader, len(columns)):
        rows += 1
        for column, raw in zip(columns, row, strict=True):
            value = raw.strip()
            if not value:
                continue
            column["filled"] += 1
            try:
                number = float(value)
            except ValueError:
                continue
            if not math.isfinite(number):
                continue
            if column["numeric"] == 0:
                column["min"] = column["max"] = number
            else:
                column["min"] = min(column["min"], number)
                column["max"] = max(column["max"], number)
            column["numeric"] += 1

    return {"rows": rows, "columns": columns}


def _decimal(value):
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Expected a finite decimal number.") from error
    if not number.is_finite() or number.adjusted() > 308 or number.as_tuple().exponent < -324:
        raise ValueError("Expected a finite decimal number within the supported range.")
    return number


def _matches(raw, compare, target):
    value = raw.strip()
    if isinstance(target, str):
        return compare(value, target)
    try:
        return compare(_decimal(value), target)
    except ValueError:
        return False


def _decimal_text(amount):
    if amount is None:
        return None
    return format(amount.normalize(), "f") if amount else "0"


def query_csv(contents, plan):
    headers, reader = _read_csv(contents)
    filters = []
    for condition in plan["filters"]:
        op = condition["op"]
        target = condition["value"].strip()
        if op not in {"eq", "ne"}:
            target = _decimal(target)
        filters.append((condition["column"] - 1, COMPARISONS[op], target))

    group_column = plan["group_by"]
    value_column = plan["value_column"]
    groups = {}
    matched_rows = missing_values = 0
    with localcontext() as context:
        # Cover the supported decimal range and the maximum row count in a 5 MiB upload.
        context.prec = 650
        for row in _rows(reader, len(headers)):
            if not all(
                _matches(row[column], compare, target) for column, compare, target in filters
            ):
                continue
            matched_rows += 1
            label = row[group_column - 1].strip() if group_column is not None else ""
            groups.setdefault(label, None)
            if len(groups) > MAX_GROUPS:
                raise ValueError(
                    f"More than {MAX_GROUPS} groups. Narrow the filters or group by another column."
                )
            amount = Decimal(1)
            if value_column is not None:
                raw = row[value_column - 1].strip()
                if not raw:
                    missing_values += 1
                    continue
                try:
                    amount = _decimal(raw)
                except ValueError as error:
                    raise ValueError(
                        f"Cannot sum a non-numeric value in column {value_column} "
                        f"at CSV line {reader.line_num}."
                    ) from error

            previous = groups[label]
            groups[label] = amount if previous is None else previous + amount

        total = None
        if value_column is None or matched_rows > missing_values:
            total = sum((amount for amount in groups.values() if amount is not None), Decimal(0))
        if group_column is None:
            groups.setdefault("", total)
        ordered = sorted(
            groups.items(), key=lambda item: (item[1] is None, -abs(item[1] or 0), item[0])
        )
        result = [
            {
                "label": label,
                "value": _decimal_text(amount),
                "share": f"{amount / total:.2%}" if total and amount is not None else None,
            }
            for label, amount in ordered
        ]
        return {
            "matched_rows": matched_rows,
            "missing_values": missing_values,
            "total": _decimal_text(total),
            "groups": result,
        }


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--query"]:
            plan = json.loads(sys.stdin.buffer.readline())
            result = query_csv(sys.stdin.buffer.read(), plan)
        else:
            result = profile_csv(sys.stdin.buffer.read())
        print(json.dumps(result, allow_nan=False))
    except (ValueError, csv.Error) as error:
        sys.exit(f"Invalid CSV: {error}")
