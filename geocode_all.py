#!/usr/bin/env python3
"""One-shot script to geocode all listings in docs/listings.json using Nominatim.
Run this once after a rate-limit cooldown (wait ~10 min from last scraper run).
"""
import json, re, time, requests
from pathlib import Path

REPO = Path(__file__).parent
GEOCACHE_FILE = REPO / "geocode_cache.json"
LISTINGS_FILE = REPO / "docs" / "listings.json"

NEIGHBORHOOD_CENTROIDS = {
    "Ballard":       (47.6677, -122.3830),
    "Queen Anne":    (47.6374, -122.3572),
    "Fremont":       (47.6516, -122.3499),
    "Phinney Ridge": (47.6670, -122.3570),
    "Wallingford":   (47.6612, -122.3340),
    "Green Lake":    (47.6799, -122.3317),
}

def load_geocache():
    return json.loads(GEOCACHE_FILE.read_text()) if GEOCACHE_FILE.exists() else {}

def save_geocache(cache):
    GEOCACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))

def _street_only(address):
    addr = re.sub(r'\s*[-–]\s*[\w/]+\s*$', '', address)
    addr = re.sub(r',?\s*#\S+', '', addr)
    addr = re.sub(r',?\s*(unit|apt|suite|ste|apartment)\s+\S+', '', addr, flags=re.I)
    addr = re.sub(r',.*$', '', addr).strip()
    return addr.strip().strip(',').strip()

def geocode_one(address, neighborhood, cache):
    if address in cache:
        cached = tuple(cache[address])
        if cached not in NEIGHBORHOOD_CENTROIDS.values():
            print(f"  [cached] {address[:50]}")
            return cached

    street = _street_only(address)
    print(f"  [nominatim] {street}", end="", flush=True)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"street": street, "city": "Seattle", "state": "WA",
                    "country": "US", "format": "json", "limit": 1},
            headers={"User-Agent": "seattle-rentals-geocoder/1.0 (personal use)"},
            timeout=10,
        )
        time.sleep(1.2)
        if resp.status_code == 200:
            results = resp.json()
            if results:
                coords = (float(results[0]["lat"]), float(results[0]["lon"]))
                cache[address] = list(coords)
                print(f" → {coords}")
                return coords
            print(" → no result, using centroid")
        elif resp.status_code == 429:
            print(" → RATE LIMITED, stopping")
            return None
        else:
            print(f" → HTTP {resp.status_code}, using centroid")
    except Exception as e:
        print(f" → error: {e}, using centroid")
        time.sleep(1.2)

    fallback = NEIGHBORHOOD_CENTROIDS.get(neighborhood, (47.6062, -122.3321))
    cache[address] = list(fallback)
    return fallback

def main():
    cache = load_geocache()
    data = json.loads(LISTINGS_FILE.read_text())
    listings = data["listings"]

    print(f"Geocoding {len(listings)} listings...")
    for l in listings:
        result = geocode_one(l["address"], l["neighborhood"], cache)
        if result is None:
            print("Stopped due to rate limiting. Re-run after a few minutes.")
            save_geocache(cache)
            return
        l["lat"], l["lng"] = result
        save_geocache(cache)

    LISTINGS_FILE.write_text(json.dumps(data, indent=2))
    real = sum(1 for l in listings if (l["lat"], l["lng"]) not in NEIGHBORHOOD_CENTROIDS.values())
    print(f"\nDone: {real}/{len(listings)} have real coordinates (rest are neighborhood centroids).")

if __name__ == "__main__":
    main()
