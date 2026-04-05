#!/usr/bin/env python3
"""
test_listing_homeharvest.py
───────────────────────────
Standalone validation of HomeHarvest as the primary listing source
for the Vicinity platform. Fetches Boston-area rental listings from
Realtor.com via HomeHarvest, validates the returned schema, and
stores results to CSV.

Run:
    pip install homeharvest pandas
    python test_listing_homeharvest.py

Output:
    data/listings/boston_rentals.csv
    data/listings/boston_area_rentals.csv   (multi-city)
    Prints field coverage, sample records, and summary stats.
"""

import os
import sys
import time
import subprocess
from datetime import datetime


# ── Dependency check ──────────────────────────────────────────────

def ensure_installed(package: str, pip_name: str = None):
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name or package]
        )


ensure_installed("homeharvest")
ensure_installed("pandas")

from homeharvest import scrape_property
import pandas as pd


# ── Config ────────────────────────────────────────────────────────

OUTPUT_DIR = os.path.join("data", "listings")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOCATIONS = [
    "Boston, MA",
    "Cambridge, MA",
    "Somerville, MA",
    "Brookline, MA",
]

# Fields the Vicinity pipeline actually uses downstream
REQUIRED_FIELDS = [
    "property_url", "list_price", "beds", "full_baths", "sqft",
    "street", "city", "state", "zip_code",
    "latitude", "longitude", "days_on_mls", "list_date",
]

DELAY_BETWEEN_CALLS = 4.0  # seconds — stay under Realtor.com rate limit


# ── Test 1: Single-city fetch ─────────────────────────────────────

def test_single_city():
    print("=" * 70)
    print("TEST 1: Single-city fetch — Boston, MA (for_rent, past 7 days)")
    print("=" * 70)

    start = time.time()
    df = scrape_property(
        location="Boston, MA",
        listing_type="for_rent",
        past_days=7,
    )
    elapsed = time.time() - start

    n = len(df)
    print(f"\n  Listings returned: {n}")
    print(f"  Columns returned:  {len(df.columns)}")
    print(f"  Fetch time:        {elapsed:.1f}s")

    if n == 0:
        print("  ❌ FAIL — zero listings. Possible rate limit or API issue.")
        return None

    # Field coverage
    print(f"\n  Field coverage (non-null / {n}):")
    for col in REQUIRED_FIELDS:
        if col in df.columns:
            non_null = df[col].notna().sum()
            pct = non_null / n * 100
            icon = "✅" if pct > 50 else "⚠️"
            print(f"    {icon} {col:25s} {non_null:>5}/{n}  ({pct:.0f}%)")
        else:
            print(f"    ❌ {col:25s} MISSING FROM RESPONSE")

    # All columns for reference
    print(f"\n  Full column list ({len(df.columns)}):")
    for i, col in enumerate(df.columns):
        print(f"    {i+1:>2}. {col}")

    # Sample record
    print(f"\n  Sample listing (first row, non-null fields):")
    row = df.iloc[0].dropna()
    for k, v in list(row.items())[:20]:
        print(f"    {k}: {str(v)[:80]}")

    # Price stats
    if "list_price" in df.columns:
        prices = df["list_price"].dropna()
        if len(prices) > 0:
            print(f"\n  Price stats (Boston for_rent):")
            print(f"    Min:    ${prices.min():,.0f}")
            print(f"    Median: ${prices.median():,.0f}")
            print(f"    Max:    ${prices.max():,.0f}")
            print(f"    Mean:   ${prices.mean():,.0f}")

    # Save
    out_path = os.path.join(OUTPUT_DIR, "boston_rentals.csv")
    df.to_csv(out_path, index=False)
    print(f"\n  ✅ Saved: {out_path} ({n} rows, {len(df.columns)} cols)")

    return df


# ── Test 2: Multi-city fetch with dedup ───────────────────────────

def test_multi_city():
    print("\n" + "=" * 70)
    print("TEST 2: Multi-city fetch — Boston/Cambridge/Somerville/Brookline")
    print("=" * 70)

    all_dfs = []
    for i, loc in enumerate(LOCATIONS):
        print(f"\n  [{i+1}/{len(LOCATIONS)}] {loc}")
        start = time.time()
        try:
            df = scrape_property(
                location=loc,
                listing_type="for_rent",
                past_days=30,
            )
            elapsed = time.time() - start
            n = len(df) if df is not None else 0
            print(f"    → {n} listings ({elapsed:.1f}s)")
            if n > 0:
                all_dfs.append(df)
        except Exception as e:
            print(f"    → ❌ {e}")

        if i < len(LOCATIONS) - 1:
            print(f"    Waiting {DELAY_BETWEEN_CALLS}s...")
            time.sleep(DELAY_BETWEEN_CALLS)

    if not all_dfs:
        print("\n  ❌ FAIL — no data from any location.")
        return None

    combined = pd.concat(all_dfs, ignore_index=True)
    before = len(combined)

    # Dedup by street + city + zip
    dedup_cols = [c for c in ["street", "city", "zip_code"] if c in combined.columns]
    if dedup_cols:
        combined = combined.drop_duplicates(subset=dedup_cols)

    print(f"\n  Total:       {before} raw listings")
    print(f"  After dedup: {len(combined)} unique listings")

    # City breakdown
    if "city" in combined.columns:
        print(f"\n  By city:")
        for city, count in combined["city"].value_counts().items():
            print(f"    {city}: {count}")

    # Bed breakdown
    if "beds" in combined.columns:
        print(f"\n  By bedrooms:")
        for beds, count in combined["beds"].value_counts().sort_index().items():
            print(f"    {beds} bed: {count}")

    # Save
    out_path = os.path.join(OUTPUT_DIR, "boston_area_rentals.csv")
    combined.to_csv(out_path, index=False)
    print(f"\n  ✅ Saved: {out_path} ({len(combined)} rows)")

    return combined


# ── Test 3: Verify geocoordinate coverage ─────────────────────────

def test_geocoverage(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TEST 3: Geocoordinate coverage check")
    print("=" * 70)

    if df is None:
        print("  SKIP — no data")
        return

    has_lat = df["latitude"].notna().sum() if "latitude" in df.columns else 0
    has_lon = df["longitude"].notna().sum() if "longitude" in df.columns else 0
    total = len(df)

    pct = has_lat / total * 100 if total > 0 else 0
    print(f"\n  Listings with coordinates: {has_lat}/{total} ({pct:.1f}%)")

    if has_lat > 0 and "latitude" in df.columns:
        lats = df["latitude"].dropna()
        lons = df["longitude"].dropna()
        print(f"  Latitude range:  {lats.min():.4f} — {lats.max():.4f}")
        print(f"  Longitude range: {lons.min():.4f} — {lons.max():.4f}")

        # Boston bounding box sanity check
        in_boston = (
            (lats > 42.2) & (lats < 42.5) &
            (lons > -71.2) & (lons < -70.9)
        )
        in_bbox = in_boston.sum()
        print(f"  Within Boston bbox: {in_bbox}/{has_lat} ({in_bbox/has_lat*100:.1f}%)")

    icon = "✅" if pct > 90 else "⚠️"
    print(f"\n  {icon} Geocoverage {'PASS' if pct > 90 else 'LOW — check for missing coords'}")


# ── Test 4: Schema compatibility with Snowflake listings table ────

def test_schema_compatibility(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TEST 4: Schema compatibility — HomeHarvest → Snowflake listings")
    print("=" * 70)

    if df is None:
        print("  SKIP — no data")
        return

    # Mapping: Snowflake column → HomeHarvest column
    mapping = {
        "listing_id":    "property_id",
        "property_url":  "property_url",
        "source":        None,  # hardcoded "realtor.com"
        "list_price":    "list_price",
        "beds":          "beds",
        "full_baths":    "full_baths",
        "sqft":          "sqft",
        "street":        "street",
        "city":          "city",
        "zip_code":      "zip_code",
        "lat":           "latitude",
        "lon":           "longitude",
        "mls_id":        "mls_id",
        "days_on_mls":   "days_on_mls",
        "agent_name":    "agent_name",
        "primary_photo": "primary_photo",
        "description":   "text",
    }

    print(f"\n  {'Snowflake Column':25s} {'HH Column':25s} {'Status'}")
    print(f"  {'─'*25} {'─'*25} {'─'*10}")

    all_ok = True
    for sf_col, hh_col in mapping.items():
        if hh_col is None:
            print(f"  {sf_col:25s} {'(hardcoded)':25s} ✅")
        elif hh_col in df.columns:
            non_null = df[hh_col].notna().sum()
            print(f"  {sf_col:25s} {hh_col:25s} ✅ ({non_null} non-null)")
        else:
            print(f"  {sf_col:25s} {hh_col:25s} ❌ MISSING")
            all_ok = False

    icon = "✅" if all_ok else "⚠️"
    print(f"\n  {icon} Schema compatibility {'PASS' if all_ok else 'PARTIAL — missing fields above'}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  VICINITY — HomeHarvest Listing Source Validation           ║")
    print(f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):>56s}  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Test 1
    boston_df = test_single_city()

    # Test 2
    area_df = test_multi_city()

    # Test 3
    test_geocoverage(area_df)

    # Test 4
    test_schema_compatibility(boston_df)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    t1 = "✅ PASS" if boston_df is not None and len(boston_df) > 0 else "❌ FAIL"
    t2 = "✅ PASS" if area_df is not None and len(area_df) > 0 else "❌ FAIL"
    print(f"  Test 1 (single city):      {t1}")
    print(f"  Test 2 (multi city):       {t2}")
    print(f"  Test 3 (geocoverage):      {'✅ PASS' if area_df is not None and 'latitude' in area_df.columns and area_df['latitude'].notna().mean() > 0.9 else '⚠️  CHECK'}")
    print(f"  Test 4 (schema compat):    {'✅ PASS' if boston_df is not None else 'SKIP'}")
    print(f"\n  Output files:")
    for f in os.listdir(OUTPUT_DIR):
        path = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(path)
        print(f"    {path} ({size:,} bytes)")
    print()


if __name__ == "__main__":
    main()