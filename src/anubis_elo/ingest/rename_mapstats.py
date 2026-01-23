from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup


MAPSTATS_ID_RE = re.compile(
    r"/stats/matches/(?:mapstatsid|performance/mapstatsid|economy/mapstatsid)/(\d+)/",
    re.IGNORECASE,
)


def extract_mapstats_id(html: str) -> int | None:
    soup = BeautifulSoup(html, "lxml")

    for a in soup.select('a[href*="/stats/matches/"]'):
        href = a.get("href") or ""
        m = MAPSTATS_ID_RE.search(href)
        if m:
            return int(m.group(1))

    m = MAPSTATS_ID_RE.search(html)
    if m:
        return int(m.group(1))

    return None


def main() -> None:
    base = Path("data/raw/hltv/mapstats")

    if not base.exists():
        raise FileNotFoundError(base)

    for path in sorted(base.glob("*.html")):
        try:
            html = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[READ FAIL] {path.name}: {e}")
            continue

        mid = extract_mapstats_id(html)
        if not mid:
            print(f"[NO ID] {path.name}")
            continue

        new_path = path.with_name(f"{mid}.html")

        if new_path.exists():
            print(f"[DUPLICATE] {path.name} -> {new_path.name} already exists")
            continue

        path.rename(new_path)
        print(f"{path.name} -> {new_path.name}")


if __name__ == "__main__":
    main()
