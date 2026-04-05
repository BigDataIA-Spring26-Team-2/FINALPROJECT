"""
Boston RouteSafe — Proof of Concept
====================================
pip install streamlit folium streamlit-folium requests pandas
streamlit run poc_routesafe.py

Every coordinate geocoded live from address text.
Google Maps Directions API for transit routing (key required).
Falls back to Nominatim + OSRM walking if no key.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import pandas as pd
import math
import json
from datetime import datetime, timedelta
from urllib.parse import quote

st.set_page_config(page_title="RouteSafe POC", layout="wide")

# ─── Config ───────────────────────────────────────────────

CRIME_RESOURCE = "b973d8cb-eeb2-4e7e-99da-c92938efc9c0"
COMPLAINTS_RESOURCE = "9d7c2214-4709-478a-a2e8-fb2020a5bb94"
CKAN = "https://data.boston.gov/api/3/action"
CITIZEN = "https://citizen.com/api/incident/trending"
OSRM = "http://router.project-osrm.org/route/v1"
OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
GMAPS_DIRECTIONS = "https://maps.googleapis.com/maps/api/directions/json"
GMAPS_GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"

VIOLENT_KEYWORDS = ["ASSAULT", "ROBBERY", "SHOOTING", "HOMICIDE", "STAB", "FIREARM", "WEAPON", "MURDER"]


# ─── Utilities ────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def decode_polyline(enc):
    pts, idx, lat, lng = [], 0, 0, 0
    while idx < len(enc):
        for is_lng in range(2):
            shift, result = 0, 0
            while True:
                b = ord(enc[idx]) - 63; idx += 1
                result |= (b & 0x1F) << shift; shift += 5
                if b < 0x20: break
            val = (~(result >> 1)) if (result & 1) else (result >> 1)
            if is_lng == 0: lat += val
            else: lng += val
        pts.append((lat / 1e5, lng / 1e5))
    return pts


def bbox(points, buf_m=300):
    lats = [p[0] for p in points]; lons = [p[1] for p in points]
    dlat, dlon = buf_m / 111000, buf_m / 82000
    return min(lats)-dlat, max(lats)+dlat, min(lons)-dlon, max(lons)+dlon


def near_corridor(plat, plon, corridor, max_m):
    step = max(1, len(corridor) // 80)
    return any(haversine(plat, plon, c[0], c[1]) <= max_m for c in corridor[::step])


def safe_get(url, params=None, timeout=15):
    try:
        return requests.get(url, params=params, timeout=timeout,
                           headers={"User-Agent": "RouteSafe-POC/1.0"})
    except:
        return None


# ─── Geocoding ────────────────────────────────────────────

@st.cache_data(ttl=3600)
def geocode_nominatim(address):
    resp = safe_get(NOMINATIM, params={
        "q": address, "format": "json", "limit": 1,
        "countrycodes": "us", "viewbox": "-71.20,42.40,-70.95,42.25", "bounded": 1,
    })
    if resp and resp.status_code == 200:
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", address)
    return None, None, None


@st.cache_data(ttl=3600)
def geocode_google(address, api_key):
    resp = safe_get(GMAPS_GEOCODE, params={
        "address": address, "key": api_key, "components": "country:US",
    })
    if resp and resp.status_code == 200:
        data = resp.json()
        if data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"], data["results"][0].get("formatted_address", address)
    return None, None, None


def geocode(address, api_key=None):
    if api_key:
        lat, lon, resolved = geocode_google(address, api_key)
        if lat: return lat, lon, resolved, "Google Maps"
    lat, lon, resolved = geocode_nominatim(address)
    if lat: return lat, lon, resolved, "Nominatim"
    return None, None, None, None


# ─── Routing ──────────────────────────────────────────────

@st.cache_data(ttl=300)
def route_google(olat, olon, dlat, dlon, api_key, departure_hour=8):
    now = datetime.now()
    dep = now.replace(hour=departure_hour, minute=0, second=0)
    if dep < now: dep += timedelta(days=1)
    while dep.weekday() >= 5: dep += timedelta(days=1)

    resp = safe_get(GMAPS_DIRECTIONS, params={
        "origin": f"{olat},{olon}", "destination": f"{dlat},{dlon}",
        "mode": "transit", "departure_time": int(dep.timestamp()),
        "alternatives": "true", "key": api_key,
    })
    if resp and resp.status_code == 200:
        data = resp.json()
        if data.get("routes"):
            route = data["routes"][0]
            leg = route["legs"][0]
            points = decode_polyline(route["overview_polyline"]["points"])
            steps = []
            for s in leg.get("steps", []):
                step = {"mode": s["travel_mode"], "duration_sec": s["duration"]["value"],
                        "instruction": s.get("html_instructions", "")}
                if s["travel_mode"] == "TRANSIT":
                    td = s.get("transit_details", {})
                    step["line_name"] = td.get("line", {}).get("name", "")
                    step["short_name"] = td.get("line", {}).get("short_name", "")
                    step["departure_stop"] = td.get("departure_stop", {}).get("name", "")
                    step["arrival_stop"] = td.get("arrival_stop", {}).get("name", "")
                    step["num_stops"] = td.get("num_stops", 0)
                steps.append(step)
            return {
                "points": points, "duration_min": round(leg["duration"]["value"]/60, 1),
                "distance": leg["distance"]["text"],
                "summary": leg["duration"]["text"], "steps": steps,
                "source": "Google Maps Directions API (transit)",
            }
    return None


@st.cache_data(ttl=300)
def route_osrm(olat, olon, dlat, dlon):
    resp = safe_get(f"{OSRM}/foot/{olon},{olat};{dlon},{dlat}",
                    params={"overview": "full", "geometries": "polyline"})
    if resp and resp.status_code == 200:
        data = resp.json()
        if data.get("routes"):
            r = data["routes"][0]
            return {
                "points": decode_polyline(r["geometry"]),
                "duration_min": round(r["duration"]/60, 1),
                "distance": f"{round(r['distance'])}m",
                "summary": f"{round(r['duration']/60,1)} min walk",
                "steps": [{"mode": "WALKING", "duration_sec": r["duration"]}],
                "source": "OSRM (walking — no transit routing without Google Maps key)",
            }
    return None


def get_route(olat, olon, dlat, dlon, api_key=None, departure_hour=8):
    if api_key:
        r = route_google(olat, olon, dlat, dlon, api_key, departure_hour)
        if r: return r
    r = route_osrm(olat, olon, dlat, dlon)
    if r: return r
    d = haversine(olat, olon, dlat, dlon)
    return {"points": [(olat,olon),(dlat,dlon)], "duration_min": round(d*1.3/84,1),
            "distance": f"{round(d*1.3)}m", "summary": "Straight-line estimate",
            "steps": [], "source": "Haversine fallback"}


# ─── Data Fetchers ────────────────────────────────────────

@st.cache_data(ttl=300)
def get_crimes(min_lat, max_lat, min_lon, max_lon, days):
    """Fetch crimes via datastore_search with pagination. Fields: Lat, Long, OFFENSE_DESCRIPTION, etc."""
    all_records = []
    offset = 0
    pages = 0
    max_pages = 5  # 5 pages x 1000 = up to 5000 records scanned

    while pages < max_pages:
        resp = safe_get(f"{CKAN}/datastore_search", params={
            "resource_id": CRIME_RESOURCE,
            "sort": "OCCURRED_ON_DATE desc",
            "limit": 1000,
            "offset": offset,
        })
        if not resp or resp.status_code != 200:
            break
        data = resp.json()
        records = data.get("result", {}).get("records", [])
        if not records:
            break

        for r in records:
            try:
                rlat = float(r.get("Lat") or 0)
                rlon = float(r.get("Long") or 0)
                if rlat == 0 or rlon == 0:
                    continue
                if min_lat <= rlat <= max_lat and min_lon <= rlon <= max_lon:
                    # Normalize field names to lowercase for downstream code
                    all_records.append({
                        "incident_number": r.get("INCIDENT_NUMBER", ""),
                        "offense_description": r.get("OFFENSE_DESCRIPTION", ""),
                        "occurred_on_date": r.get("OCCURRED_ON_DATE", ""),
                        "hour": r.get("HOUR", ""),
                        "street": r.get("STREET", ""),
                        "district": r.get("DISTRICT", ""),
                        "shooting": r.get("SHOOTING", ""),
                        "lat": rlat,
                        "long": rlon,
                    })
            except (ValueError, TypeError):
                pass

        # Check if we've gone past our date window
        last_date = records[-1].get("OCCURRED_ON_DATE", "")
        if last_date:
            try:
                cutoff = datetime.now() - timedelta(days=days)
                rec_date = datetime.fromisoformat(last_date.replace("+00", ""))
                if rec_date < cutoff:
                    break
            except:
                pass

        offset += 1000
        pages += 1

    return all_records


@st.cache_data(ttl=300)
def get_complaints(min_lat, max_lat, min_lon, max_lon, days):
    """Fetch 311 complaints via datastore_search. Fields: latitude, longitude, type, open_dt, etc."""
    all_records = []
    offset = 0
    pages = 0
    max_pages = 3

    while pages < max_pages:
        resp = safe_get(f"{CKAN}/datastore_search", params={
            "resource_id": COMPLAINTS_RESOURCE,
            "sort": "open_dt desc",
            "limit": 1000,
            "offset": offset,
        })
        if not resp or resp.status_code != 200:
            break
        data = resp.json()
        records = data.get("result", {}).get("records", [])
        if not records:
            break

        for r in records:
            try:
                rlat = float(r.get("latitude") or 0)
                rlon = float(r.get("longitude") or 0)
                if rlat == 0 or rlon == 0:
                    continue
                if min_lat <= rlat <= max_lat and min_lon <= rlon <= max_lon:
                    r["latitude"] = rlat
                    r["longitude"] = rlon
                    all_records.append(r)
            except (ValueError, TypeError):
                pass

        last_date = records[-1].get("open_dt", "")
        if last_date:
            try:
                cutoff = datetime.now() - timedelta(days=days)
                rec_date = datetime.fromisoformat(last_date.replace("+00", "").split(".")[0])
                if rec_date < cutoff:
                    break
            except:
                pass

        offset += 1000
        pages += 1

    return all_records


@st.cache_data(ttl=120)
def get_citizen(lat, lon, radius=0.015):
    resp = safe_get(CITIZEN, params={
        "lowerLatitude":lat-radius,"lowerLongitude":lon-radius,
        "upperLatitude":lat+radius,"upperLongitude":lon+radius,
        "fullResponse":"true","limit":50})
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            if isinstance(data,list): return data
            if isinstance(data,dict):
                for v in data.values():
                    if isinstance(v,list): return v
        except: pass
    return []


@st.cache_data(ttl=600)
def get_amenities(lat, lon, radius=800):
    query = f"""[out:json][timeout:15];
    (node["amenity"~"supermarket|pharmacy|gym|fitness_centre|laundry|cafe|library"](around:{radius},{lat},{lon});
     node["shop"~"supermarket|convenience|laundry"](around:{radius},{lat},{lon}););
    out body;"""
    resp = safe_get(OVERPASS, params={"data": query})
    if resp and resp.status_code == 200:
        return [{"name":e.get("tags",{}).get("name","Unnamed"),
                 "type":e.get("tags",{}).get("amenity") or e.get("tags",{}).get("shop","?"),
                 "lat":e["lat"],"lon":e["lon"]}
                for e in resp.json().get("elements",[])]
    return []


@st.cache_data(ttl=120)
def get_citizen_detail(inc_id):
    resp = safe_get(f"https://citizen.com/api/incident/{inc_id}")
    if resp and resp.status_code == 200:
        try: return resp.json()
        except: pass
    return None


# ─── Scoring ──────────────────────────────────────────────

def score_corridor(crimes, corridor_pts, buf_m=300):
    nearby = [c for c in crimes if near_corridor(c["lat"],c["long"],corridor_pts,buf_m)]
    violent = [c for c in nearby if any(k in (c.get("offense_description") or "").upper() for k in VIOLENT_KEYWORDS)]
    t,v = len(nearby),len(violent)
    if t==0: s=95
    elif t<=3 and v==0: s=80
    elif t<=8 and v<=1: s=60
    elif t<=15 and v<=3: s=40
    else: s=max(10,50-t*2)
    return s, nearby, violent


def score_livability(complaints, lat, lon, radius=500):
    nearby = [c for c in complaints if haversine(lat,lon,c["latitude"],c["longitude"])<=radius]
    types = {}
    for c in nearby:
        t=(c.get("type") or "Other").strip(); types[t]=types.get(t,0)+1
    t=len(nearby)
    if t<=5: s=90
    elif t<=15: s=70
    elif t<=30: s=50
    else: s=max(10,60-t)
    return s, nearby, types


# ─── Sidebar ──────────────────────────────────────────────

with st.sidebar:
    st.subheader("Google Maps API Key")
    api_key = st.text_input("Key (enables transit routing + geocoding)", type="password")
    if api_key:
        st.caption("Transit routing active")
    else:
        st.caption("No key — Nominatim geocoding, OSRM walking routes")

    st.divider()
    st.subheader("Listing")
    listing_addr = st.text_input("Listing address", "45 Brighton Ave, Allston, Boston, MA")

    st.divider()
    st.subheader("Destinations")
    num_dests = st.number_input("Count", 1, 6, 3)
    defaults = [
        ("Northeastern University, Boston, MA", "School", 8),
        ("Crunch Fitness, 195 Harvard Ave, Allston, MA", "Gym", 7),
        ("500 Boylston St, Boston, MA", "Internship", 9),
        ("Davis Square, Somerville, MA", "Friend", 20),
        ("Star Market, Commonwealth Ave, Boston, MA", "Grocery", 10),
        ("Boston Public Library, Boylston St, Boston, MA", "Library", 14),
    ]
    dest_inputs = []
    for i in range(num_dests):
        da,dt,dh = defaults[i] if i<len(defaults) else ("","Other",9)
        with st.expander(f"Destination {i+1}", expanded=(i<3)):
            addr = st.text_input("Address", da, key=f"a{i}")
            c1,c2 = st.columns(2)
            tp = c1.text_input("Label", dt, key=f"t{i}")
            hr = c2.number_input("Departure hour", 0, 23, dh, key=f"h{i}")
            dest_inputs.append({"address":addr,"type":tp,"hour":hr})

    st.divider()
    days_back = st.slider("Lookback (days)", 7, 180, 90)
    run = st.button("Build Graph", type="primary", use_container_width=True)


# ─── Main ─────────────────────────────────────────────────

st.title("RouteSafe — Proof of Concept")

if "results" not in st.session_state:
    st.session_state.results = None

if run:
    # Compute and store in session_state
    status = st.status("Running...", expanded=True)

    # 1. Geocode
    status.write("Geocoding listing...")
    l_lat,l_lon,l_resolved,l_source = geocode(listing_addr, api_key or None)
    if not l_lat:
        st.error(f"Could not geocode: {listing_addr}")
        st.stop()
    status.write(f"  {l_resolved} -> ({l_lat:.5f}, {l_lon:.5f}) via {l_source}")

    geocoded = []
    for d in dest_inputs:
        if not d["address"].strip(): continue
        status.write(f"Geocoding: {d['address']}...")
        la,lo,res,src = geocode(d["address"], api_key or None)
        if la:
            geocoded.append({**d,"lat":la,"lon":lo,"resolved":res,"geo_source":src})
            status.write(f"  {res} -> ({la:.5f}, {lo:.5f}) via {src}")
        else:
            st.warning(f"Failed to geocode: {d['address']}")

    if not geocoded:
        st.error("No destinations geocoded."); st.stop()

    # 2. Routes
    status.write("Computing routes...")
    routes = {}
    for d in geocoded:
        r = get_route(l_lat,l_lon,d["lat"],d["lon"],api_key or None,d["hour"])
        routes[d["type"]] = {**r,**d}
        status.write(f"  -> {d['type']}: {r['duration_min']} min via {r['source']}")

    # 3. Crime
    all_pts = [(l_lat,l_lon)]
    for r in routes.values(): all_pts.extend(r["points"])
    mn_la,mx_la,mn_lo,mx_lo = bbox(all_pts, 300)
    status.write("Fetching Boston PD crimes...")
    crimes = get_crimes(mn_la,mx_la,mn_lo,mx_lo,days_back)
    status.write(f"  {len(crimes)} records")

    # 4. 311
    status.write("Fetching 311 complaints...")
    cb1,cb2,cb3,cb4 = bbox([(l_lat,l_lon)],500)
    complaints = get_complaints(cb1,cb2,cb3,cb4,days_back)
    status.write(f"  {len(complaints)} records")

    # 5. Citizen
    status.write("Fetching Citizen real-time...")
    citizen = get_citizen(l_lat,l_lon)
    status.write(f"  {len(citizen)} live incidents")

    # 6. Amenities
    status.write("Fetching amenities (Overpass)...")
    amenities = get_amenities(l_lat,l_lon)
    amen_types = {}
    for a in amenities: t=a["type"]; amen_types[t]=amen_types.get(t,0)+1
    status.write(f"  {len(amenities)} amenities")

    # 7. Score
    corridor_scores = {}
    for rn,rd in routes.items():
        s,near,viol = score_corridor(crimes,rd["points"])
        corridor_scores[rn] = {"safety":s,"crimes":len(near),"violent":len(viol),
                               "nearby":near,"violent_list":viol,
                               "duration":rd["duration_min"],"distance":rd["distance"],"hour":rd["hour"]}

    liv_score,liv_nearby,liv_types = score_livability(complaints,l_lat,l_lon)
    essentials = sum(1 for k in ["supermarket","convenience","gym","fitness_centre","pharmacy","laundry"] if k in amen_types)

    status.update(label="Complete.", state="complete")

    # Store everything in session_state
    st.session_state.results = {
        "l_lat": l_lat, "l_lon": l_lon, "l_resolved": l_resolved, "l_source": l_source,
        "listing_addr": listing_addr, "geocoded": geocoded, "routes": routes,
        "crimes": crimes, "complaints": complaints, "citizen": citizen,
        "amenities": amenities, "amen_types": amen_types,
        "corridor_scores": corridor_scores, "liv_score": liv_score,
        "liv_nearby": liv_nearby, "liv_types": liv_types, "essentials": essentials,
        "days_back": days_back, "has_api_key": bool(api_key),
    }

# ─── Display Results ──────────────────────────────────────

if st.session_state.results is None:
    st.write("Enter addresses in the sidebar. Add a Google Maps API key for transit routing. "
             "Click Build Graph. Everything is geocoded and fetched live.")
    st.stop()

R = st.session_state.results
l_lat,l_lon,l_resolved,l_source = R["l_lat"],R["l_lon"],R["l_resolved"],R["l_source"]
geocoded,routes = R["geocoded"],R["routes"]
crimes,complaints,citizen = R["crimes"],R["complaints"],R["citizen"]
amenities,amen_types = R["amenities"],R["amen_types"]
corridor_scores = R["corridor_scores"]
liv_score,liv_nearby,liv_types,essentials = R["liv_score"],R["liv_nearby"],R["liv_types"],R["essentials"]

st.subheader("1. Geocoded Locations")
rows = [{"Role":"Listing","Input":R["listing_addr"],"Resolved":l_resolved,"Lat":l_lat,"Lon":l_lon,"Via":l_source}]
for d in geocoded:
    rows.append({"Role":d["type"],"Input":d["address"],"Resolved":d["resolved"],"Lat":d["lat"],"Lon":d["lon"],"Via":d["geo_source"]})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.subheader("2. Routes")
for rn,rd in routes.items():
    st.write(f"**Listing -> {rn}** — {rd['duration_min']} min, {rd['distance']}")
    st.caption(f"Source: {rd['source']} | {len(rd['points'])} polyline points | Departure: {rd['hour']}:00")
    if rd.get("steps") and any(s.get("line_name") for s in rd["steps"]):
        step_rows = []
        for s in rd["steps"]:
            row = {"Mode":s["mode"],"Duration":f"{s['duration_sec']//60}m"}
            if s["mode"]=="TRANSIT":
                row["Line"]=s.get("line_name") or s.get("short_name","")
                row["From"]=s.get("departure_stop","")
                row["To"]=s.get("arrival_stop","")
                row["Stops"]=s.get("num_stops","")
            step_rows.append(row)
        st.dataframe(pd.DataFrame(step_rows), use_container_width=True, hide_index=True)

st.subheader("3. Corridor Scores")
st.dataframe(pd.DataFrame([{
    "Route":f"Listing -> {rn}","Commute":f"{sc['duration']} min","Distance":sc["distance"],
    "Crimes (300m)":sc["crimes"],"Violent":sc["violent"],
    "Safety":f"{sc['safety']}/100","Departure":f"{sc['hour']}:00"
} for rn,sc in corridor_scores.items()]), use_container_width=True, hide_index=True)

mc1,mc2,mc3 = st.columns(3)
mc1.metric("Livability",f"{liv_score}/100",f"{len(liv_nearby)} complaints / 500m")
mc2.metric("Amenities",f"{len(amenities)}",f"{essentials}/6 essentials")
mc3.metric("Citizen",f"{len(citizen)} live","~2km bbox")

st.subheader("4. Graph")

m = folium.Map(location=[l_lat,l_lon], zoom_start=13, tiles="CartoDB positron")
folium.CircleMarker([l_lat,l_lon],radius=10,color="#000",fill=True,fill_color="#000",
                    fill_opacity=0.9,popup=f"LISTING: {l_resolved}",tooltip="Listing").add_to(m)

for d in geocoded:
    folium.CircleMarker([d["lat"],d["lon"]],radius=7,color="#333",fill=True,fill_color="#555",
                        fill_opacity=0.8,popup=f"{d['type']}: {d['resolved']}",tooltip=d["type"]).add_to(m)

for rn,rd in routes.items():
    s = corridor_scores[rn]["safety"]
    color = "#22c55e" if s>=70 else "#eab308" if s>=50 else "#ef4444"
    folium.PolyLine(rd["points"],color=color,weight=4,opacity=0.8,
                    popup=f"{rn}: {s}/100, {corridor_scores[rn]['crimes']} crimes",
                    tooltip=f"{rn} — {s}/100").add_to(m)

plotted = set()
for rn,sc in corridor_scores.items():
    for c in sc["nearby"]:
        cid=c.get("incident_number",id(c))
        if cid in plotted: continue
        plotted.add(cid)
        v=any(k in (c.get("offense_description") or "").upper() for k in VIOLENT_KEYWORDS)
        folium.CircleMarker([c["lat"],c["long"]],radius=3,color="#dc2626" if v else "#f97316",
                           fill=True,fill_opacity=0.6,
                           popup=f"{c.get('offense_description','?')}\n{c.get('occurred_on_date','')[:10]}").add_to(m)

for inc in citizen:
    if isinstance(inc,dict) and inc.get("latitude") and inc.get("longitude"):
        folium.CircleMarker([float(inc["latitude"]),float(inc["longitude"])],radius=5,
                           color="#7c3aed",fill=True,fill_opacity=0.7,
                           popup=f"LIVE: {inc.get('title') or inc.get('raw','?')}").add_to(m)

for a in amenities:
    folium.CircleMarker([a["lat"],a["lon"]],radius=2,color="#059669",fill=True,fill_opacity=0.4,
                        popup=f"{a['name']} ({a['type']})").add_to(m)

st_folium(m, use_container_width=True, height=520)
st.caption("Black=listing. Grey=destinations. Route color=safety. Orange/red=crime (corridor only). Purple=Citizen. Green=amenities.")

st.subheader("5. All Reported Incidents")
st.write(f"Every data point fetched — {len(crimes)} crimes (Boston PD), {len(complaints)} 311 complaints, "
         f"{len(citizen)} Citizen live incidents. No corridor filtering. Raw overlay.")

layer_sel = st.multiselect("Layers", ["Boston PD Crimes", "311 Complaints", "Citizen (Live)"],
                           default=["Boston PD Crimes", "311 Complaints", "Citizen (Live)"])

m2 = folium.Map(location=[l_lat, l_lon], zoom_start=14, tiles="CartoDB positron")

# Listing pin for reference
folium.CircleMarker([l_lat,l_lon],radius=8,color="#000",fill=True,fill_color="#000",
                    fill_opacity=0.9,tooltip="Listing").add_to(m2)

# Route polylines for reference (thin, grey)
for rn,rd in routes.items():
    folium.PolyLine(rd["points"],color="#999",weight=2,opacity=0.4,dash_array="6").add_to(m2)

if "Boston PD Crimes" in layer_sel and crimes:
    crime_group = folium.FeatureGroup(name="Boston PD Crimes")
    for c in crimes:
        v = any(k in (c.get("offense_description") or "").upper() for k in VIOLENT_KEYWORDS)
        offense = c.get("offense_description", "Unknown")
        date = (c.get("occurred_on_date") or "")[:10]
        hour = c.get("hour", "?")
        street = c.get("street", "")
        shooting = c.get("shooting", "")
        color = "#dc2626" if v else "#f97316"
        folium.CircleMarker(
            [c["lat"], c["long"]], radius=3 if not v else 5,
            color=color, fill=True, fill_opacity=0.5 if not v else 0.8,
            popup=folium.Popup(
                f"<b>CRIME</b><br>{offense}<br>{date} at {hour}:00<br>{street}"
                f"{'<br><b>SHOOTING</b>' if shooting and shooting != '0' else ''}",
                max_width=250),
        ).add_to(crime_group)
    crime_group.add_to(m2)

if "311 Complaints" in layer_sel and complaints:
    complaint_group = folium.FeatureGroup(name="311 Complaints")
    for c in complaints:
        ctype = c.get("type", "Unknown")
        title = c.get("case_title", "")
        date = (c.get("open_dt") or "")[:10]
        street = c.get("location_street_name", "")
        hood = c.get("neighborhood", "")
        folium.CircleMarker(
            [c["latitude"], c["longitude"]], radius=3,
            color="#2563eb", fill=True, fill_opacity=0.5,
            popup=folium.Popup(
                f"<b>311</b><br>{ctype}<br>{title}<br>{date}<br>{street}, {hood}",
                max_width=250),
        ).add_to(complaint_group)
    complaint_group.add_to(m2)

if "Citizen (Live)" in layer_sel and citizen:
    citizen_group = folium.FeatureGroup(name="Citizen Live")
    for inc in citizen:
        if not isinstance(inc, dict): continue
        ilat = inc.get("latitude")
        ilon = inc.get("longitude")
        if not ilat or not ilon: continue
        title = inc.get("title") or inc.get("raw", "?")
        sev = inc.get("severity", "?")
        lvl = inc.get("level", "?")
        addr = inc.get("address", "")
        ts = inc.get("ts")
        ts_str = ""
        if isinstance(ts, (int,float)) and ts > 1e12:
            ts_str = datetime.utcfromtimestamp(ts/1000).strftime("%Y-%m-%d %H:%M")
        folium.CircleMarker(
            [float(ilat), float(ilon)], radius=6,
            color="#7c3aed", fill=True, fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>CITIZEN (LIVE)</b><br>{title}<br>Severity: {sev} / Level: {lvl}<br>{addr}<br>{ts_str}",
                max_width=300),
        ).add_to(citizen_group)
    citizen_group.add_to(m2)

folium.LayerControl().add_to(m2)
st_folium(m2, use_container_width=True, height=560)

crime_violent = sum(1 for c in crimes if any(k in (c.get("offense_description") or "").upper() for k in VIOLENT_KEYWORDS))
citizen_critical = sum(1 for inc in citizen if isinstance(inc,dict) and inc.get("level",0) in [2,"2"])
st.caption(f"Crimes: {len(crimes)} total, {crime_violent} violent. "
           f"311: {len(complaints)} complaints. "
           f"Citizen: {len(citizen)} live, {citizen_critical} critical (level 2).")

st.subheader("6. Source Data")
tabs = st.tabs(["Crimes","311 Complaints","Citizen","Amenities"])

with tabs[0]:
    st.write(f"Boston PD CKAN — {len(crimes)} records, last {R['days_back']} days, bounding box of all corridors")
    st.write("Each crime position tested against 300m buffer of route polyline. Violent offenses weighted heavier.")
    for rn,sc in corridor_scores.items():
        offenses={}
        for c in sc["nearby"]: o=c.get("offense_description","?"); offenses[o]=offenses.get(o,0)+1
        top=sorted(offenses.items(),key=lambda x:-x[1])[:5]
        st.write(f"- {rn}: {sc['crimes']} total, {sc['violent']} violent. "
                 f"Top: {', '.join(f'{o} ({n})' for o,n in top) if top else 'none'}")
    if crimes:
        df=pd.DataFrame(crimes)[["incident_number","offense_description","occurred_on_date","hour","street","district","shooting"]].head(25)
        df["occurred_on_date"]=df["occurred_on_date"].str[:10]
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[1]:
    st.write(f"Boston 311 CKAN — {len(complaints)} records within 500m, last {R['days_back']} days")
    st.write(f"Livability: {liv_score}/100. Complaint types indicate pest/noise/infrastructure issues.")
    if liv_types:
        st.dataframe(pd.DataFrame([{"Type":k,"Count":v} for k,v in sorted(liv_types.items(),key=lambda x:-x[1])]),
                     use_container_width=True, hide_index=True)
    if complaints:
        df=pd.DataFrame(complaints)[["open_dt","type","case_title","location_street_name","neighborhood"]].head(20)
        df["open_dt"]=df["open_dt"].str[:10]
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[2]:
    st.write(f"Citizen App — {len(citizen)} live incidents, tight bbox around listing")
    st.write("Fills 2-3 day gap before Boston PD data appears. Polled hourly in production.")
    for inc in citizen:
        if isinstance(inc,dict):
            title=inc.get("title") or inc.get("raw","?")
            sev,lvl=inc.get("severity","?"),inc.get("level","?")
            ts=inc.get("ts")
            ts_s=datetime.utcfromtimestamp(ts/1000).strftime("%Y-%m-%d %H:%M UTC") if isinstance(ts,(int,float)) and ts>1e12 else ""
            st.write(f"- {title} — severity: {sev}, level: {lvl}, {ts_s}")
    first_id=next((inc.get("key") for inc in citizen if isinstance(inc,dict) and inc.get("key")),None)
    if first_id:
        st.write("---")
        st.write(f"Detail: /api/incident/{first_id}")
        detail=get_citizen_detail(first_id)
        if detail:
            st.write(f"Address: {detail.get('address','?')} | Closed: {detail.get('closed','?')}")
            for uid,ud in list(detail.get("updates",{}).items())[:3]:
                if isinstance(ud,dict):
                    st.write(f"  [{ud.get('type','?')}] {ud.get('text','')[:120]}")
                    for clip in (ud.get("radioClips") or []):
                        if isinstance(clip,dict) and clip.get("transcription"):
                            st.write(f"  Scanner: {clip['transcription'].get('text','')[:200]}")
                            break

with tabs[3]:
    st.write(f"Overpass/OSM — {len(amenities)} amenities within 800m")
    st.write("Feeds convenience scoring. In discovery mode, user picks from these to build routine.")
    if amen_types:
        st.dataframe(pd.DataFrame([{"Category":k,"Count":v} for k,v in sorted(amen_types.items(),key=lambda x:-x[1])]),
                     use_container_width=True, hide_index=True)
    if amenities:
        st.dataframe(pd.DataFrame(amenities), use_container_width=True, hide_index=True)

st.subheader("7. Pipeline Summary")
st.write(f"""
**Listing:** {l_resolved} — geocoded live via {l_source}

**Routes:** {len(routes)} computed via {'Google Maps Directions (transit)' if R["has_api_key"] else 'OSRM (walking)'}

**Data fetched live:** Boston PD: {len(crimes)} crimes | 311: {len(complaints)} complaints | Citizen: {len(citizen)} live incidents | Overpass: {len(amenities)} amenities

**Scores:** {' | '.join(f'{rn}: {sc["safety"]}/100' for rn,sc in corridor_scores.items())} | Livability: {liv_score}/100 | Essentials: {essentials}/6

In the full system, this runs for 15-50 candidates in parallel. Google Maps Distance Matrix pre-filters by commute. 
The Route Monitor accumulates daily scorecards per candidate. After the watch period, the comparison report 
shows score trajectories across all candidates.
""")