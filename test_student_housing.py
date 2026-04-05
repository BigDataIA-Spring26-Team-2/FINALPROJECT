#!/usr/bin/env python3
"""
Boston Student Housing Platform — Data Source Validation (v2)
==============================================================
Fixed resource IDs for crime and 311. POST method for Overpass.

Run: python test_student_housing.py
Requires: pip install httpx
"""

import asyncio, httpx, json, re, time, math, urllib.parse
from datetime import datetime

TIMEOUT = 30
BOLD, GREEN, RED, YELLOW, X = "\033[1m", "\033[92m", "\033[91m", "\033[93m", "\033[0m"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
RESULTS = []
CKAN = "https://data.boston.gov/api/3/action/datastore_search"

# Correct resource IDs (verified from data.boston.gov April 2026)
CRIME_ID = "b973d8cb-eeb2-4e7e-99da-c92938efc9c0"   # Crime 2023-present
R311_2025 = "9d7c2214-4709-478a-a2e8-fb2020a5bb94"   # 311 requests 2025
R311_NEW  = "254adca6-64ab-4c5c-9fc0-a6da622be185"    # 311 new system (Oct 2025+)
R311_2026 = "1a0b420d-99f1-4887-9851-990b2a5a6e17"    # 311 requests 2026


async def _get(c, url, headers=None):
    t0 = time.perf_counter()
    resp = await c.get(url, timeout=TIMEOUT, follow_redirects=True,
                       headers=headers or {"User-Agent": UA})
    return resp, round((time.perf_counter() - t0) * 1000)


async def _post(c, url, data=None, headers=None):
    t0 = time.perf_counter()
    resp = await c.post(url, data=data, timeout=TIMEOUT, follow_redirects=True,
                        headers=headers or {"User-Agent": UA})
    return resp, round((time.perf_counter() - t0) * 1000)


def _ok(label, msg="", ms=None):
    t = f"{ms}ms" if ms else ""
    print(f"    {GREEN}PASS{X} {label:<55} {t:>7}")
    if msg: print(f"         {msg}")
    RESULTS.append(("PASS", label))

def _fail(label, msg="", ms=None):
    t = f"{ms}ms" if ms else ""
    print(f"    {RED}FAIL{X} {label:<55} {t:>7}")
    if msg: print(f"         {msg}")
    RESULTS.append(("FAIL", label))

def _warn(label, msg="", ms=None):
    t = f"{ms}ms" if ms else ""
    print(f"    {YELLOW}WARN{X} {label:<55} {t:>7}")
    if msg: print(f"         {msg}")
    RESULTS.append(("WARN", label))


# ═══════════════════════════════════════════════════════════════════
# 1. BOSTON POLICE CRIME INCIDENTS
# ═══════════════════════════════════════════════════════════════════

async def test_crime(c):
    print(f"\n  {BOLD}1. Boston Police Crime Incidents{X}")
    print(f"  {'─'*64}")
    print(f"  Resource: {CRIME_ID}")
    print(f"  Source: data.boston.gov/dataset/crime-incident-reports\n")

    # 1a: Basic fetch
    url = f"{CKAN}?resource_id={CRIME_ID}&limit=5"
    try:
        resp, ms = await _get(c, url)
        data = resp.json()
        records = data.get("result", {}).get("records", [])
        total = data.get("result", {}).get("total", 0)
        if records:
            fields = list(records[0].keys())
            _ok("Crime endpoint",
                f"{total:,} total records | {len(fields)} fields", ms)
            print(f"         Fields: {', '.join(fields[:12])}")
            r = records[0]
            _ok("Crime sample",
                f"{r.get('OFFENSE_DESCRIPTION', '?')[:45]} | "
                f"{str(r.get('OCCURRED_ON_DATE', '?'))[:10]} | "
                f"{r.get('STREET', '?')}")
        else:
            _fail("Crime endpoint", f"0 records (resource_id may have changed)", ms)
    except Exception as e:
        _fail("Crime endpoint", str(e)[:80])

    # 1b: Coordinates check
    url = f"{CKAN}?resource_id={CRIME_ID}&limit=50"
    try:
        resp, ms = await _get(c, url)
        records = resp.json().get("result", {}).get("records", [])
        with_coords = [r for r in records
                      if r.get("Lat") and r.get("Long")
                      and str(r.get("Lat")) not in ("", "0", "None")
                      and str(r.get("Long")) not in ("", "0", "None")]
        pct = len(with_coords) / len(records) * 100 if records else 0
        if with_coords:
            sample = with_coords[0]
            _ok("Crime coordinates",
                f"{len(with_coords)}/{len(records)} ({pct:.0f}%) | "
                f"sample: ({sample.get('Lat')}, {sample.get('Long')})", ms)
        elif records:
            _warn("Crime coordinates",
                  f"0/{len(records)} have lat/lon. Check field names.", ms)
            print(f"         Available fields: {list(records[0].keys())}")
        else:
            _fail("Crime coordinates", "no records to check", ms)
    except Exception as e:
        _fail("Crime coordinates", str(e)[:80])

    # 1c: District filter
    url = f"{CKAN}?resource_id={CRIME_ID}&filters={{\"DISTRICT\":\"D14\"}}&limit=5"
    try:
        resp, ms = await _get(c, url)
        records = resp.json().get("result", {}).get("records", [])
        if records:
            _ok("Crime district D14 (Allston/Brighton)",
                f"{len(records)} records", ms)
        else:
            _warn("Crime district D14", "0 records. Try different district code.", ms)
    except Exception as e:
        _fail("Crime district filter", str(e)[:80])

    # 1d: Full text search
    url = f"{CKAN}?resource_id={CRIME_ID}&q=ASSAULT&limit=5"
    try:
        resp, ms = await _get(c, url)
        records = resp.json().get("result", {}).get("records", [])
        if records:
            _ok("Crime search: ASSAULT",
                f"{len(records)} results | "
                f"{records[0].get('OFFENSE_DESCRIPTION', '?')[:45]}", ms)
        else:
            _warn("Crime search ASSAULT", "0 results", ms)
    except Exception as e:
        _fail("Crime search", str(e)[:80])


# ═══════════════════════════════════════════════════════════════════
# 2. BOSTON 311 SERVICE REQUESTS
# ═══════════════════════════════════════════════════════════════════

async def test_311(c):
    print(f"\n  {BOLD}2. Boston 311 Service Requests{X}")
    print(f"  {'─'*64}")
    print(f"  Testing 3 resource IDs (Boston transitioned systems Oct 2025)\n")

    ids = {
        "311 — 2025 legacy": R311_2025,
        "311 — new system":  R311_NEW,
        "311 — 2026":        R311_2026,
    }

    working_id = None
    for label, rid in ids.items():
        url = f"{CKAN}?resource_id={rid}&limit=5"
        try:
            resp, ms = await _get(c, url)
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            total = data.get("result", {}).get("total", 0)
            if records and total > 0:
                fields = list(records[0].keys())
                _ok(label,
                    f"{total:,} records | {len(fields)} fields", ms)
                print(f"         Fields: {', '.join(fields[:10])}")
                if not working_id:
                    working_id = rid
            else:
                _warn(label, f"0 records", ms)
        except Exception as e:
            _fail(label, str(e)[:80])

    if not working_id:
        _fail("311 — no working resource ID found", "all three returned 0 records")
        return

    # Coordinate check on working ID
    url = f"{CKAN}?resource_id={working_id}&limit=50"
    try:
        resp, ms = await _get(c, url)
        records = resp.json().get("result", {}).get("records", [])
        # Try common field name variations
        with_coords = []
        for r in records:
            lat = r.get("latitude") or r.get("LATITUDE") or r.get("Latitude") or r.get("location_lat")
            if lat and str(lat) not in ("", "0", "None", "0.0"):
                with_coords.append(r)
        pct = len(with_coords) / len(records) * 100 if records else 0
        _ok("311 coordinates",
            f"{len(with_coords)}/{len(records)} ({pct:.0f}%) have lat/lon", ms)
    except Exception as e:
        _fail("311 coordinates", str(e)[:80])

    # Search tests on working ID
    for query, qlabel in [("rodent", "rodent/pest"), ("noise", "noise"),
                          ("heat", "heating"), ("bedbugs", "bedbugs")]:
        url = f"{CKAN}?resource_id={working_id}&q={query}&limit=5"
        try:
            resp, ms = await _get(c, url)
            records = resp.json().get("result", {}).get("records", [])
            if records:
                _ok(f"311 search: {qlabel}",
                    f"{len(records)} results", ms)
            else:
                _warn(f"311 search: {qlabel}", "0 results", ms)
        except Exception as e:
            _fail(f"311 search: {qlabel}", str(e)[:60])


# ═══════════════════════════════════════════════════════════════════
# 3. MBTA TRANSIT
# ═══════════════════════════════════════════════════════════════════

async def test_mbta(c):
    print(f"\n  {BOLD}3. MBTA Transit (V3 API){X}")
    print(f"  {'─'*64}")
    print(f"  Source: api-v3.mbta.com (free, no key required)\n")

    base = "https://api-v3.mbta.com"

    locations = {
        "Northeastern (Ruggles)": (42.3368, -71.0899),
        "BU Central":             (42.3505, -71.1054),
        "MIT (Kendall)":          (42.3629, -71.0862),
        "Allston":                (42.3534, -71.1323),
        "Quincy":                 (42.2529, -71.0023),
    }

    for name, (lat, lon) in locations.items():
        url = (f"{base}/stops?filter[latitude]={lat}"
               f"&filter[longitude]={lon}&filter[radius]=0.3&page[limit]=20")
        try:
            resp, ms = await _get(c, url)
            stops = resp.json().get("data", [])
            if stops:
                names = [s["attributes"]["name"] for s in stops[:3]]
                _ok(f"MBTA near {name}",
                    f"{len(stops)} stops | {', '.join(names)}", ms)
            else:
                _warn(f"MBTA near {name}", "0 stops", ms)
        except Exception as e:
            _fail(f"MBTA near {name}", str(e)[:60])
        await asyncio.sleep(0.3)

    # Routes
    url = f"{base}/routes?filter[type]=0,1"
    try:
        resp, ms = await _get(c, url)
        routes = resp.json().get("data", [])
        names = [r["attributes"]["long_name"] for r in routes]
        _ok("MBTA subway/light rail lines",
            f"{len(routes)}: {', '.join(names[:5])}", ms)
    except Exception as e:
        _fail("MBTA routes", str(e)[:60])


# ═══════════════════════════════════════════════════════════════════
# 4. OPENSTREETMAP OVERPASS — AMENITIES (POST method)
# ═══════════════════════════════════════════════════════════════════

async def test_overpass(c):
    print(f"\n  {BOLD}4. OpenStreetMap Overpass API — Amenities{X}")
    print(f"  {'─'*64}")
    print(f"  Method: POST, batched (all categories in one query)")
    print(f"  Source: overpass-api.de (free, no key)\n")

    overpass_url = "https://overpass-api.de/api/interpreter"

    def build_batch_query(lat, lon, radius=1000):
        return (
            f'[out:json][timeout:30];'
            f'('
            f'node["shop"="supermarket"](around:{radius},{lat},{lon});'
            f'node["shop"="convenience"](around:{radius},{lat},{lon});'
            f'node["shop"="laundry"](around:{radius},{lat},{lon});'
            f'node["amenity"="pharmacy"](around:{radius},{lat},{lon});'
            f'node["leisure"="fitness_centre"](around:{radius},{lat},{lon});'
            f'node["amenity"="cafe"](around:{radius},{lat},{lon});'
            f'node["amenity"="restaurant"](around:{radius},{lat},{lon});'
            f'node["amenity"="library"](around:{radius},{lat},{lon});'
            f');out body;'
        )

    locations = {
        "Allston":  (42.3534, -71.1323),
        "Quincy":   (42.2529, -71.0023),
        "Cambridge": (42.3736, -71.1209),
    }

    for loc_name, (lat, lon) in locations.items():
        query = build_batch_query(lat, lon)
        try:
            resp, ms = await _post(c, overpass_url,
                                   data={"data": query},
                                   headers={"User-Agent": UA})
            if resp.status_code == 429:
                _warn(f"Overpass: {loc_name} (all amenities)",
                      "rate limited (429)", ms)
                await asyncio.sleep(10)
                continue
            if resp.status_code != 200:
                _fail(f"Overpass: {loc_name}",
                      f"status={resp.status_code}", ms)
                await asyncio.sleep(5)
                continue

            data = resp.json()
            elements = data.get("elements", [])

            # Group by category
            counts = {}
            samples = {}
            for e in elements:
                tags = e.get("tags", {})
                cat = (tags.get("shop") or tags.get("amenity")
                       or tags.get("leisure") or "other")
                counts[cat] = counts.get(cat, 0) + 1
                if cat not in samples:
                    samples[cat] = tags.get("name", "unnamed")

            if elements:
                _ok(f"Overpass: {loc_name} (1 batched query)",
                    f"{len(elements)} total amenities", ms)
                for cat in ["supermarket", "convenience", "laundry",
                           "pharmacy", "fitness_centre", "cafe",
                           "restaurant", "library"]:
                    ct = counts.get(cat, 0)
                    sample = samples.get(cat, "")
                    status = GREEN + "PASS" + X if ct > 0 else YELLOW + "NONE" + X
                    sample_str = f" | e.g. {sample}" if sample else ""
                    print(f"         {status} {cat:<18} {ct:>3} found{sample_str}")
            else:
                _warn(f"Overpass: {loc_name}", "0 amenities found", ms)
        except Exception as e:
            _fail(f"Overpass: {loc_name}", str(e)[:80])

        await asyncio.sleep(5)  # Generous delay between location queries


# ═══════════════════════════════════════════════════════════════════
# 5. CRAIGSLIST RENTAL LISTINGS
# ═══════════════════════════════════════════════════════════════════

async def test_craigslist(c):
    print(f"\n  {BOLD}5. Craigslist Rental Listings{X}")
    print(f"  {'─'*64}")
    print(f"  Source: boston.craigslist.org (HTML scrape)\n")

    searches = [
        ("All under $2500", "max_price=2500"),
        ("1BR under $2000", "max_price=2000&min_bedrooms=1&max_bedrooms=1"),
        ("2BR under $2500", "max_price=2500&min_bedrooms=2&max_bedrooms=2"),
        ("3BR under $3000", "max_price=3000&min_bedrooms=3&max_bedrooms=3"),
    ]

    for label, params in searches:
        url = f"https://boston.craigslist.org/search/apa?{params}"
        try:
            resp, ms = await _get(c, url)
            if resp.status_code != 200:
                _warn(f"CL: {label}", f"status={resp.status_code}", ms)
                continue
            html = resp.text
            prices = sorted(int(p.replace(",", "")) for p in re.findall(r'\$(\d[\d,]{2,})', html)
                           if 400 <= int(p.replace(",", "")) <= 10000)
            if prices:
                n = len(prices)
                _ok(f"CL: {label}",
                    f"{n} listings | median=${prices[n//2]:,} | "
                    f"range=${prices[0]:,}-${prices[-1]:,}", ms)
            else:
                _warn(f"CL: {label}", "0 prices parsed", ms)
        except Exception as e:
            _fail(f"CL: {label}", str(e)[:60])
        await asyncio.sleep(1.5)


# ═══════════════════════════════════════════════════════════════════
# 6. REDDIT r/boston
# ═══════════════════════════════════════════════════════════════════

async def test_reddit(c):
    print(f"\n  {BOLD}6. Reddit r/boston{X}")
    print(f"  {'─'*64}")
    print(f"  Source: reddit.com JSON API\n")

    hoods = ["allston apartment", "cambridge rent", "quincy housing",
             "somerville apartment", "jamaica plain rent"]

    for query in hoods:
        url = (f"https://www.reddit.com/r/boston/search.json"
               f"?q={urllib.parse.quote(query)}&sort=new&limit=10&restrict_sr=on")
        try:
            resp, ms = await _get(c, url,
                                  headers={"User-Agent": "StudentHousing/1.0"})
            if resp.status_code == 200:
                posts = resp.json().get("data", {}).get("children", [])
                if posts:
                    titles = [p["data"]["title"][:55] for p in posts[:2]]
                    _ok(f"Reddit: '{query}'",
                        f"{len(posts)} posts", ms)
                    for t in titles:
                        print(f"         \"{t}\"")
                else:
                    _warn(f"Reddit: '{query}'", "0 posts", ms)
            elif resp.status_code == 429:
                _warn(f"Reddit: '{query}'", "rate limited", ms)
            else:
                _warn(f"Reddit: '{query}'", f"status={resp.status_code}", ms)
        except Exception as e:
            _fail(f"Reddit: '{query}'", str(e)[:60])
        await asyncio.sleep(2)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    w = 74
    print(f"\n{BOLD}{'='*w}{X}")
    print(f"{BOLD}  Boston Student Housing — Data Source Validation (v2){X}")
    print(f"  Fixed resource IDs + POST for Overpass")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*w}")

    async with httpx.AsyncClient() as c:
        await test_crime(c)
        await test_311(c)
        await test_mbta(c)
        await test_overpass(c)
        await test_craigslist(c)
        await test_reddit(c)

    passed = sum(1 for s, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for s, _ in RESULTS if s == "WARN")
    total = len(RESULTS)

    print(f"\n{'='*w}")
    print(f"  {BOLD}SUMMARY{X}")
    print(f"  {'─'*64}")

    groups = {
        "Crime Incidents": [r for r in RESULTS if "Crime" in r[1]],
        "311 Complaints":  [r for r in RESULTS if "311" in r[1]],
        "MBTA Transit":    [r for r in RESULTS if "MBTA" in r[1]],
        "Overpass/OSM":    [r for r in RESULTS if "Overpass" in r[1]],
        "Craigslist":      [r for r in RESULTS if "CL:" in r[1]],
        "Reddit":          [r for r in RESULTS if "Reddit" in r[1]],
    }

    for src, items in groups.items():
        if not items: continue
        p = sum(1 for s, _ in items if s == "PASS")
        t = len(items)
        color = GREEN if p == t else YELLOW if p >= t * 0.5 else RED
        print(f"    {color}{'ALL PASS' if p==t else f'{p}/{t}':>8}{X}  {src} ({t} checks)")

    if failed:
        print(f"\n  Failures:")
        for s, label in RESULTS:
            if s == "FAIL":
                print(f"    {RED}FAIL{X} {label}")

    pct = passed / total * 100 if total > 0 else 0
    color = GREEN if pct >= 80 else YELLOW if pct >= 60 else RED
    print(f"\n  {'='*64}")
    print(f"  {color}{BOLD}STUDENT HOUSING: {passed}/{total} ({pct:.0f}%){X}")
    print(f"  {'='*64}\n")

    with open("student_housing_results.json", "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(),
                   "results": RESULTS,
                   "pass": passed, "fail": failed, "warn": warned}, f, indent=2)
    print(f"  Saved: student_housing_results.json\n")


if __name__ == "__main__":
    asyncio.run(main())