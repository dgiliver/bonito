"""Build point-in-time NASDAQ-100 membership from quarterly Wikipedia snapshots.

For each quarter start 2015-Q1 → 2026-Q4, take the newest revision of the
"Nasdaq-100" article at or before that date and parse its components table
(the table with a "Ticker" column). Writes data/reference/ndx_membership.json:

    {"source": ..., "snapshots": {"2016-01-01": {"revid": ..., "tickers": [...]}, ...}}

Approximation (documented in docs/STRATEGY_SEARCH_2026-10.md): a membership change
is visible from the next quarterly snapshot, not its exact effective date.

Usage: python scripts/data/build_ndx_membership.py [OUT_JSON]
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
UA = "bonito-research/1.0 (point-in-time index membership; contact via GitHub dgiliver/bonito)"
TITLES = ("Nasdaq-100", "List of NASDAQ-100 companies", "List of Nasdaq-100 companies")


CACHE = Path("data/reference/.wiki_cache")
PAUSE_S = 4.0  # be polite: Wikipedia returns 429 on bursts


def _get(url: str, tries: int = 8) -> bytes:
    """GET with an on-disk cache (re-runs never re-fetch) and 429-aware backoff."""
    import hashlib
    import urllib.error

    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if cached.exists():
        return cached.read_bytes()
    for i in range(tries):
        time.sleep(PAUSE_S)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            cached.write_bytes(body)
            return body
        except urllib.error.HTTPError as e:
            if i == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 15 * (i + 1)
            print(f"  HTTP {e.code}, waiting {wait}s", flush=True)
            time.sleep(wait)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(10 * (i + 1))
    raise RuntimeError("unreachable")


def revision_at(title: str, when: date) -> int | None:
    q = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "titles": title, "rvlimit": 1,
        "rvstart": f"{when.isoformat()}T00:00:00Z", "rvdir": "older",
        "rvprop": "ids|timestamp", "format": "json", "redirects": 1,
    })
    pages = json.loads(_get(f"{API}?{q}"))["query"]["pages"]
    page = next(iter(pages.values()))
    revs = page.get("revisions") or []
    return revs[0]["revid"] if revs else None


def tickers_in_revision(revid: int) -> list[str]:
    html = _get(f"https://en.wikipedia.org/w/index.php?oldid={revid}").decode("utf-8", "ignore")
    for table in re.findall(r'<table class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', html, re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
        if not rows:
            continue
        head = [re.sub(r"<[^>]+>|\[\d+\]", "", c).strip().lower()
                for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S)]
        col = next((i for i, h in enumerate(head) if h in ("ticker", "symbol", "ticker symbol")), None)
        if col is None:
            continue
        out = []
        for row in rows[1:]:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            if len(cells) > col:
                sym = re.sub(r"<[^>]+>|\[\d+\]|&#160;", "", cells[col]).strip().upper()
                if re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", sym):
                    out.append(sym)
        if len(out) >= 90:  # the components table, not a stray one
            return sorted(set(out))
    # Older revisions (~2015-2016) list components as "<li>Company (TICKER)</li>"
    # under a "Components" heading instead of a table.
    starts = [m.end() for m in re.finditer(r'id="Components"', html)]
    if starts:
        section = re.split(r"<h[23]", html[starts[-1] :], maxsplit=1)[0]
        out = []
        for item in re.findall(r"<li[^>]*>(.*?)</li>", section, re.S):
            text = re.sub(r"<[^>]+>", "", item).strip()
            m = re.search(r"\(([A-Z][A-Z.\-]{0,5})\)$", text)
            if m:
                out.append(m.group(1))
        if len(out) >= 90:
            return sorted(set(out))
        # ~2016-2018: the list lives in a {{columns-list}} template's wikitext, embedded
        # in a data-mw attribute as lines like "#[[Company]] (TICKER)".
        out = re.findall(r"\\n#[^\\]*?\(([A-Z][A-Z.\-]{0,5})\)", section)
        if len(out) >= 90:
            return sorted(set(out))
    return []


def main() -> None:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/reference/ndx_membership.json")
    snapshots: dict[str, dict] = {}
    quarters = [date(y, m, 1) for y in range(2015, 2027) for m in (1, 4, 7, 10)]
    for q in quarters:
        if q > date.today():
            break
        for title in TITLES:
            revid = revision_at(title, q)
            tickers = tickers_in_revision(revid) if revid else []
            if tickers:
                snapshots[q.isoformat()] = {"title": title, "revid": revid, "tickers": tickers}
                print(f"{q} {title!r} rev {revid}: {len(tickers)} tickers", flush=True)
                break
        else:
            print(f"{q}: NO components table found", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "source": "English Wikipedia revision snapshots, quarterly (see docs/STRATEGY_SEARCH_2026-10.md)",
        "snapshots": snapshots,
    }, indent=1))
    print(f"wrote {out_path} with {len(snapshots)} snapshots")


if __name__ == "__main__":
    main()
