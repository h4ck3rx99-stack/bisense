"""One official product-list row = one chunk.

The BIS "Products under Compulsory Certification" lists (Scheme-I ISI mark, Scheme-II CRS) hold ~924 rows.
Stored as whole category tables they were up to ~4,300 characters per chunk, and the embedding model and
reranker only read the first ~512 tokens, so rows late in a category were invisible (e.g. "Self-Ballasted
LED Lamps", ~2,400 characters into the CRS electronics table). Each row is now its own chunk:

    Product: Self-Ballasted LED Lamps for General Lighting Services · IS 16102 (Part 1):2017 · Scheme-II CRS · Order: ...

The category stays as the clause heading (metadata); citations still point at the category section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SEP = " · "
SCHEMES = {"ISI": "Scheme-I ISI mark", "CRS": "Scheme-II CRS"}
_ROW_RE = re.compile(
    r"^Product: (?P<product>.*?) · (?P<numbers>.*?)(?: — (?P<title>.*?))? · (?P<scheme>Scheme-I ISI mark|Scheme-II CRS)(?: · (?P<order>.*))?$", re.S
)


@dataclass
class ListRow:
    product: str
    numbers: str  # IS number cell as printed, e.g. "IS 16102 (Part 1):2017"
    title: str
    scheme: str  # "ISI" | "CRS"
    order: str
    denotified: bool


def scheme_of(list_title: str) -> str | None:
    t = list_title or ""
    if re.search(r"Scheme[- ]II\b|Compulsory Registration", t, re.I):
        return "CRS"
    if re.search(r"Scheme[- ]I\b|ISI Mark", t, re.I):
        return "ISI"
    return None


def format_row(product: str, numbers: str, title: str, scheme: str, order: str) -> str:
    head = f"{numbers} — {title}" if title and title.strip() != product.strip() else numbers
    parts = [f"Product: {product or title}", head, SCHEMES[scheme]]
    if order:
        parts.append(f"Status: {order}" if re.match(r"de-?notified", order, re.I) else f"Order: {order}")
    return SEP.join(" ".join(p.split()) for p in parts)


def parse_row(text: str) -> ListRow | None:
    m = _ROW_RE.match(text.strip())
    if not m:
        return None
    order = m.group("order") or ""
    denotified = order.startswith("Status:") and bool(re.search(r"de-?notified", order, re.I))
    order = re.sub(r"^(Order|Status): ", "", order)
    scheme = "CRS" if m.group("scheme") == SCHEMES["CRS"] else "ISI"
    return ListRow(m.group("product"), m.group("numbers"), m.group("title") or "", scheme, order, denotified)


def rows_from_table(table_rows: list[list[str]], scheme: str) -> list[str]:
    """Chunk texts for the body rows of a category table built by ingest/catalogue.py."""
    if not table_rows:
        return []
    header = [h.lower() for h in table_rows[0]]

    def col(name: str) -> int | None:
        return next((i for i, h in enumerate(header) if name in h), None)

    c_is, c_prod, c_title, c_order = col("is no"), col("product"), col("title"), col("notification")
    out = []
    for r in table_rows[1:]:

        def cell(i: int | None, row: list[str] = r) -> str:
            return row[i].strip() if i is not None and i < len(row) else ""

        if not cell(c_is):
            continue
        out.append(format_row(cell(c_prod), cell(c_is), cell(c_title), scheme, cell(c_order)))
    return out


_QCO_RE = re.compile(r"(?:^|\d+\.\s*)([A-Z][\w&,/' -]{2,70}?)\s*\(\s*Quality Control\s*\)\s*(?:\(?Amendment\)?\s*)?Order,?\s*(\d{4})", re.I)
_CRS_RE = re.compile(r"Compulsory Registration\)?\s*Order,?\s*(\d{4})", re.I)


def order_short(order: str | None) -> str | None:
    """A short name for the notification: "Helmet for Riders of Two Wheeler Motor Vehicles QCO 2020",
    "CRS Order 2012". None when the text has no recognisable order."""
    if not order:
        return None
    m = _QCO_RE.search(order)
    if m:
        name = re.sub(r"^\d+\.\s*", "", m.group(1)).strip(" ,.-")
        return f"{name} QCO {m.group(2)}"
    m = _CRS_RE.search(order)
    if m:
        return f"CRS Order {m.group(1)}"
    return None
