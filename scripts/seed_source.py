"""
Step 3: fill the source database with realistic data.

Run:  python scripts/seed_source.py            (default sizes)
      python scripts/seed_source.py --orders 50000

Concept: we use a fixed random seed, so everyone who runs this gets the SAME
data. Reproducible data is essential later, when we measure whether the AI
detects problems correctly — the "normal" baseline must not change randomly.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyodbc  # noqa: E402
from faker import Faker  # noqa: E402

from driftwatch.config import settings  # noqa: E402

SEED = 42
CATEGORIES = {
    "Electronics": (499, 79999),
    "Home & Kitchen": (149, 14999),
    "Fashion": (199, 4999),
    "Books": (99, 1499),
    "Grocery": (20, 999),
    "Sports": (299, 19999),
}
STATUS_WEIGHTS = {"DELIVERED": 70, "SHIPPED": 10, "PLACED": 8, "CANCELLED": 7, "RETURNED": 5}


def make_customers(fake: Faker, n: int) -> list[tuple]:
    rows = []
    for cid in range(1, n + 1):
        signup = fake.date_between(start_date="-4y", end_date="-30d")
        rows.append((
            cid,
            fake.name(),
            fake.email() if random.random() > 0.03 else None,        # ~3% missing emails (realistic)
            fake.msisdn()[:10] if random.random() > 0.05 else None,  # ~5% missing phones
            fake.city(),
            fake.state(),
            signup,
            1 if random.random() > 0.08 else 0,
        ))
    return rows


def make_products(fake: Faker, n: int) -> list[tuple]:
    rows = []
    cats = list(CATEGORIES)
    for pid in range(1, n + 1):
        cat = random.choice(cats)
        lo, hi = CATEGORIES[cat]
        rows.append((
            pid,
            f"{fake.word().title()} {fake.word().title()} {cat.split()[0]}",
            cat,
            round(random.uniform(lo, hi), 2),
            fake.date_time_between(start_date="-4y", end_date="-60d"),
        ))
    return rows


def make_orders(n: int, customers: list[tuple], products: list[tuple]) -> list[tuple]:
    rows = []
    statuses, weights = zip(*STATUS_WEIGHTS.items())
    now = datetime.now().replace(microsecond=0)
    for oid in range(1, n + 1):
        cust = random.choice(customers)
        prod = random.choice(products)
        order_date = now - timedelta(days=random.randint(1, 720), minutes=random.randint(0, 1439))
        status = random.choices(statuses, weights)[0]
        updated = order_date + timedelta(hours=random.randint(0, 240))
        rows.append((
            oid,
            cust[0],
            prod[0],
            random.choices([1, 2, 3, 4, 5], [60, 20, 10, 6, 4])[0],
            prod[3],
            random.choice([0, 0, 0, 5, 10, 15]),
            status,
            order_date,
            min(updated, now),
        ))
    return rows


def insert(cur, table: str, cols: str, rows: list[tuple]) -> None:
    placeholders = ",".join("?" * len(rows[0]))
    cur.fast_executemany = True  # sends rows in bulk instead of one round-trip per row
    cur.executemany(f"INSERT INTO dbo.{table} ({cols}) VALUES ({placeholders})", rows)
    print(f"   inserted {len(rows):>7,} rows into {table}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=2000)
    parser.add_argument("--products", type=int, default=200)
    parser.add_argument("--orders", type=int, default=20000)
    args = parser.parse_args()

    random.seed(SEED)
    fake = Faker("en_IN")
    Faker.seed(SEED)

    customers = make_customers(fake, args.customers)
    products = make_products(fake, args.products)
    orders = make_orders(args.orders, customers, products)

    print("Seeding DriftwatchSource ...")
    with pyodbc.connect(settings.odbc_connection_string(), autocommit=False) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.orders; DELETE FROM dbo.customers; DELETE FROM dbo.products;")
        insert(cur, "customers",
               "customer_id, full_name, email, phone, city, state, signup_date, is_active", customers)
        insert(cur, "products",
               "product_id, product_name, category, unit_price, created_at", products)
        insert(cur, "orders",
               "order_id, customer_id, product_id, quantity, unit_price, discount_pct, "
               "order_status, order_date, updated_at", orders)
        conn.commit()  # all-or-nothing: if anything above failed, nothing is saved
    print("[OK] Done. Next: python -m driftwatch.pipeline.run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())