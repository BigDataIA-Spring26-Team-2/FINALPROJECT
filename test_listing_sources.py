#!/usr/bin/env python3
"""
Boston Rental Listing Sources — Exhaustive Scrapeability Test
================================================================
Tests every possible source of rental listings for Boston.
For each: can we get the search page, can we get individual
listing pages, and can we extract address/coordinates.

Run: python test_listing_sources.py
Requires: pip install httpx
"""

import asyncio, httpx, re, time, json
from datetime import datetime

TIMEOUT = 30
BOLD, GREEN, RED, YELLOW, X = "\033[1m", "\033[92m", "\033[91m", "\033[93m", "\033[0m"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
RESULTS = []


async def _get(c, url, headers=None):
    t0 = time.perf_counter()
    resp = await c.get(url, timeout=TIMEOUT, follow_redirects=True,
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
# 1. CRAIGSLIST — SEARCH + INDIVIDUAL LISTINGS
# ═══════════════════════════════════════════════════════════════════

async def test_craigslist(c):
    print(f"\n  {BOLD}1. Craigslist (boston.craigslist.org){X}")
    print(f"  {'─'*64}")
    print(f"  Testing: search results + individual listing pages\n")

    # 1a: Search page (already validated)
    search_url = "https://boston.craigslist.org/search/apa?max_price=2500&min_bedrooms=1"
    listing_urls = []
    try:
        resp, ms = await _get(c, search_url)
        html = resp.text
        prices = [int(p.replace(",", "")) for p in re.findall(r'\$(\d[\d,]{2,})', html)
                 if 400 <= int(p.replace(",", "")) <= 10000]
        _ok("CL search page",
            f"{len(prices)} listings with prices | status={resp.status_code}", ms)

        # Extract individual listing URLs
        urls = re.findall(r'href="(https://boston\.craigslist\.org/[^"]+/\d+\.html)"', html)
        if not urls:
            urls = re.findall(r'href="(/[^"]+/d/[^"]+/\d+\.html)"', html)
            urls = [f"https://boston.craigslist.org{u}" for u in urls]
        if not urls:
            # Try broader pattern
            urls = re.findall(r'(https://boston\.craigslist\.org/\w+/apa/d/[^"\'>\s]+)', html)
        listing_urls = list(set(urls))
        if listing_urls:
            _ok("CL listing URLs from search",
                f"{len(listing_urls)} unique listing links found")
            print(f"         Sample: {listing_urls[0][:70]}")
        else:
            _warn("CL listing URLs",
                  "0 listing links parsed from search HTML")
            # Debug: show link patterns
            all_hrefs = re.findall(r'href="([^"]{20,80})"', html)
            apa_links = [h for h in all_hrefs if "/apa/" in h or "/d/" in h]
            if apa_links:
                print(f"         Apartment-like links found: {apa_links[0][:70]}")
            else:
                print(f"         Sample hrefs: {all_hrefs[:3]}")
    except Exception as e:
        _fail("CL search page", str(e)[:80])

    await asyncio.sleep(2)

    # 1b: Individual listing pages
    for i, lurl in enumerate(listing_urls[:3]):
        try:
            resp, ms = await _get(c, lurl)
            if resp.status_code != 200:
                _warn(f"CL listing {i+1}", f"status={resp.status_code}", ms)
                await asyncio.sleep(2)
                continue

            page = resp.text
            found = {}

            # Description
            desc_match = re.search(
                r'<section[^>]*id="postingbody"[^>]*>(.*?)</section>',
                page, re.DOTALL | re.IGNORECASE)
            if desc_match:
                desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
                desc = re.sub(r'\s+', ' ', desc)
                found["description"] = desc[:100]

            # Coordinates from JSON-LD or inline JS
            lat = re.search(r'"latitude"\s*[=:]\s*"?([\d.-]+)', page)
            lon = re.search(r'"longitude"\s*[=:]\s*"?([\d.-]+)', page)
            if lat and lon:
                found["lat"] = lat.group(1)
                found["lon"] = lon.group(1)

            # Map data-attributes
            if not lat:
                map_lat = re.search(r'data-latitude="([\d.-]+)"', page)
                map_lon = re.search(r'data-longitude="([\d.-]+)"', page)
                if map_lat and map_lon:
                    found["lat"] = map_lat.group(1)
                    found["lon"] = map_lon.group(1)

            # Price
            price_match = re.search(r'class="price"[^>]*>\$?([\d,]+)', page)
            if price_match:
                found["price"] = price_match.group(1)

            # Address / location
            addr_match = re.search(r'<div[^>]*class="mapaddress"[^>]*>(.*?)</div>', page, re.DOTALL)
            if addr_match:
                found["address"] = re.sub(r'<[^>]+>', '', addr_match.group(1)).strip()

            # Housing attributes
            attrs = re.findall(r'<span\b[^>]*>([\w\s/]+(?:BR|Ba|ft|available)[\w\s]*)</span>', page, re.I)

            if found.get("description"):
                _ok(f"CL listing {i+1} — description extracted",
                    f"${found.get('price','?')} | {len(found['description'])} chars", ms)
                print(f"         \"{found['description'][:75]}...\"")
                if found.get("lat"):
                    print(f"         Coordinates: ({found['lat']}, {found['lon']})")
                if found.get("address"):
                    print(f"         Address: {found['address']}")
            else:
                _warn(f"CL listing {i+1}",
                      f"page loaded ({len(page)//1024}KB) but no description div found", ms)
                # Check for alternative content containers
                body_match = re.search(r'class="body"[^>]*>(.*?)</section', page[:5000], re.DOTALL)
                if body_match:
                    print(f"         Found 'body' class, description may be in different structure")

        except Exception as e:
            _fail(f"CL listing {i+1}", str(e)[:80])
        await asyncio.sleep(2)


# ═══════════════════════════════════════════════════════════════════
# 2. HOTPADS (Zillow-owned, apartment search)
# ═══════════════════════════════════════════════════════════════════

async def test_hotpads(c):
    print(f"\n  {BOLD}2. HotPads (hotpads.com){X}")
    print(f"  {'─'*64}\n")

    url = "https://hotpads.com/boston-ma/apartments-for-rent"
    try:
        resp, ms = await _get(c, url)
        if resp.status_code == 200 and len(resp.text) > 5000:
            prices = re.findall(r'\$(\d[\d,]{2,})', resp.text)
            prices = [int(p.replace(",","")) for p in prices if 500 <= int(p.replace(",","")) <= 10000]
            _ok("HotPads search page",
                f"status=200 | {len(resp.text)//1024}KB | {len(prices)} prices found", ms)
        else:
            _warn("HotPads", f"status={resp.status_code} | {len(resp.text)//1024}KB", ms)
    except Exception as e:
        _fail("HotPads", str(e)[:60])


# ═══════════════════════════════════════════════════════════════════
# 3. ZUMPER
# ═══════════════════════════════════════════════════════════════════

async def test_zumper(c):
    print(f"\n  {BOLD}3. Zumper (zumper.com){X}")
    print(f"  {'─'*64}\n")

    url = "https://www.zumper.com/apartments-for-rent/boston-ma"
    try:
        resp, ms = await _get(c, url)
        if resp.status_code == 200 and len(resp.text) > 5000:
            prices = re.findall(r'\$(\d[\d,]{2,})', resp.text)
            prices = [int(p.replace(",","")) for p in prices if 500 <= int(p.replace(",","")) <= 10000]
            listings = re.findall(r'href="(/apartments-for-rent/[^"]+)"', resp.text)
            _ok("Zumper search page",
                f"status=200 | {len(resp.text)//1024}KB | "
                f"{len(prices)} prices | {len(listings)} listing links", ms)
            if listings:
                print(f"         Sample: https://www.zumper.com{listings[0][:60]}")
        else:
            _warn("Zumper", f"status={resp.status_code} | {len(resp.text)//1024}KB", ms)
    except Exception as e:
        _fail("Zumper", str(e)[:60])


# ═══════════════════════════════════════════════════════════════════
# 4. PADMAPPER
# ═══════════════════════════════════════════════════════════════════

async def test_padmapper(c):
    print(f"\n  {BOLD}4. PadMapper (padmapper.com){X}")
    print(f"  {'─'*64}\n")

    url = "https://www.padmapper.com/apartments/boston-ma"
    try:
        resp, ms = await _get(c, url)
        if resp.status_code == 200 and len(resp.text) > 5000:
            _ok("PadMapper search page",
                f"status=200 | {len(resp.text)//1024}KB", ms)
        else:
            _warn("PadMapper", f"status={resp.status_code} | {len(resp.text)//1024}KB", ms)
    except Exception as e:
        _fail("PadMapper", str(e)[:60])


# ═══════════════════════════════════════════════════════════════════
# 5. SPARE ROOM (room shares — very student relevant)
# ═══════════════════════════════════════════════════════════════════

async def test_spareroom(c):
    print(f"\n  {BOLD}5. SpareRoom (spareroom.com){X}")
    print(f"  {'─'*64}\n")

    url = "https://www.spareroom.com/roommate/?search_id=&flatshare_type=offered&search=Boston%2C+MA"
    try:
        resp, ms = await _get(c, url)
        if resp.status_code == 200 and len(resp.text) > 5000:
            prices = re.findall(r'\$(\d[\d,]{2,})', resp.text)
            prices = [int(p.replace(",","")) for p in prices if 300 <= int(p.replace(",","")) <= 5000]
            _ok("SpareRoom search (room shares)",
                f"status=200 | {len(resp.text)//1024}KB | {len(prices)} prices", ms)
        else:
            _warn("SpareRoom", f"status={resp.status_code} | {len(resp.text)//1024}KB", ms)
    except Exception as e:
        _fail("SpareRoom", str(e)[:60])


# ═══════════════════════════════════════════════════════════════════
# 6. UNIVERSITY HOUSING BOARDS
# ═══════════════════════════════════════════════════════════════════

async def test_university_boards(c):
    print(f"\n  {BOLD}6. University Off-Campus Housing Boards{X}")
    print(f"  {'─'*64}\n")

    boards = {
        "Northeastern Off-Campus": "https://offcampushousing.northeastern.edu/",
        "BU Off-Campus Housing":   "https://www.bu.edu/off-campus-housing/",
        "MIT Off-Campus Housing":  "https://studentlife.mit.edu/housing/off-campus-housing",
        "Harvard Off-Campus":      "https://www.och.harvard.edu/",
        "BC Off-Campus Housing":   "https://www.bc.edu/content/bc-web/offices/student-affairs/sites/off-campus-housing.html",
    }

    for name, url in boards.items():
        try:
            resp, ms = await _get(c, url)
            if resp.status_code == 200 and len(resp.text) > 2000:
                # Check if listings are on the page or if it's just info
                has_listings = bool(re.search(r'\$\d{3,}|bedroom|rent|lease|available', resp.text.lower()))
                has_links = bool(re.search(r'href="[^"]*listing|href="[^"]*property|href="[^"]*apartment', resp.text.lower()))
                _ok(f"{name}",
                    f"status=200 | {len(resp.text)//1024}KB | "
                    f"listings={'likely' if has_listings else 'info page'}", ms)
            elif resp.status_code == 200:
                _warn(f"{name}", f"small page ({len(resp.text)}B)", ms)
            else:
                _warn(f"{name}", f"status={resp.status_code}", ms)
        except Exception as e:
            _fail(f"{name}", str(e)[:60])
        await asyncio.sleep(1)


# ═══════════════════════════════════════════════════════════════════
# 7. BOSTON CITY DATA — ADDRESS-LEVEL RECORDS
# ═══════════════════════════════════════════════════════════════════

async def test_boston_city_data(c):
    print(f"\n  {BOLD}7. Boston City Data — Address-Level Records{X}")
    print(f"  {'─'*64}")
    print(f"  Source: data.boston.gov (CKAN)\n")

    CKAN = "https://data.boston.gov/api/3/action/datastore_search"

    datasets = {
        "Property Assessments": {
            "id": "695a8596-5458-442b-a017-7cd72471aade",
            "why": "Assessed value, year built, owner, use code per parcel",
        },
        "Building Permits": {
            "id": "6ddcd912-32a0-43df-9908-63574f8c7e77",
            "why": "Construction activity, declared value, descriptions with addresses",
        },
        "Code Enforcement Violations": {
            "id": "800a2663-1d6a-46e7-9b03-0cd4078c1d96",
            "why": "Building code violations by address (habitability issues)",
        },
        "Housing Violations": {
            "id": "1d2e5c34-a5ec-4539-84e9-f24b5e2f7a88",
            "why": "Specific housing code violations (lead paint, sanitary, structural)",
        },
    }

    for name, info in datasets.items():
        url = f"{CKAN}?resource_id={info['id']}&limit=3"
        try:
            resp, ms = await _get(c, url)
            data = resp.json()
            records = data.get("result", {}).get("records", [])
            total = data.get("result", {}).get("total", 0)
            if records and total > 0:
                fields = list(records[0].keys())
                # Check for address/location fields
                addr_fields = [f for f in fields
                             if any(k in f.lower() for k in
                                    ["addr", "street", "location", "lat", "lon",
                                     "zip", "address", "st_name"])]
                _ok(f"Boston: {name}",
                    f"{total:,} records | location fields: {', '.join(addr_fields[:4])}", ms)
                print(f"         {info['why']}")
            else:
                _warn(f"Boston: {name}",
                      f"0 records (resource_id may have changed)", ms)
        except Exception as e:
            _fail(f"Boston: {name}", str(e)[:60])
        await asyncio.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════
# 8. RENT AGGREGATORS (likely blocked, testing anyway)
# ═══════════════════════════════════════════════════════════════════

async def test_aggregators(c):
    print(f"\n  {BOLD}8. Rental Aggregators (may be blocked){X}")
    print(f"  {'─'*64}\n")

    sites = {
        "Zillow":        "https://www.zillow.com/boston-ma/rentals/",
        "Apartments.com": "https://www.apartments.com/boston-ma/",
        "Realtor.com":   "https://www.realtor.com/apartments/Boston_MA",
        "Trulia":        "https://www.trulia.com/for_rent/Boston,MA/",
        "Rent.com":      "https://www.rent.com/massachusetts/boston-apartments",
    }

    for name, url in sites.items():
        try:
            resp, ms = await _get(c, url)
            if resp.status_code == 200 and len(resp.text) > 10000:
                prices = re.findall(r'\$(\d[\d,]{2,})', resp.text)
                prices = [int(p.replace(",","")) for p in prices if 500 <= int(p.replace(",","")) <= 10000]
                listing_count = len(prices) if prices else "?"
                _ok(f"{name}",
                    f"status=200 | {len(resp.text)//1024}KB | {listing_count} prices", ms)
            elif resp.status_code == 200:
                _warn(f"{name}",
                      f"status=200 but small ({len(resp.text)//1024}KB) — likely JS-rendered", ms)
            elif resp.status_code == 403:
                _fail(f"{name}", f"403 Forbidden (bot blocked)", ms)
            elif resp.status_code == 429:
                _fail(f"{name}", f"429 Rate Limited", ms)
            else:
                _warn(f"{name}", f"status={resp.status_code}", ms)
        except Exception as e:
            _fail(f"{name}", str(e)[:60])
        await asyncio.sleep(1)


# ═══════════════════════════════════════════════════════════════════
# 9. GEOCODING — CAN WE CONVERT ADDRESSES TO LAT/LON
# ═══════════════════════════════════════════════════════════════════

async def test_geocoding(c):
    print(f"\n  {BOLD}9. Geocoding — Address to Coordinates{X}")
    print(f"  {'─'*64}")
    print(f"  Can we convert listing addresses to lat/lon?\n")

    test_addresses = [
        "45 Brighton Ave, Boston MA",
        "1234 Commonwealth Ave, Allston MA",
        "100 Cambridge St, Cambridge MA",
    ]

    # Nominatim (OpenStreetMap geocoder, 1 req/sec)
    for addr in test_addresses:
        url = (f"https://nominatim.openstreetmap.org/search"
               f"?q={addr.replace(' ', '+')}&format=json&limit=1")
        try:
            resp, ms = await _get(c, url,
                                  headers={"User-Agent": "StudentHousing/1.0 (educational)"})
            results = resp.json()
            if results:
                r = results[0]
                _ok(f"Nominatim: {addr[:35]}",
                    f"({r['lat']}, {r['lon']}) | {r.get('display_name','')[:40]}", ms)
            else:
                _warn(f"Nominatim: {addr[:35]}", "0 results", ms)
        except Exception as e:
            _fail(f"Nominatim: {addr[:35]}", str(e)[:60])
        await asyncio.sleep(1.5)  # Strict 1 req/sec


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    w = 74
    print(f"\n{BOLD}{'='*w}{X}")
    print(f"{BOLD}  Boston Rental Sources — Exhaustive Scrapeability Test{X}")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*w}")

    async with httpx.AsyncClient() as c:
        await test_craigslist(c)
        await test_hotpads(c)
        await test_zumper(c)
        await test_padmapper(c)
        await test_spareroom(c)
        await test_university_boards(c)
        await test_boston_city_data(c)
        await test_aggregators(c)
        await test_geocoding(c)

    passed = sum(1 for s, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for s, _ in RESULTS if s == "WARN")
    total = len(RESULTS)

    print(f"\n{'='*w}")
    print(f"  {BOLD}SUMMARY{X}")
    print(f"  {'─'*64}")

    groups = {
        "Craigslist":       [r for r in RESULTS if "CL " in r[1]],
        "HotPads":          [r for r in RESULTS if "HotPads" in r[1]],
        "Zumper":           [r for r in RESULTS if "Zumper" in r[1]],
        "PadMapper":        [r for r in RESULTS if "PadMapper" in r[1]],
        "SpareRoom":        [r for r in RESULTS if "SpareRoom" in r[1]],
        "University Boards": [r for r in RESULTS if any(u in r[1] for u in
                             ["Northeastern", "BU Off", "MIT Off", "Harvard Off", "BC Off"])],
        "Boston City Data":  [r for r in RESULTS if "Boston:" in r[1]],
        "Aggregators":       [r for r in RESULTS if any(a in r[1] for a in
                             ["Zillow", "Apartments", "Realtor", "Trulia", "Rent.com"])],
        "Geocoding":         [r for r in RESULTS if "Nominatim" in r[1]],
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
    print(f"  {color}{BOLD}LISTING SOURCES: {passed}/{total} ({pct:.0f}%){X}")
    print(f"  {'='*64}\n")

    with open("listing_sources_results.json", "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(),
                   "results": RESULTS,
                   "pass": passed, "fail": failed, "warn": warned}, f, indent=2)
    print(f"  Saved: listing_sources_results.json\n")


if __name__ == "__main__":
    asyncio.run(main())