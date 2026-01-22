from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

MAPSTATS_ID_RE = re.compile(
    r"/stats/matches/(?:mapstatsid|performance/mapstatsid|economy/mapstatsid)/(\d+)/",
    re.IGNORECASE,
)

STATS_PLAYER_ID_RE = re.compile(r"/stats/players/(\d+)/", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedMapStats:
    mapstats_id: int
    event_name: Optional[str]
    map_name: Optional[str]

    team1_name: Optional[str]
    team2_name: Optional[str]
    team1_rounds: Optional[int]
    team2_rounds: Optional[int]

    player_ids_10: list[int]

    source_path: str


def _text(el) -> Optional[str]:
    if not el:
        return None
    t = el.get_text(" ", strip=True)
    return t if t else None


def _extract_mapstats_id(raw_html: str, soup: BeautifulSoup) -> int:
    for a in soup.select('a[href*="/stats/matches/"]'):
        href = a.get("href") or ""
        m = MAPSTATS_ID_RE.search(href)
        if m:
            return int(m.group(1))

    m = MAPSTATS_ID_RE.search(raw_html)
    if m:
        return int(m.group(1))

    raise ValueError("Could not find mapstats_id in HTML")


def _extract_event_name(soup: BeautifulSoup) -> Optional[str]:
    return _text(soup.select_one(".stats-match-menu .menu-header"))


def _extract_team_names(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    t1 = _text(soup.select_one(".match-info-box .team-left a"))
    t2 = _text(soup.select_one(".match-info-box .team-right a"))

    if not t1:
        t1 = _text(soup.select_one(".match-info-box .team-left .team-name"))
    if not t2:
        t2 = _text(soup.select_one(".match-info-box .team-right .team-name"))

    return t1, t2


def _extract_anubis_map_block_score_and_name(
    soup: BeautifulSoup,
) -> tuple[Optional[str], Optional[int], Optional[int]]:
    
    for block in soup.select(".stats-match-map-result"):
        full = block.select_one(".dynamic-map-name-full")
        if not full:
            continue

        full_name = full.get_text(strip=True)
        if full_name.lower() != "anubis":
            continue

        score_el = block.select_one(".stats-match-map-result-score")
        if not score_el:
            return full_name, None, None

        txt = score_el.get_text(" ", strip=True)
        parts = [p.strip() for p in txt.replace("–", "-").split("-")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return full_name, int(parts[0]), int(parts[1])

        return full_name, None, None

    return None, None, None


def _extract_rounds_fallback(soup: BeautifulSoup) -> tuple[Optional[int], Optional[int]]:
    s1 = _text(soup.select_one(".match-info-box .team-left .bold"))
    s2 = _text(soup.select_one(".match-info-box .team-right .bold"))

    r1 = int(s1) if s1 and s1.isdigit() else None
    r2 = int(s2) if s2 and s2.isdigit() else None
    return r1, r2


def _extract_player_ids_from_stats_tables(soup: BeautifulSoup) -> list[int]:
    """
    On mapstats pages, player rows are in two tables:
      table.stats-table.totalstats (one per team)
    Player links are typically:
      /stats/players/<id>/<slug>

    Could be necessary for future when mapping player ids to actual player names
    """
    player_ids: list[int] = []

    for table in soup.select("table.stats-table.totalstats"):
        for a in table.select('td.st-player a[href*="/stats/players/"]'):
            href = a.get("href") or ""
            m = STATS_PLAYER_ID_RE.search(href)
            if m:
                player_ids.append(int(m.group(1)))

    seen = set()
    deduped: list[int] = []
    for pid in player_ids:
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(pid)

    return deduped


def parse_mapstats_html(html: str, source_path: str = "<memory>") -> ParsedMapStats:
    soup = BeautifulSoup(html, "lxml")

    mapstats_id = _extract_mapstats_id(html, soup)
    event_name = _extract_event_name(soup)

    team1_name, team2_name = _extract_team_names(soup)

    map_name, team1_rounds, team2_rounds = _extract_anubis_map_block_score_and_name(soup)
    if team1_rounds is None or team2_rounds is None:
        r1, r2 = _extract_rounds_fallback(soup)
        team1_rounds = team1_rounds if team1_rounds is not None else r1
        team2_rounds = team2_rounds if team2_rounds is not None else r2

    player_ids = _extract_player_ids_from_stats_tables(soup)

    return ParsedMapStats(
        mapstats_id=mapstats_id,
        event_name=event_name,
        map_name=map_name,
        team1_name=team1_name,
        team2_name=team2_name,
        team1_rounds=team1_rounds,
        team2_rounds=team2_rounds,
        player_ids_10=player_ids[:10],
        source_path=str(source_path),
    )


def parse_mapstats_file(path: Path) -> ParsedMapStats:
    html = path.read_text(encoding="utf-8", errors="ignore")
    return parse_mapstats_html(html, source_path=str(path))
