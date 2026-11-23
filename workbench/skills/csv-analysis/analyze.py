import csv
import io
import json
import math
import sys


def profile_csv(contents):
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = contents.decode("gb18030")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    headers = next((row for row in reader if row), [])
    if not 1 <= len(headers) <= 128:
        raise ValueError("CSV must have a header and between 1 and 128 columns.")

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
    for row in reader:
        if not row or (len(row) == 1 and not row[0].strip() and len(columns) > 1):
            continue
        if len(row) != len(columns):
            raise ValueError(
                f"CSV row ending at line {reader.line_num} has the wrong number of columns."
            )
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


if __name__ == "__main__":
    try:
        print(json.dumps(profile_csv(sys.stdin.buffer.read()), allow_nan=False))
    except (ValueError, csv.Error) as error:
        sys.exit(f"Invalid CSV: {error}")
