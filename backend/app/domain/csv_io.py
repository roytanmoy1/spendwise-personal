import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO

from app.domain.insights import CATEGORY_KEYWORDS, categorize_merchant

KNOWN_CATEGORIES = {category.casefold(): category for category, _ in CATEGORY_KEYWORDS}
KNOWN_CATEGORIES["other"] = "Other"
KNOWN_METHODS = {"upi", "card", "cash", "netbanking"}
CSV_FIELDS = ("merchant", "amount", "date", "category", "method", "city", "note")


def parse_transactions(csv_text: str, *, now: datetime) -> list[dict]:
    if len(csv_text.encode("utf-8")) > 131_072:
        raise ValueError("CSV must be 128 KB or smaller")
    reader = csv.DictReader(StringIO(csv_text, newline=""))
    if not reader.fieldnames or not {"merchant", "amount", "date", "method"}.issubset(
        reader.fieldnames
    ):
        raise ValueError("CSV needs merchant, amount, date and method columns")
    rows = []
    for line_number, row in enumerate(reader, start=2):
        # ponytail: 200 rows per atomic import; use queued jobs for larger files.
        if line_number > 201:
            raise ValueError("Import at most 200 transactions at once")
        if None in row:
            raise ValueError(f"Row {line_number} has too many columns")
        merchant = (row.get("merchant") or "").strip()
        if not 2 <= len(merchant) <= 100:
            raise ValueError(f"Row {line_number} has an invalid merchant")
        try:
            amount = Decimal(row.get("amount") or "") * 100
            if (
                not amount.is_finite()
                or amount != amount.to_integral_value()
                or not 0 < amount <= 100_000_000_000
            ):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ValueError(f"Row {line_number} has an invalid amount") from None
        try:
            occurred_at = datetime.fromisoformat(
                row["date"].strip().replace("Z", "+00:00")
            )
            if occurred_at.tzinfo is None or occurred_at > now + timedelta(minutes=5):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError(f"Row {line_number} has an invalid date") from None
        method = (row.get("method") or "").strip().casefold()
        if method not in KNOWN_METHODS:
            raise ValueError(f"Row {line_number} has an invalid method")
        category = (row.get("category") or "").strip()
        normalized_category = (
            KNOWN_CATEGORIES.get(category.casefold())
            if category
            else categorize_merchant(merchant)
        )
        if normalized_category is None:
            raise ValueError(f"Row {line_number} has an invalid category")
        city = (row.get("city") or "").strip()
        note = (row.get("note") or "").strip()
        if len(city) > 80 or len(note) > 240:
            raise ValueError(f"Row {line_number} has a field that is too long")
        rows.append(
            {
                "merchant": merchant,
                "amount_minor": int(amount),
                "occurred_at": occurred_at.astimezone(UTC),
                "method": method,
                "category": normalized_category,
                "city": city or None,
                "note": note or None,
            }
        )
    if not rows:
        raise ValueError("CSV has no transactions")
    return rows


def export_transactions(transactions) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(CSV_FIELDS)
    for transaction in transactions:
        # Spreadsheets interpret leading operators as formulas even in quoted CSV fields.
        def plain_text(value):
            text = str(value or "")
            return (
                f"'{text}"
                if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                else text
            )

        writer.writerow(
            (
                plain_text(transaction.merchant),
                f"{Decimal(transaction.amount_minor) / 100:.2f}",
                transaction.occurred_at.isoformat(),
                plain_text(transaction.category),
                plain_text(transaction.method),
                plain_text(transaction.city),
                plain_text(transaction.note),
            )
        )
    return output.getvalue()
