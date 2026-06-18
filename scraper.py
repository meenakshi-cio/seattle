#!/usr/bin/env python3
"""
Seattle rental listing monitor.

Scrapes 8 property management companies and writes docs/listings.json,
which a GitHub Pages site displays with auto-refresh.

Backend breakdown:
  AppFolio (7 sites): Walls, Redside, Cornell, North Pacific, Madeson,
                       Ballard Realty, SJA PM
  Propertyware (1 site): Maple Leaf Management
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TARGET_BEDS = {2, 3}

TARGET_NEIGHBORHOODS = {
    "ballard",
    "queen anne",
    "fremont",
    "phinney ridge",
    "phinney",
    "wallingford",
    "green lake",
}

REPO_ROOT   = Path(__file__).parent
SEEN_FILE   = REPO_ROOT / "seen_listings.json"
LISTINGS_OUT = REPO_ROOT / "docs" / "listings.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20

APPFOLIO_SITES = [
    ("Walls Property Management",           "https://wallspropmgmt.appfolio.com"),
    ("Redside Partners",                    "https://redside.appfolio.com"),
    ("Cornell & Associates",                "https://cornellandassociates.appfolio.com"),
    ("North Pacific Property Management",   "https://northpacificpm.appfolio.com"),
    ("Madeson Management",                  "https://madeson.appfolio.com"),
    ("Ballard Realty",                      "https://ballardpm.appfolio.com"),
    ("SJA Property Management",             "https://sja.appfolio.com"),
]

# customer_id is the public widget key embedded in each site's HTML.
PROPERTYWARE_SITES = [
    (
        "Maple Leaf Management",
        "4GJkEYHYQFdaTzYpAEFtEmPOeNdhnyt",  # data-customer-id
        "12943381",                            # data-website-id
        "6078",                                # data-widget-id
    ),
]

PROPERTYWARE_BASE = "https://connect.propertyware.com"

# ---------------------------------------------------------------------------
# Persistence — seen_listings.json stores {listing_id: first_seen_iso}
# ---------------------------------------------------------------------------

def load_seen() -> dict:
    if SEEN_FILE.exists():
        data = json.loads(SEEN_FILE.read_text())
        # Migrate from old flat-list format
        if isinstance(data, list):
            now = datetime.now(timezone.utc).isoformat()
            return {lid: now for lid in data}
        return data
    return {}


def save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def extract_beds_appfolio(text: str) -> Optional[int]:
    """Parse AppFolio bed/bath string: '2 bd / 1 ba', 'Studio / 1 ba'."""
    text = text.lower().strip()
    if text.startswith("studio"):
        return 0
    m = re.match(r"(\d+)\s*bd", text)
    return int(m.group(1)) if m else None


def extract_beds_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def neighborhood_match(text: str) -> Optional[str]:
    lower = text.lower()
    for n in TARGET_NEIGHBORHOODS:
        if n in lower:
            # Canonical display name
            return {"phinney": "Phinney Ridge"}.get(n, n.title())
    return None


def get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def listing_id(listing: dict) -> str:
    return f"{listing['source']}|{listing['url']}"


# ---------------------------------------------------------------------------
# AppFolio scraper
# ---------------------------------------------------------------------------

def scrape_appfolio(source_name: str, base_url: str) -> list:
    soup = get_soup(f"{base_url}/listings/")
    if not soup:
        return []

    results = []
    for item in soup.select(".js-listing-item"):
        bb_el = item.select_one(".js-listing-blurb-bed-bath")
        if not bb_el:
            continue
        beds = extract_beds_appfolio(bb_el.get_text(strip=True))
        if beds not in TARGET_BEDS:
            continue

        addr_el  = item.select_one(".js-listing-address")
        title_el = item.select_one(".js-listing-title")
        combined = (addr_el.get_text(" ", strip=True) if addr_el else "") + " " + \
                   (title_el.get_text(" ", strip=True) if title_el else "")

        hood = neighborhood_match(combined)
        if not hood:
            continue

        link_el = item.select_one(".js-listing-title a")
        path    = link_el["href"] if link_el else "/listings/"
        url     = (base_url + path) if path.startswith("/") else path

        rent_el = item.select_one(".js-listing-blurb-rent")
        rent    = rent_el.get_text(strip=True) if rent_el else ""

        results.append({
            "source":       source_name,
            "beds":         beds,
            "neighborhood": hood,
            "address":      addr_el.get_text(strip=True) if addr_el else "",
            "rent":         rent,
            "url":          url,
        })

    return results


# ---------------------------------------------------------------------------
# Propertyware scraper
# ---------------------------------------------------------------------------

def scrape_propertyware(source_name: str, customer_id: str,
                        website_id: str, widget_id: str) -> list:
    """
    Auth flow (reverse-engineered from listing.min.js):
      POST /auth/apikey  Authorization: Apikey {customer_id}  → JWT
      GET  /api/marketing/listings  ?website_id=…&widget_id=…
    """
    h = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer":    "https://www.mapleleafmanagement.com/rentals/",
        "Origin":     "https://www.mapleleafmanagement.com",
    }

    try:
        auth = requests.post(
            f"{PROPERTYWARE_BASE}/auth/apikey",
            headers={**h, "Authorization": f"Apikey {customer_id}"},
            timeout=REQUEST_TIMEOUT,
        )
        auth.raise_for_status()
        token = auth.json().get("access-key", "")
        if not token:
            print(f"  [ERROR] Propertyware: no token returned for {source_name}")
            return []
        h["Authorization"] = token
    except Exception as e:
        print(f"  [ERROR] Propertyware auth failed for {source_name}: {e}")
        return []

    try:
        r = requests.get(
            f"{PROPERTYWARE_BASE}/api/marketing/listings",
            headers=h,
            params={"website_id": website_id, "widget_id": widget_id},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        print(f"  [ERROR] Propertyware listings failed for {source_name}: {e}")
        return []

    results = []
    for item in raw:
        beds = None
        for key in ("numBedrooms", "bedrooms", "beds", "num_bedrooms"):
            if key in item:
                beds = extract_beds_int(item[key])
                break
        if beds not in TARGET_BEDS:
            continue

        addr = ", ".join(filter(None, [
            item.get("address", ""),
            item.get("city", ""),
            item.get("state", ""),
            item.get("zip") or item.get("postalCode", ""),
        ]))
        name = item.get("name") or item.get("title") or ""
        hood = neighborhood_match(f"{addr} {name}")
        if not hood:
            continue

        lid  = item.get("id", "")
        url  = item.get("url") or item.get("listingUrl") or \
               (f"https://app.propertyware.com/pw/index.html#/listing/{lid}" if lid
                else "https://www.mapleleafmanagement.com/rentals/")

        rent_val = item.get("targetRent") or item.get("rent") or item.get("price") or ""
        rent = (f"${rent_val:,.0f}" if isinstance(rent_val, (int, float)) and rent_val
                else str(rent_val))

        results.append({
            "source":       source_name,
            "beds":         beds,
            "neighborhood": hood,
            "address":      addr,
            "rent":         rent,
            "url":          url,
        })

    return results


# ---------------------------------------------------------------------------
# Write docs/listings.json and push to GitHub
# ---------------------------------------------------------------------------

def write_listings_json(listings_with_meta: list, updated: str) -> None:
    LISTINGS_OUT.parent.mkdir(parents=True, exist_ok=True)
    LISTINGS_OUT.write_text(json.dumps(
        {"updated": updated, "listings": listings_with_meta},
        indent=2,
    ))


def git_push(new_count: int) -> None:
    """Commit docs/listings.json and push. Silently skips if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=REPO_ROOT, capture_output=True,
        )
        if result.returncode != 0:
            print("  [git] Not a git repo — skipping push.")
            return

        subprocess.run(["git", "add", "docs/listings.json"], cwd=REPO_ROOT, check=True)

        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=REPO_ROOT,
        )
        if diff.returncode == 0:
            print("  [git] No changes to listings.json — skipping commit.")
            return

        msg = f"listings: {new_count} new listing(s)" if new_count else "listings: routine refresh"
        subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True)
        print("  [git] Pushed listings.json to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"  [git] Push failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*60}")
    print(f"  Seattle Rental Monitor — {now_str}")
    print(f"{'='*60}")

    seen = load_seen()
    print(f"  Previously seen listings: {len(seen)}")

    # ── Scrape all sites ──────────────────────────────────────────────────
    all_found = []

    for source_name, base_url in APPFOLIO_SITES:
        print(f"\n  Scraping {source_name} …")
        try:
            results = scrape_appfolio(source_name, base_url)
            print(f"    → {len(results)} matching listing(s)")
            all_found.extend(results)
        except Exception as e:
            print(f"    → ERROR: {e}")
        time.sleep(1.5)

    for source_name, customer_id, website_id, widget_id in PROPERTYWARE_SITES:
        print(f"\n  Scraping {source_name} (Propertyware) …")
        try:
            results = scrape_propertyware(source_name, customer_id, website_id, widget_id)
            print(f"    → {len(results)} matching listing(s)")
            all_found.extend(results)
        except Exception as e:
            print(f"    → ERROR: {e}")
        time.sleep(1.5)

    # ── Merge with seen timestamps ────────────────────────────────────────
    new_count = 0
    listings_with_meta = []

    for listing in all_found:
        lid = listing_id(listing)
        if lid not in seen:
            seen[lid] = now_iso
            new_count += 1
        listings_with_meta.append({**listing, "first_seen": seen[lid]})

    save_seen(seen)

    # ── Write JSON + push ─────────────────────────────────────────────────
    write_listings_json(listings_with_meta, now_iso)
    git_push(new_count)

    # ── Console summary ───────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  Total matching listings : {len(all_found)}")
    print(f"  New (not seen before)   : {new_count}")

    if new_count:
        print("\n  NEW LISTINGS:")
        for l in listings_with_meta:
            if l["first_seen"] == now_iso:
                print(f"    [{l['beds']}BR | {l['neighborhood']}] {l['source']}")
                print(f"      {l['address']}  {l['rent']}")
                print(f"      {l['url']}")

    print(f"\n  Done. Next run in ~3 hours.\n")


if __name__ == "__main__":
    main()
