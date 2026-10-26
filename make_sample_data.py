import sys

import numpy as np
import pandas as pd

from tenants import TENANTS_DIR

rng = np.random.default_rng(42)
PRODUCTS = {
    "Basic Plan": ("Subscription", 499), "Pro Plan": ("Subscription", 1499),
    "Team Plan": ("Subscription", 4999), "Onboarding Pack": ("Services", 9999),
    "Training Session": ("Services", 2999), "API Credits": ("Add-on", 999),
}
REGIONS = ["North", "South", "East", "West"]
CHANNELS = ["Organic", "Paid Ads", "Referral", "Partner"]


def make_orders(days=365, end="2026-10-18"):
    dates = pd.date_range(end=end, periods=days, freq="D")
    names = list(PRODUCTS)
    rows = []
    for i, d in enumerate(dates):
        n = int(rng.poisson(25 * (1 + i / days * 0.5)))
        if i >= days - 21:
            n = int(n * 0.8)
        for _ in range(n):
            product = rng.choice(names, p=[0.35, 0.25, 0.08, 0.05, 0.12, 0.15])
            region = rng.choice(REGIONS, p=[0.3, 0.25, 0.2, 0.25])
            if region == "South" and product == "Pro Plan" and i >= days - 21:
                continue
            category, price = PRODUCTS[product]
            qty = int(rng.integers(1, 4)) if category == "Add-on" else 1
            discount = rng.choice([0, 0, 0, 0.1, 0.2])
            rows.append({
                "order_date": d.date(), "customer_id": f"C{rng.integers(1, 3000):05d}",
                "product": product, "category": category, "region": region,
                "channel": rng.choice(CHANNELS, p=[0.4, 0.3, 0.2, 0.1]),
                "quantity": qty, "unit_price": price, "discount": discount,
                "revenue": round(qty * price * (1 - discount), 2),
            })
    df = pd.DataFrame(rows)
    df.insert(0, "order_id", [f"O{i:06d}" for i in range(1, len(df) + 1)])
    return df


if __name__ == "__main__":
    tenant_id = sys.argv[1]
    rng = np.random.default_rng(int(sys.argv[2]) if len(sys.argv) > 2 else 42)
    out = TENANTS_DIR / tenant_id / "data"
    out.mkdir(parents=True, exist_ok=True)
    df = make_orders()
    df.to_csv(out / "orders.csv", index=False)
    print(f"wrote {len(df)} orders to {out / 'orders.csv'}")
