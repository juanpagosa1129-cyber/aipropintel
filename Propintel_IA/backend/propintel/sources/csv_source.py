from __future__ import annotations

import csv
from io import StringIO


def parse_csv_text(csv_text: str) -> list[dict]:
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("CSV sin encabezados")
    return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in reader]
