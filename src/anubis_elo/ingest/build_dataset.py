from __future__ import annotations

import csv
from pathlib import Path

from anubis_elo.ingest.parse_mapstats_from_html import parse_mapstats_file


def main():
    in_dir = Path("data/raw/hltv/mapstats")
    out_csv = Path("data/processed/anubis_mapstats_parsed.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    html_files = list(in_dir.glob("*.html")) + list(in_dir.glob("*.htm"))
    if not html_files:
        raise FileNotFoundError(f"No HTML files found in: {in_dir}")

    def sort_key(p: Path) -> int:
        try:
            return int(p.stem)
        except Exception:
            return 10**18

    html_files.sort(key=sort_key)

    rows = []
    for p in html_files:
        try:
            rows.append(parse_mapstats_file(p))
        except Exception as e:
            print(f"[FAIL] {p.name}: {e}")

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "mapstats_id",
            "event_name",
            "map_name",
            "team1_name",
            "team2_name",
            "team1_rounds",
            "team2_rounds",
            "team1_player_ids",
            "team2_player_ids",
            "player_ids_10",
            "team1_player_names",
            "team2_player_names",
            "player_names_10",
            "source_path",
        ])

        for r in rows:
            w.writerow([
                r.mapstats_id,
                r.event_name,
                r.map_name,
                r.team1_name,
                r.team2_name,
                r.team1_rounds,
                r.team2_rounds,
                ",".join(map(str, (r.team1_player_ids or []))),
                ",".join(map(str, (r.team2_player_ids or []))),
                ",".join(map(str, (r.player_ids_10 or []))),
                ",".join((r.team1_player_names or [])),
                ",".join((r.team2_player_names or [])),
                ",".join((r.player_names_10 or [])),
                r.source_path,
            ])

    print(f"Wrote {len(rows)} rows -> {out_csv}")


if __name__ == "__main__":
    main()
