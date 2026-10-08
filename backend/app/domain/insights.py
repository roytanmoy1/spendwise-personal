from collections import Counter
from datetime import UTC, datetime, timedelta

# ponytail: Keywords cover known merchants; add reviewed enrichment for broader accuracy.
CATEGORY_KEYWORDS = (
    ("Health", ("pharmacy", "hospital", "clinic", "medical")),
    ("Groceries", ("grocery", "supermarket", "kirana", "big bazaar")),
    ("Food", ("restaurant", "cafe", "coffee", "swiggy", "zomato")),
    ("Transport", ("petrol", "fuel", "uber", "ola", "metro")),
    ("Bills", ("electricity", "broadband", "airtel", "jio")),
    ("Entertainment", ("cinema", "netflix", "spotify")),
    ("Shopping", ("amazon", "flipkart", "shopping")),
)


def categorize_merchant(name: str) -> str:
    merchant = name.strip().casefold()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in merchant for keyword in keywords):
            return category
    return "Other"


def spending_summary(transactions, *, now: datetime) -> dict:
    current_month = now.strftime("%Y-%m")
    previous_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    monthly = Counter()
    by_category = Counter()
    by_method = Counter()
    count = 0

    for transaction in transactions:
        occurred_at = transaction.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        if occurred_at > now:
            continue
        month = occurred_at.strftime("%Y-%m")
        monthly[month] += transaction.amount_minor
        count += 1
        if month == current_month:
            by_category[transaction.category] += transaction.amount_minor
            by_method[transaction.method] += transaction.amount_minor

    return {
        "total_spent_minor": sum(monthly.values()),
        "this_month_minor": monthly[current_month],
        "last_month_minor": monthly[previous_month],
        "transaction_count": count,
        "by_category": [
            {"category": category, "amount_minor": amount}
            for category, amount in by_category.most_common()
        ],
        "by_method": [
            {"method": method, "amount_minor": amount}
            for method, amount in by_method.most_common()
        ],
        "monthly": [
            {"month": month, "amount_minor": monthly[month]}
            for month in sorted(monthly)
            if monthly[month] != 0
        ],
    }
