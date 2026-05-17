"""Prospect scraper — pulls leads from Google Maps via Apify.

Exposes a programmatic `scrape_prospects(query, max_results)` for use by the
Flask routes, plus a CLI for ad-hoc runs.
"""

from __future__ import annotations

import sys

from apify_client import ApifyClient

from config import APIFY_ACTOR_ID, APIFY_API_KEY, DEFAULT_MAX_RESULTS


def _calculate_lead_score(rating) -> int:
    if rating is None or rating == "":
        return 0
    try:
        return min(int(float(rating) * 20), 100)
    except (TypeError, ValueError):
        return 0


def _extract_email(item: dict) -> str:
    emails = item.get("emails") or []
    if isinstance(emails, list) and emails:
        first = emails[0]
        if isinstance(first, dict):
            return first.get("value", "") or ""
        return str(first)
    if isinstance(emails, str):
        return emails
    return ""


def _normalize(item: dict, query: str) -> dict:
    rating = item.get("totalScore")
    if rating is None:
        rating = item.get("rating")
    return {
        "name": (item.get("title") or "").strip(),
        "address": item.get("address") or "",
        "phone": item.get("phoneUnformatted") or item.get("phone") or "",
        "website": item.get("website") or "",
        "email": _extract_email(item),
        "rating": rating if rating is not None else "",
        "review_count": item.get("reviewsCount") or 0,
        "lead_score": _calculate_lead_score(rating),
        "query": query,
    }


def scrape_prospects(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    """Run the Apify Google Maps actor and return normalized prospect dicts."""
    print(f"[apify] Starting actor {APIFY_ACTOR_ID} for: {query!r} (max={max_results})")
    client = ApifyClient(APIFY_API_KEY)

    run_input = {
        "searchStringsArray": [query],
        "maxCrawledPlacesPerSearch": max_results,
        "language": "en",
    }

    run = client.actor(APIFY_ACTOR_ID).call(run_input=run_input)
    if run is None:
        raise RuntimeError("Apify run returned None")
    print(f"[apify] Run {run['id']} finished: {run.get('status')}")

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"[apify] Fetched {len(items)} item(s)")

    return [_normalize(item, query) for item in items if (item.get("title") or "").strip()]


def _cli():
    import sheets

    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = input("Enter search query: ").strip()
    if not query:
        print("No query provided. Exiting.")
        sys.exit(1)

    prospects = scrape_prospects(query)
    added, skipped = sheets.append_prospects(prospects, owner_email="cli@local")
    print(f"[done] added={added} skipped={skipped} total_seen={len(prospects)}")


if __name__ == "__main__":
    _cli()
