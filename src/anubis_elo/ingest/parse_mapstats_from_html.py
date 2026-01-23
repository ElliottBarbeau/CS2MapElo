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

    team1_player_ids: list[int]
    team2_player_ids: list[int]
    player_ids_10: list[int]

    team1_player_names: list[str]
    team2_player_names: list[str]
    player_names_10: list[str]

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
        txt = txt.replace("–", "-").replace("—", "-")
        parts = [p.strip() for p in txt.split("-")]
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


def _players_from_table(table) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for a in table.select('td.st-player a[href*="/stats/players/"]'):
        href = a.get("href") or ""
        m = STATS_PLAYER_ID_RE.search(href)
        if not m:
            continue
        pid = int(m.group(1))
        name = a.get_text(strip=True) or ""
        found.append((pid, name))

    seen: set[int] = set()
    out: list[tuple[int, str]] = []
    for pid, name in found:
        if pid in seen:
            continue
        seen.add(pid)
        out.append((pid, name))
    return out


def _extract_team_players(soup: BeautifulSoup) -> tuple[list[int], list[int], list[str], list[str]]:
    tables = soup.select("table.stats-table.totalstats")
    if len(tables) < 2:
        return [], [], [], []

    t1 = _players_from_table(tables[0])[:5]
    t2 = _players_from_table(tables[1])[:5]

    team1_ids = [pid for pid, _ in t1]
    team2_ids = [pid for pid, _ in t2]
    team1_names = [name for _, name in t1]
    team2_names = [name for _, name in t2]

    return team1_ids, team2_ids, team1_names, team2_names


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

    team1_player_ids, team2_player_ids, team1_player_names, team2_player_names = _extract_team_players(soup)
    player_ids_10 = (team1_player_ids + team2_player_ids)[:10]
    player_names_10 = (team1_player_names + team2_player_names)[:10]

    return ParsedMapStats(
        mapstats_id=mapstats_id,
        event_name=event_name,
        map_name=map_name,
        team1_name=team1_name,
        team2_name=team2_name,
        team1_rounds=team1_rounds,
        team2_rounds=team2_rounds,
        team1_player_ids=team1_player_ids,
        team2_player_ids=team2_player_ids,
        player_ids_10=player_ids_10,
        team1_player_names=team1_player_names,
        team2_player_names=team2_player_names,
        player_names_10=player_names_10,
        source_path=str(source_path),
    )


def parse_mapstats_file(path: Path) -> ParsedMapStats:
    html = path.read_text(encoding="utf-8", errors="ignore")
    return parse_mapstats_html(html, source_path=str(path))
