#!/usr/bin/env python3
"""
Boston Student Housing — Data Inspector
=========================================
Fetches sample records from every data source and prints
the EXACT fields, values, and structure. No assumptions.

Run: python inspect_data.py
Requires: pip install httpx
"""

import asyncio, httpx, json, time
from datetime import datetime

TIMEOUT = 30
BOLD, GREEN, RED, YELLOW, CYAN, X = (
    "\033[1m", "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CKAN = "https://data.boston.gov/api/3/action/datastore_search"


async def _get(c, url, headers=None):
    resp = await c.get(url, timeout=TIMEOUT, follow_redirects=True,
                       headers=headers or {"User-Agent": UA})
    return resp


def print_record(record, indent=9):
    pad = " " * indent
    for k, v in record.items():
        val = str(v)[:70] if v is not None else "NULL"
        print(f"{pad}{CYAN}{k:<30}{X} {val}")


def print_section(title, total, fields, records, meta=""):
    print(f"\n    {GREEN}Total records: {total:,}{X}")
    if meta:
        print(f"    {meta}")
    print(f"    {BOLD}Fields ({len(fields)}):{X}")
    print(f"         {', '.join(fields)}")
    for i, r in enumerate(records[:2]):
        print(f"\n    {BOLD}Sample record {i+1}:{X}")
        print_record(r)


# ═══════════════════════════════════════════════════════════════════
# 1. CRIME INCIDENTS
# ═══════════════════════════════════════════════════════════════════

async def inspect_crime(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}1. BOSTON POLICE CRIME INCIDENTS{X}")
    print(f"  Resource: b973d8cb-eeb2-4e7e-99da-c92938efc9c0")
    print(f"  URL: data.boston.gov/dataset/crime-incident-reports-august-2015-to-date")
    print(f"{'='*74}")

    rid = "b973d8cb-eeb2-4e7e-99da-c92938efc9c0"

    # Get total count and sample
    url = f"{CKAN}?resource_id={rid}&limit=2"
    resp = await _get(c, url)
    data = resp.json()
    records = data["result"]["records"]
    total = data["result"]["total"]
    fields = [f["id"] for f in data["result"]["fields"]]

    print_section("Crime Incidents", total, fields, records)

    # Check date range
    url_latest = f"{CKAN}?resource_id={rid}&sort=OCCURRED_ON_DATE+desc&limit=1"
    url_oldest = f"{CKAN}?resource_id={rid}&sort=OCCURRED_ON_DATE+asc&limit=1"

    resp_l = await _get(c, url_latest)
    resp_o = await _get(c, url_oldest)
    latest = resp_l.json()["result"]["records"]
    oldest = resp_o.json()["result"]["records"]

    if latest and oldest:
        print(f"\n    {BOLD}Date range:{X}")
        print(f"         Oldest: {oldest[0].get('OCCURRED_ON_DATE', '?')}")
        print(f"         Latest: {latest[0].get('OCCURRED_ON_DATE', '?')}")

    # Check coordinate coverage
    url_coords = f"{CKAN}?resource_id={rid}&limit=100"
    resp_c = await _get(c, url_coords)
    recs = resp_c.json()["result"]["records"]
    with_coords = [r for r in recs if r.get("Lat") and str(r["Lat"]) not in ("", "0", "None", "0.0")]
    null_coords = [r for r in recs if not r.get("Lat") or str(r["Lat"]) in ("", "0", "None", "0.0")]

    print(f"\n    {BOLD}Coordinate coverage (sample of 100):{X}")
    print(f"         With lat/lon: {len(with_coords)}")
    print(f"         Missing lat/lon: {len(null_coords)}")
    if null_coords:
        print(f"         Null sample: offense={null_coords[0].get('OFFENSE_DESCRIPTION','?')[:40]}, "
              f"street={null_coords[0].get('STREET','?')}")

    # Check unique offense types
    url_off = f"{CKAN}?resource_id={rid}&limit=500"
    resp_off = await _get(c, url_off)
    offenses = set(r.get("OFFENSE_DESCRIPTION", "") for r in resp_off.json()["result"]["records"])
    print(f"\n    {BOLD}Unique offense types (from 500 sample):{X}")
    for off in sorted(offenses)[:15]:
        print(f"         {off}")
    if len(offenses) > 15:
        print(f"         ... and {len(offenses)-15} more")

    # Check districts
    districts = set(r.get("DISTRICT", "") for r in resp_off.json()["result"]["records"])
    print(f"\n    {BOLD}Districts found:{X}")
    print(f"         {', '.join(sorted(d for d in districts if d))}")


# ═══════════════════════════════════════════════════════════════════
# 2. 311 COMPLAINTS — ALL THREE RESOURCE IDS
# ═══════════════════════════════════════════════════════════════════

async def inspect_311(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}2. BOSTON 311 SERVICE REQUESTS{X}")
    print(f"  Note: Boston transitioned systems Oct 2025. Testing all three.")
    print(f"{'='*74}")

    ids = {
        "2025 Legacy (9d7c2214)": "9d7c2214-4709-478a-a2e8-fb2020a5bb94",
        "New System (254adca6)":  "254adca6-64ab-4c5c-9fc0-a6da622be185",
        "2026 (1a0b420d)":       "1a0b420d-99f1-4887-9851-990b2a5a6e17",
    }

    for label, rid in ids.items():
        print(f"\n    {BOLD}--- {label} ---{X}")
        url = f"{CKAN}?resource_id={rid}&limit=2"
        try:
            resp = await _get(c, url)
            data = resp.json()
            records = data["result"]["records"]
            total = data["result"]["total"]

            if total == 0:
                print(f"    {YELLOW}Empty dataset (0 records){X}")
                continue

            fields = [f["id"] for f in data["result"]["fields"]]
            print_section(f"311 {label}", total, fields, records)

            # Check for location fields specifically
            loc_fields = [f for f in fields if any(k in f.lower()
                         for k in ["lat", "lon", "location", "addr", "street", "zip",
                                   "x_", "y_", "fire_district", "ward", "neighborhood"])]
            print(f"\n    {BOLD}Location-related fields:{X}")
            print(f"         {', '.join(loc_fields)}")

            # Check coordinate coverage
            url2 = f"{CKAN}?resource_id={rid}&limit=50"
            resp2 = await _get(c, url2)
            recs = resp2.json()["result"]["records"]
            with_coords = 0
            lat_field = None
            for f in ["latitude", "LATITUDE", "Latitude", "location_lat", "y_latitude"]:
                if any(r.get(f) for r in recs):
                    lat_field = f
                    break
            if lat_field:
                with_coords = sum(1 for r in recs if r.get(lat_field)
                                 and str(r[lat_field]) not in ("", "0", "None"))
            print(f"         Lat field: {lat_field or 'NOT FOUND'}")
            print(f"         With coordinates: {with_coords}/50")

            # Check types/categories
            type_field = None
            for f in ["TYPE", "type", "Type", "reason", "REASON", "subject", "SUBJECT",
                       "closure_reason", "case_title"]:
                if f in fields:
                    type_field = f
                    break
            if type_field:
                url3 = f"{CKAN}?resource_id={rid}&limit=200"
                resp3 = await _get(c, url3)
                types = set(str(r.get(type_field, ""))[:50] for r in resp3.json()["result"]["records"])
                print(f"\n    {BOLD}Categories (field: {type_field}, from 200 sample):{X}")
                for t in sorted(types)[:12]:
                    if t:
                        print(f"         {t}")
                if len(types) > 12:
                    print(f"         ... and {len(types)-12} more")

            # Date range
            date_field = None
            for f in ["open_dt", "OPEN_DT", "Open_DT", "opened", "created_dt",
                       "case_enquiry_id", "ticket_created_dt_tm"]:
                if f in fields:
                    date_field = f
                    break
            if date_field:
                print(f"\n    {BOLD}Date field: {date_field}{X}")
                # Get latest
                url_l = f"{CKAN}?resource_id={rid}&sort={date_field}+desc&limit=1"
                resp_l = await _get(c, url_l)
                latest = resp_l.json()["result"]["records"]
                if latest:
                    print(f"         Latest record: {latest[0].get(date_field, '?')}")

        except Exception as e:
            print(f"    {RED}Error: {str(e)[:80]}{X}")


# ═══════════════════════════════════════════════════════════════════
# 3. MBTA V3 API
# ═══════════════════════════════════════════════════════════════════

async def inspect_mbta(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}3. MBTA V3 API{X}")
    print(f"  URL: api-v3.mbta.com")
    print(f"{'='*74}")

    base = "https://api-v3.mbta.com"

    # Stops near Northeastern
    url = f"{base}/stops?filter[latitude]=42.3368&filter[longitude]=-71.0899&filter[radius]=0.2&page[limit]=5"
    resp = await _get(c, url)
    data = resp.json()
    stops = data.get("data", [])

    print(f"\n    {BOLD}Stops near Northeastern (0.2 mile radius):{X}")
    for s in stops:
        a = s["attributes"]
        print(f"         {a['name']:<30} ({a['latitude']:.4f}, {a['longitude']:.4f}) "
              f"| wheelchair: {a.get('wheelchair_boarding', '?')}")

    # Routes
    url = f"{base}/routes?filter[type]=0,1"
    resp = await _get(c, url)
    routes = resp.json().get("data", [])
    print(f"\n    {BOLD}Subway/Light Rail Routes:{X}")
    for r in routes:
        a = r["attributes"]
        print(f"         {a['long_name']:<25} | type={a['type']} | color=#{a.get('color','')}")

    # Schedules sample (does the schedule endpoint work?)
    url = f"{base}/schedules?filter[route]=Green-B&filter[date]=2026-04-04&page[limit]=5"
    resp = await _get(c, url)
    scheds = resp.json().get("data", [])
    print(f"\n    {BOLD}Schedule sample (Green Line B, today):{X}")
    if scheds:
        for s in scheds[:3]:
            a = s["attributes"]
            print(f"         depart={a.get('departure_time','?')} | "
                  f"arrive={a.get('arrival_time','?')} | "
                  f"stop={s.get('relationships',{}).get('stop',{}).get('data',{}).get('id','?')}")
    else:
        print(f"         {YELLOW}No schedules returned (may need different date){X}")

    # Predictions (real-time)
    url = f"{base}/predictions?filter[stop]=place-ruMDL&page[limit]=5"
    resp = await _get(c, url)
    preds = resp.json().get("data", [])
    print(f"\n    {BOLD}Real-time predictions (Ruggles):{X}")
    if preds:
        for p in preds[:3]:
            a = p["attributes"]
            print(f"         route={p.get('relationships',{}).get('route',{}).get('data',{}).get('id','?')} | "
                  f"arrival={a.get('arrival_time','?')} | "
                  f"status={a.get('status','?')}")
    else:
        print(f"         {YELLOW}No predictions (may need correct stop ID){X}")


# ═══════════════════════════════════════════════════════════════════
# 4. OVERPASS (batched query)
# ═══════════════════════════════════════════════════════════════════

async def inspect_overpass(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}4. OPENSTREETMAP OVERPASS API{X}")
    print(f"  URL: overpass-api.de/api/interpreter")
    print(f"{'='*74}")

    lat, lon = 42.3534, -71.1323  # Allston
    query = (
        f'[out:json][timeout:30];'
        f'('
        f'node["shop"="supermarket"](around:1000,{lat},{lon});'
        f'node["shop"="convenience"](around:1000,{lat},{lon});'
        f'node["shop"="laundry"](around:1000,{lat},{lon});'
        f'node["amenity"="pharmacy"](around:1000,{lat},{lon});'
        f'node["leisure"="fitness_centre"](around:1000,{lat},{lon});'
        f'node["amenity"="cafe"](around:1000,{lat},{lon});'
        f'node["amenity"="restaurant"](around:1000,{lat},{lon});'
        f'node["amenity"="library"](around:1000,{lat},{lon});'
        f');out body;'
    )

    resp = await c.post("https://overpass-api.de/api/interpreter",
                        data={"data": query}, timeout=45,
                        headers={"User-Agent": UA})
    data = resp.json()
    elements = data.get("elements", [])

    # Group by type
    by_type = {}
    for e in elements:
        tags = e.get("tags", {})
        cat = tags.get("shop") or tags.get("amenity") or tags.get("leisure") or "other"
        by_type.setdefault(cat, []).append(e)

    print(f"\n    {BOLD}Amenities within 1km of Allston ({len(elements)} total):{X}")
    for cat, items in sorted(by_type.items()):
        print(f"\n    {CYAN}{cat} ({len(items)}):{X}")
        for item in items[:3]:
            tags = item.get("tags", {})
            name = tags.get("name", "unnamed")
            hours = tags.get("opening_hours", "hours unknown")
            addr = tags.get("addr:street", "")
            num = tags.get("addr:housenumber", "")
            address = f"{num} {addr}".strip() or "no address"
            print(f"         {name:<30} | {address:<25} | {hours[:30]}")
        if len(items) > 3:
            print(f"         ... and {len(items)-3} more")

    # Show full tag set of one element
    if elements:
        print(f"\n    {BOLD}Full tags of first element:{X}")
        print_record(elements[0].get("tags", {}))
        print(f"         lat={elements[0].get('lat')} lon={elements[0].get('lon')}")


# ═══════════════════════════════════════════════════════════════════
# 5. CRAIGSLIST INDIVIDUAL LISTING
# ═══════════════════════════════════════════════════════════════════

async def inspect_craigslist(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}5. CRAIGSLIST INDIVIDUAL LISTING{X}")
    print(f"  URL: boston.craigslist.org")
    print(f"{'='*74}")

    import re

    # Get a listing URL
    search_url = "https://boston.craigslist.org/search/apa?max_price=2500&min_bedrooms=1"
    resp = await _get(c, search_url)
    urls = re.findall(r'href="(https://boston\.craigslist\.org/[^"]+/\d+\.html)"', resp.text)
    urls = list(set(urls))

    if not urls:
        print(f"    {RED}Could not extract listing URLs{X}")
        return

    print(f"    {GREEN}Found {len(urls)} listing URLs{X}")

    await asyncio.sleep(2)

    # Fetch first listing
    resp = await _get(c, urls[0])
    page = resp.text

    # Extract everything we can
    print(f"\n    {BOLD}Listing URL:{X} {urls[0][:70]}")
    print(f"    {BOLD}Page size:{X} {len(page)//1024}KB")

    # Description
    desc_match = re.search(r'<section[^>]*id="postingbody"[^>]*>(.*?)</section>', page, re.DOTALL)
    if desc_match:
        desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
        desc = re.sub(r'\s+', ' ', desc)
        print(f"\n    {BOLD}Description ({len(desc)} chars):{X}")
        print(f"         {desc[:200]}")

    # Price
    price = re.search(r'class="price"[^>]*>\$?([\d,]+)', page)
    print(f"\n    {BOLD}Price:{X} ${price.group(1) if price else 'not found'}")

    # Coordinates
    lat = re.search(r'"latitude"\s*[=:]\s*"?([\d.-]+)', page)
    lon = re.search(r'"longitude"\s*[=:]\s*"?([\d.-]+)', page)
    if not lat:
        lat = re.search(r'data-latitude="([\d.-]+)"', page)
        lon = re.search(r'data-longitude="([\d.-]+)"', page)
    print(f"    {BOLD}Coordinates:{X} ({lat.group(1) if lat else 'NOT FOUND'}, "
          f"{lon.group(1) if lon else 'NOT FOUND'})")

    # Address
    addr = re.search(r'<div[^>]*class="mapaddress"[^>]*>(.*?)</div>', page, re.DOTALL)
    if addr:
        addr_text = re.sub(r'<[^>]+>', '', addr.group(1)).strip()
        print(f"    {BOLD}Address:{X} {addr_text}")

    # Housing attributes
    attrs = re.findall(r'<span class="shared-line-bubble[^"]*"[^>]*>(.*?)</span>', page, re.DOTALL)
    if attrs:
        clean = [re.sub(r'<[^>]+>', '', a).strip() for a in attrs]
        print(f"    {BOLD}Attributes:{X} {', '.join(clean)}")

    # Posting date
    post_date = re.search(r'<time[^>]*datetime="([^"]+)"', page)
    if post_date:
        print(f"    {BOLD}Posted:{X} {post_date.group(1)}")

    # Images
    images = re.findall(r'"(https://images\.craigslist\.org/[^"]+)"', page)
    print(f"    {BOLD}Images:{X} {len(images)} found")


# ═══════════════════════════════════════════════════════════════════
# 6. PROPERTY ASSESSMENTS
# ═══════════════════════════════════════════════════════════════════

async def inspect_assessments(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}6. BOSTON PROPERTY ASSESSMENTS{X}")
    print(f"  Resource: 695a8596-5458-442b-a017-7cd72471aade")
    print(f"{'='*74}")

    rid = "695a8596-5458-442b-a017-7cd72471aade"
    url = f"{CKAN}?resource_id={rid}&limit=2"
    resp = await _get(c, url)
    data = resp.json()
    records = data["result"]["records"]
    total = data["result"]["total"]
    fields = [f["id"] for f in data["result"]["fields"]]

    print_section("Property Assessments", total, fields, records)

    # Search by street name
    url2 = f"{CKAN}?resource_id={rid}&q=Brighton+Ave&limit=3"
    resp2 = await _get(c, url2)
    recs2 = resp2.json()["result"]["records"]
    if recs2:
        print(f"\n    {BOLD}Search 'Brighton Ave' (sample):{X}")
        for r in recs2[:2]:
            print(f"         {r.get('ST_NUM','')} {r.get('ST_NAME','')} {r.get('ST_NAME_SUF','')} | "
                  f"value=${r.get('AV_TOTAL', '?')} | "
                  f"built={r.get('YR_BUILT','?')} | "
                  f"rooms={r.get('R_TOTAL_RMS','?')} | "
                  f"zip={r.get('ZIPCODE','?')}")


# ═══════════════════════════════════════════════════════════════════
# 7. BUILDING PERMITS
# ═══════════════════════════════════════════════════════════════════

async def inspect_permits(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}7. BOSTON BUILDING PERMITS{X}")
    print(f"  Resource: 6ddcd912-32a0-43df-9908-63574f8c7e77")
    print(f"{'='*74}")

    rid = "6ddcd912-32a0-43df-9908-63574f8c7e77"
    url = f"{CKAN}?resource_id={rid}&limit=2"
    resp = await _get(c, url)
    data = resp.json()
    records = data["result"]["records"]
    total = data["result"]["total"]
    fields = [f["id"] for f in data["result"]["fields"]]

    print_section("Building Permits", total, fields, records)

    # Check coordinate coverage
    url2 = f"{CKAN}?resource_id={rid}&limit=50"
    resp2 = await _get(c, url2)
    recs = resp2.json()["result"]["records"]
    with_coords = [r for r in recs if r.get("y_latitude") and str(r["y_latitude"]) not in ("", "0", "None")]
    print(f"\n    {BOLD}Coordinate coverage:{X}")
    print(f"         With lat/lon: {len(with_coords)}/50")

    # Latest permits
    url3 = f"{CKAN}?resource_id={rid}&sort=issued_date+desc&limit=3"
    resp3 = await _get(c, url3)
    latest = resp3.json()["result"]["records"]
    if latest:
        print(f"\n    {BOLD}Latest permits:{X}")
        for r in latest:
            print(f"         {r.get('issued_date', '?')[:10]} | "
                  f"${r.get('declared_valuation', '?')} | "
                  f"{str(r.get('description', '?'))[:50]} | "
                  f"{r.get('address', '?')}")


# ═══════════════════════════════════════════════════════════════════
# 8. REDDIT
# ═══════════════════════════════════════════════════════════════════

async def inspect_reddit(c):
    print(f"\n{'='*74}")
    print(f"  {BOLD}8. REDDIT r/boston{X}")
    print(f"  URL: reddit.com/r/boston/search.json")
    print(f"{'='*74}")

    import urllib.parse
    url = ("https://www.reddit.com/r/boston/search.json"
           f"?q={urllib.parse.quote('allston apartment rent')}&sort=new&limit=3&restrict_sr=on")
    resp = await _get(c, url, headers={"User-Agent": "StudentHousing/1.0"})
    data = resp.json()
    posts = data.get("data", {}).get("children", [])

    print(f"\n    {BOLD}Search: 'allston apartment rent' ({len(posts)} results):{X}")
    for p in posts:
        d = p["data"]
        print(f"\n    {CYAN}Title:{X} {d['title'][:70]}")
        print(f"         score={d['score']} | comments={d['num_comments']} | "
              f"created={datetime.fromtimestamp(d['created_utc']).strftime('%Y-%m-%d')}")
        body = d.get("selftext", "")[:150]
        if body:
            print(f"         {body}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    print(f"\n{BOLD}{'='*74}{X}")
    print(f"{BOLD}  BOSTON STUDENT HOUSING — DATA INSPECTOR{X}")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Fetching sample data from every source")
    print(f"{BOLD}{'='*74}{X}")

    async with httpx.AsyncClient() as c:
        await inspect_crime(c)
        await asyncio.sleep(0.5)
        await inspect_311(c)
        await asyncio.sleep(0.5)
        await inspect_mbta(c)
        await asyncio.sleep(0.5)
        await inspect_overpass(c)
        await asyncio.sleep(0.5)
        await inspect_craigslist(c)
        await asyncio.sleep(0.5)
        await inspect_assessments(c)
        await asyncio.sleep(0.5)
        await inspect_permits(c)
        await asyncio.sleep(0.5)
        await inspect_reddit(c)

    print(f"\n{BOLD}{'='*74}{X}")
    print(f"  Done. Every field name and sample value printed above.")
    print(f"  Use this to confirm exact field names for SQL templates,")
    print(f"  coordinate field names for spatial queries, and date")
    print(f"  field names for temporal filters.")
    print(f"{BOLD}{'='*74}{X}\n")


if __name__ == "__main__":
    asyncio.run(main())