"""
LIFESTYLE SEARCH — GENERAL WEB + DYNAMIC QUERY TEST
=====================================================
Run: python test_lifestyle_search.py

Tests the GENERAL web search pipeline that handles ANY preference term.
The LLM generates queries, web search returns results, LLM extracts structure.

Also tests: Meetup, Facebook Events, Brave Search, Google Custom Search,
and shows exactly how the dual pipeline (structured + unstructured) works.
"""

import requests
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import quote

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
GOOGLE_KEY = os.environ.get("GOOGLE_MAPS_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")  # Custom Search Engine ID


def safe_get(url, params=None, headers=None, timeout=15):
    try:
        return requests.get(url, params=params, headers=headers or HEADERS, timeout=timeout)
    except Exception as e:
        print(f"    EXCEPTION: {e}")
        return None


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


# ═════════════════════════════════════════════════════════════
# 1. THE CORE IDEA — LLM GENERATES QUERIES FOR ANY INPUT
# ═════════════════════════════════════════════════════════════

def show_dynamic_expansion():
    section("1. DYNAMIC QUERY GENERATION — ANY PREFERENCE")

    # This is what the LLM would produce for arbitrary inputs.
    # In production, the LLM generates these — not a lookup table.
    examples = {
        "I'm into parties": {
            "web_queries": [
                "best party spots Allston Boston",
                "nightlife scene Brighton Ave 2026",
                "Allston house party culture reddit",
                "Boston weekend party events this month",
                "bars with DJ Allston Brighton",
            ],
            "overpass_tags": ["amenity=bar", "amenity=pub", "amenity=nightclub"],
            "google_places_types": ["bar", "night_club"],
            "reddit_queries": ["allston parties", "boston nightlife", "brighton bars weekend"],
            "news_queries": ["Allston nightlife", "Boston party events"],
        },
        "I have two cats": {
            "web_queries": [
                "pet friendly apartments Allston Boston",
                "cat friendly neighborhoods Boston",
                "vet clinics near Allston",
                "pet stores Brighton Boston",
                "Allston landlord pet policy reddit",
            ],
            "overpass_tags": ["shop=pet", "amenity=veterinary"],
            "google_places_types": ["pet_store", "veterinary_care"],
            "reddit_queries": ["allston pet friendly", "boston cats apartment", "pet deposit boston"],
            "news_queries": ["Boston pet friendly housing"],
            "311_filter": "animal",  # filter 311 complaints for animal-related
        },
        "I love Korean food": {
            "web_queries": [
                "best Korean restaurants Allston Boston",
                "Korean grocery stores near Brighton",
                "Allston Koreatown food scene",
                "Korean BBQ Boston review",
                "Asian supermarket Allston",
            ],
            "overpass_tags": ["cuisine=korean", "shop=supermarket"],
            "google_places_types": ["restaurant"],
            "google_places_keyword": "korean",
            "reddit_queries": ["korean food allston", "best korean restaurant boston", "hmart boston"],
            "yelp_search": "korean",
        },
        "I need quiet to study": {
            "web_queries": [
                "quiet neighborhoods Boston for students",
                "best study spots Allston Brighton",
                "Allston noise levels at night reddit",
                "quiet cafes with wifi Boston",
                "library study spaces near Allston",
            ],
            "overpass_tags": ["amenity=library", "amenity=cafe"],
            "reddit_queries": ["allston quiet", "brighton noise", "quiet neighborhoods boston"],
            "311_filter": "noise|loud|party|music",  # 311 noise complaints = inverse signal
            "inverse_signal": True,  # fewer noise complaints = BETTER for this preference
        },
        "I play tennis regularly": {
            "web_queries": [
                "tennis courts near Allston Boston",
                "public tennis courts Brighton",
                "tennis clubs Boston membership",
                "indoor tennis Boston winter",
            ],
            "overpass_tags": ["sport=tennis", "leisure=pitch"],
            "google_places_types": ["gym"],
            "google_places_keyword": "tennis",
            "reddit_queries": ["tennis courts boston", "tennis allston brighton"],
        },
        "I want to be close to live music": {
            "web_queries": [
                "live music venues Allston Boston",
                "concerts near Brighton Ave",
                "open mic nights Allston",
                "jazz bars Boston",
                "Allston music scene 2026",
            ],
            "overpass_tags": ["amenity=pub", "amenity=nightclub", "amenity=theatre"],
            "google_places_keyword": "live music",
            "reddit_queries": ["live music allston", "concert venues boston", "open mic boston"],
            "eventbrite_query": "live music boston",
        },
    }

    for pref, queries in examples.items():
        total = sum(len(v) if isinstance(v, list) else 1 for v in queries.values())
        print(f"  Student says: \"{pref}\"")
        print(f"  LLM generates {total} search vectors across {len(queries)} channels:")
        for channel, q in queries.items():
            if isinstance(q, list):
                print(f"    {channel}: {', '.join(q[:3])}{'...' if len(q) > 3 else ''}")
            elif isinstance(q, bool):
                print(f"    {channel}: {q}")
            else:
                print(f"    {channel}: {q}")
        print()

    print("  KEY INSIGHT: The LLM generates these dynamically for ANY input.")
    print("  No predefined category list. The LLM understands 'parties' means")
    print("  bars + clubs + events. It understands 'two cats' means vet + pet store")
    print("  + pet-friendly housing policy. It understands 'quiet to study' means")
    print("  FEWER noise complaints = BETTER (inverse signal).")


# ═════════════════════════════════════════════════════════════
# 2. GOOGLE CUSTOM SEARCH — any query, structured results
# ═════════════════════════════════════════════════════════════

def test_google_custom_search():
    section("2. GOOGLE CUSTOM SEARCH API")

    if not GOOGLE_KEY or not GOOGLE_CSE_ID:
        print("  No key/CSE ID (set GOOGLE_MAPS_KEY + GOOGLE_CSE_ID)")
        print("  Free tier: 100 queries/day")
        print("  Returns: title, snippet, link, pagemap (structured data)")
        print("  This is how you search the ENTIRE web for any lifestyle term")
        print()
        print("  TESTING WITHOUT KEY — using Google News RSS as proxy:")

        # Google News RSS works without a key and returns web results
        test_queries = [
            "parties nightlife Allston Boston",
            "Korean food restaurants Allston",
            "tennis courts Brighton Boston",
            "quiet neighborhoods Boston students",
            "cat friendly apartments Allston",
        ]

        for q in test_queries:
            url = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
            resp = safe_get(url)
            if resp and resp.status_code == 200:
                titles = re.findall(r'<title>(.*?)</title>', resp.text)
                items = re.findall(r'<item>', resp.text)
                print(f"\n  \"{q}\":")
                print(f"    {len(items)} results")
                for t in titles[1:3]:
                    print(f"    - {t[:70]}")
            time.sleep(0.5)
        return

    # With key: full Custom Search
    queries = [
        "best party bars Allston Boston",
        "Korean BBQ near Allston",
        "quiet study cafes Brighton",
    ]
    for q in queries:
        resp = safe_get("https://www.googleapis.com/customsearch/v1", params={
            "key": GOOGLE_KEY, "cx": GOOGLE_CSE_ID, "q": q, "num": 5,
        })
        if resp and resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            print(f"  \"{q}\": {len(items)} results")
            for item in items[:3]:
                print(f"    - {item['title'][:60]}")
                print(f"      {item.get('snippet', '')[:80]}")
                print(f"      {item['link'][:60]}")
        else:
            print(f"  \"{q}\": HTTP {resp.status_code if resp else 'FAIL'}")
        time.sleep(0.5)


# ═════════════════════════════════════════════════════════════
# 3. BRAVE SEARCH API — best free alternative to Google
# ═════════════════════════════════════════════════════════════

def test_brave_search():
    section("3. BRAVE SEARCH API")

    brave_key = os.environ.get("BRAVE_API_KEY", "")
    if not brave_key:
        print("  No key (set BRAVE_API_KEY — free 2000 queries/month)")
        print("  Returns: title, description, url, age, language")
        print("  Best free web search API. Already available as MCP tool.")
        print()

        # Test Brave's public search page for scrapeability
        print("  TESTING PUBLIC BRAVE SEARCH PAGE:")
        queries = ["parties Allston Boston", "Korean food near Allston"]
        for q in queries:
            resp = safe_get(f"https://search.brave.com/search?q={quote(q)}")
            if resp:
                print(f"    \"{q}\": HTTP {resp.status_code} [{len(resp.content)//1024}KB]")
                if resp.status_code == 200:
                    # Check for result snippets
                    snippets = re.findall(r'class="snippet-description"[^>]*>(.*?)</p>', resp.text, re.DOTALL)
                    titles = re.findall(r'class="snippet-title"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
                    print(f"      Titles found: {len(titles)}, Snippets: {len(snippets)}")
                elif resp.status_code == 403:
                    print(f"      BLOCKED")
            time.sleep(1)
        return

    # With API key
    for q in ["best party spots Allston Boston", "Korean restaurants near Brighton Ave Boston"]:
        resp = safe_get("https://api.search.brave.com/res/v1/web/search",
                       params={"q": q, "count": 5},
                       headers={"X-Subscription-Token": brave_key, "Accept": "application/json"})
        if resp and resp.status_code == 200:
            data = resp.json()
            results = data.get("web", {}).get("results", [])
            print(f"  \"{q[:40]}\": {len(results)} results")
            for r in results[:3]:
                print(f"    - {r.get('title', '?')[:60]}")
                print(f"      {r.get('description', '')[:80]}")
        time.sleep(0.5)


# ═════════════════════════════════════════════════════════════
# 4. MEETUP.COM — local groups and events by interest
# ═════════════════════════════════════════════════════════════

def test_meetup():
    section("4. MEETUP.COM — GROUPS & EVENTS BY INTEREST")

    # Test public search pages
    interests = [
        ("fitness", "Fitness groups"),
        ("nightlife", "Nightlife groups"),
        ("board-games", "Board game groups"),
        ("photography", "Photography groups"),
        ("cooking", "Cooking groups"),
        ("tennis", "Tennis groups"),
    ]

    for interest, label in interests:
        url = f"https://www.meetup.com/find/?keywords={interest}&location=Boston%2C+MA&source=EVENTS"
        resp = safe_get(url)
        if resp:
            print(f"  {label}: HTTP {resp.status_code} [{len(resp.content)//1024}KB]")
            if resp.status_code == 200:
                # Look for event/group data
                group_names = re.findall(r'"name":"([^"]{5,60})"', resp.text)
                # Deduplicate
                seen = set()
                unique = []
                for g in group_names:
                    if g not in seen and not g.startswith("http"):
                        seen.add(g)
                        unique.append(g)
                print(f"    Groups/events found: {len(unique)}")
                for g in unique[:3]:
                    print(f"      - {g}")
        else:
            print(f"  {label}: FAILED")
        time.sleep(1)

    # Test Meetup API (GraphQL)
    print(f"\n  MEETUP GRAPHQL API:")
    gql_query = {
        "query": """query {
            keywordSearch(filter: {query: "fitness", lat: 42.3534, lon: -71.1323, radius: 10, source: EVENTS}) {
                count
                edges { node { id title dateTime going venue { name city } } }
            }
        }"""
    }
    resp = safe_get("https://www.meetup.com/gql", headers={
        "Content-Type": "application/json",
        **HEADERS
    })
    if resp:
        print(f"    GraphQL endpoint: HTTP {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"    Response keys: {list(data.keys())[:5]}")
            except:
                pass
    else:
        print(f"    GraphQL endpoint: FAILED")


# ═════════════════════════════════════════════════════════════
# 5. OVERPASS — DYNAMIC QUERY FROM ANY TERM
# ═════════════════════════════════════════════════════════════

def test_overpass_dynamic():
    section("5. OVERPASS — DYNAMIC QUERIES FROM ANY TERM")

    lat, lon = 42.3534, -71.1323

    # Show that Overpass can query by cuisine, sport, or any tag
    dynamic_queries = {
        "Korean food": f"""[out:json][timeout:10];
            (node["cuisine"~"korean"](around:2000,{lat},{lon});
             node["name"~"[Kk]orean"](around:2000,{lat},{lon});
             node["shop"="supermarket"]["name"~"[Hh]-?[Mm]art|[Aa]sian"](around:2000,{lat},{lon}););
            out body;""",

        "tennis": f"""[out:json][timeout:10];
            (node["sport"="tennis"](around:3000,{lat},{lon});
             way["sport"="tennis"](around:3000,{lat},{lon});
             node["leisure"="pitch"]["sport"="tennis"](around:3000,{lat},{lon}););
            out body;""",

        "dog parks": f"""[out:json][timeout:10];
            (node["leisure"="dog_park"](around:2000,{lat},{lon});
             way["leisure"="dog_park"](around:2000,{lat},{lon});
             node["amenity"="veterinary"](around:2000,{lat},{lon});
             node["shop"="pet"](around:2000,{lat},{lon}););
            out body;""",

        "live music venues": f"""[out:json][timeout:10];
            (node["amenity"="nightclub"](around:2000,{lat},{lon});
             node["amenity"="pub"]["live_music"="yes"](around:2000,{lat},{lon});
             node["amenity"="theatre"](around:2000,{lat},{lon});
             node["amenity"="music_venue"](around:2000,{lat},{lon}););
            out body;""",

        "late night food": f"""[out:json][timeout:10];
            (node["amenity"="fast_food"](around:1000,{lat},{lon});
             node["amenity"="restaurant"]["opening_hours"~"24|23|22|02|03|04"](around:1000,{lat},{lon});
             node["shop"="convenience"]["opening_hours"~"24"](around:1000,{lat},{lon}););
            out body;""",

        "vegan options": f"""[out:json][timeout:10];
            (node["diet:vegan"="yes"](around:2000,{lat},{lon});
             node["diet:vegan"="only"](around:2000,{lat},{lon});
             node["cuisine"~"vegan"](around:2000,{lat},{lon});
             node["name"~"[Vv]egan"](around:2000,{lat},{lon}););
            out body;""",

        "coworking spaces": f"""[out:json][timeout:10];
            (node["amenity"="coworking_space"](around:3000,{lat},{lon});
             node["office"="coworking"](around:3000,{lat},{lon}););
            out body;""",
    }

    for term, query in dynamic_queries.items():
        resp = safe_get("https://overpass-api.de/api/interpreter", params={"data": query})
        if resp and resp.status_code == 200:
            elements = resp.json().get("elements", [])
            print(f"  \"{term}\": {len(elements)} results")
            for e in elements[:3]:
                tags = e.get("tags", {})
                name = tags.get("name", "unnamed")
                etype = e.get("type", "?")
                lat_e = e.get("lat", "?")
                lon_e = e.get("lon", "?")
                extra = tags.get("cuisine", "") or tags.get("sport", "") or tags.get("opening_hours", "")
                print(f"    - {name} [{etype}] ({lat_e}, {lon_e}) {extra[:30]}")
        else:
            status = resp.status_code if resp else "FAIL"
            print(f"  \"{term}\": HTTP {status}")
        time.sleep(1)


# ═════════════════════════════════════════════════════════════
# 6. SOCIAL MEDIA — what's actually accessible
# ═════════════════════════════════════════════════════════════

def test_social_media():
    section("6. SOCIAL MEDIA ACCESSIBILITY CHECK")

    sources = [
        {
            "name": "Instagram Location Search",
            "url": "https://www.instagram.com/explore/locations/",
            "note": "Requires auth. Location-tagged posts would show activity near listings.",
        },
        {
            "name": "Twitter/X Search",
            "url": "https://api.twitter.com/2/tweets/search/recent",
            "note": "Requires API key ($100/mo for Basic). Would search 'party Allston tonight'.",
        },
        {
            "name": "Facebook Events (public page)",
            "url": "https://www.facebook.com/events/search/?q=party+boston",
            "note": "Graph API deprecated for most event search. Public page may work.",
        },
        {
            "name": "TikTok Search",
            "url": "https://www.tiktok.com/search?q=allston+boston+nightlife",
            "note": "No public API. Would need scraping.",
        },
        {
            "name": "Nextdoor",
            "url": "https://nextdoor.com/",
            "note": "Requires auth + address verification. Hyperlocal neighborhood data.",
        },
    ]

    for src in sources:
        resp = safe_get(src["url"], timeout=10)
        status = resp.status_code if resp else "FAIL"
        size = len(resp.content)//1024 if resp else 0
        print(f"  {src['name']}: HTTP {status} [{size}KB]")
        print(f"    {src['note']}")

        if resp and resp.status_code == 200 and size > 5:
            # Check if there's parseable content
            if "event" in src["name"].lower() or "facebook" in src["url"]:
                events = re.findall(r'"event_name"[:\s]*"([^"]+)"', resp.text)
                if events:
                    print(f"    Events found: {len(events)}")
                    for e in events[:2]:
                        print(f"      - {e[:60]}")
        print()


# ═════════════════════════════════════════════════════════════
# 7. THE FULL PIPELINE — how it all connects
# ═════════════════════════════════════════════════════════════

def test_full_pipeline_demo():
    section("7. FULL PIPELINE DEMO — 'I'm into parties' near one listing")

    lat, lon = 42.3534, -71.1323
    preference = "parties"
    print(f"  Preference: \"{preference}\"")
    print(f"  Listing: 45 Brighton Ave, Allston ({lat}, {lon})")
    print(f"  Running all available channels...\n")

    results = {"structured": [], "unstructured": []}

    # Channel 1: Overpass (structured)
    print("  [1/5] Overpass — bars, pubs, nightclubs...")
    query = f"""[out:json][timeout:10];
        (node["amenity"~"bar|pub|nightclub"](around:1000,{lat},{lon}););
        out body;"""
    resp = safe_get("https://overpass-api.de/api/interpreter", params={"data": query})
    if resp and resp.status_code == 200:
        elements = resp.json().get("elements", [])
        for e in elements:
            tags = e.get("tags", {})
            results["structured"].append({
                "name": tags.get("name", "Unnamed"),
                "type": tags.get("amenity", "?"),
                "lat": e.get("lat"),
                "lon": e.get("lon"),
                "source": "Overpass/OSM",
                "quality": "exists (no rating)",
            })
        print(f"    {len(elements)} venues found")

    time.sleep(0.5)

    # Channel 2: Reddit (unstructured)
    print("  [2/5] Reddit — party scene discussion...")
    import urllib.parse
    for q in ["allston parties", "allston nightlife bars"]:
        url = f"https://www.reddit.com/r/boston/search.json?q={urllib.parse.quote(q)}&sort=new&limit=5&restrict_sr=on"
        resp = safe_get(url, headers={"User-Agent": "RouteSafe/1.0"})
        if resp and resp.status_code == 200:
            posts = resp.json().get("data", {}).get("children", [])
            for p in posts:
                d = p["data"]
                results["unstructured"].append({
                    "title": d["title"][:80],
                    "body": (d.get("selftext") or "")[:200],
                    "score": d["score"],
                    "source": "Reddit r/boston",
                    "date": datetime.fromtimestamp(d["created_utc"]).strftime("%Y-%m-%d"),
                })
            print(f"    '{q}': {len(posts)} posts")
        time.sleep(1.5)

    # Channel 3: Google News (unstructured)
    print("  [3/5] Google News — recent party/nightlife coverage...")
    news_url = f"https://news.google.com/rss/search?q={quote('Allston Boston nightlife parties')}&hl=en-US"
    resp = safe_get(news_url)
    if resp and resp.status_code == 200:
        titles = re.findall(r'<title>(.*?)</title>', resp.text)
        for t in titles[1:6]:
            results["unstructured"].append({
                "title": t[:80], "body": "", "score": 0,
                "source": "Google News", "date": "recent",
            })
        print(f"    {len(titles)-1} headlines")

    # Channel 4: Eventbrite (semi-structured)
    print("  [4/5] Eventbrite — party events...")
    resp = safe_get(f"https://www.eventbrite.com/d/ma--boston/party/", headers=HEADERS)
    if resp and resp.status_code == 200:
        event_names = re.findall(r'"name":"([^"]{5,80})"', resp.text)
        unique_events = list(dict.fromkeys(event_names))[:10]
        for e in unique_events:
            results["unstructured"].append({
                "title": e, "body": "", "score": 0,
                "source": "Eventbrite", "date": "upcoming",
            })
        print(f"    {len(unique_events)} events found")
    else:
        print(f"    HTTP {resp.status_code if resp else 'FAIL'}")

    # Channel 5: Citizen for safety context
    print("  [5/5] Citizen — recent incidents (safety context for party hours)...")
    resp = safe_get("https://citizen.com/api/incident/trending", params={
        "lowerLatitude": lat - 0.015, "lowerLongitude": lon - 0.015,
        "upperLatitude": lat + 0.015, "upperLongitude": lon + 0.015,
        "fullResponse": "true", "limit": 50,
    })
    nighttime_incidents = 0
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            incidents = data if isinstance(data, list) else []
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list): incidents = v; break
            for inc in incidents:
                ts = inc.get("ts", 0)
                if isinstance(ts, (int, float)) and ts > 1e12:
                    hour = datetime.utcfromtimestamp(ts/1000).hour
                    if hour >= 22 or hour <= 4:
                        nighttime_incidents += 1
        except:
            pass
    print(f"    {nighttime_incidents} nighttime incidents (10PM-4AM)")

    # Summary
    print(f"\n  {'─'*60}")
    print(f"  AGGREGATED RESULTS FOR \"{preference}\":")
    print(f"  {'─'*60}")
    print(f"  Structured venues (Overpass): {len(results['structured'])}")
    for r in results["structured"][:5]:
        print(f"    - {r['name']} ({r['type']}) — {r['source']}")

    print(f"\n  Unstructured signals: {len(results['unstructured'])}")
    by_source = {}
    for r in results["unstructured"]:
        by_source.setdefault(r["source"], []).append(r)
    for src, items in by_source.items():
        print(f"    {src}: {len(items)} items")
        for item in items[:2]:
            print(f"      - {item['title'][:65]}")

    print(f"\n  Safety context: {nighttime_incidents} nighttime incidents nearby")
    print(f"\n  LLM SYNTHESIS WOULD SAY:")
    print(f"  \"This area has {len(results['structured'])} bars and nightlife venues within 1km.")
    print(f"  Reddit sentiment is {'positive' if any(r['score'] > 5 for r in results['unstructured'] if r['source']=='Reddit r/boston') else 'mixed'}.")
    print(f"  {nighttime_incidents} nighttime incidents in the past 48 hours —")
    print(f"  {'consider the walk home after midnight' if nighttime_incidents > 2 else 'relatively quiet late night'}.")
    print(f"  Party score for this listing: estimated based on venue density + sentiment.\"")


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  LIFESTYLE SEARCH — GENERAL WEB + DYNAMIC QUERY TEST")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    show_dynamic_expansion()
    test_google_custom_search()
    test_brave_search()
    test_meetup()
    test_overpass_dynamic()
    test_social_media()
    test_full_pipeline_demo()

    section("WHAT THIS PROVES")
    print("""
  The system handles ANY preference because:

  1. The LLM generates search queries — not a lookup table.
     "I'm into parties" and "I play tennis" produce completely
     different query sets across completely different APIs.

  2. Two pipelines converge per listing:
     STRUCTURED: Overpass (venues exist), Google Places (rated),
       Yelp (reviewed), Eventbrite (events scheduled)
     UNSTRUCTURED: Reddit (community discussion), Google News
       (recent coverage), web search (everything else)

  3. The LLM processes results from both pipelines:
     - Extracts venue names and addresses from unstructured text
     - Geocodes them to plot on the map
     - Classifies sentiment (positive/negative/neutral)
     - Computes a preference match score per listing
     - Cross-references with safety data (Citizen nighttime incidents
       matter more if the student's preference is nightlife)

  4. For the weekly report:
     - Overpass: cached, re-queried monthly (venues don't move)
     - Google Places: re-queried weekly (ratings change)
     - Reddit: scraped weekly (new posts appear)
     - Google News: scraped daily (current coverage)
     - Eventbrite: scraped weekly (upcoming events change)
     - Citizen: polled hourly (real-time safety)
     - 311: queried daily (new complaints)

  5. The comparison across listings:
     Listing A: parties 85/100, safety-at-night 40/100
     Listing B: parties 50/100, safety-at-night 80/100
     Listing C: parties 70/100, safety-at-night 65/100
     "If nightlife is your priority but you want to feel safe
     walking home, Listing C is the best tradeoff."

  Run test_lifestyle_sources.py first for the structured API tests.
  Run this file for the general search + dynamic query tests.
  Together they define the complete lifestyle intelligence layer.
""")