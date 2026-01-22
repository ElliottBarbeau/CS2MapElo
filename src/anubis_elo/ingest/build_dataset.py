from __future__ import annotations

import csv
from pathlib import Path

from anubis_elo.ingest.parse_mapstats_from_html import parse_mapstats_file


def main():
    in_dir = Path("data/raw/hltv/mapstats")
    out_csv = Path("data/processed/anubis_mapstats_parsed.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in sorted(in_dir.glob("*.html")):
        try:
            parsed = parse_mapstats_file(p)
            rows.append(parsed)
        except Exception as e:
            print(f"[FAIL] {p.name}: {e}")

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "mapstats_id", "event_name", "map_name",
            "team1_name", "team2_name", "team1_rounds", "team2_rounds",
            "player_ids_10", "source_path",
        ])
        for r in rows:
            w.writerow([
                r.mapstats_id, r.event_name, r.map_name,
                r.team1_name, r.team2_name, r.team1_rounds, r.team2_rounds,
                ",".join(map(str, r.player_ids_10)),
                r.source_path,
            ])

    print(f"Wrote {len(rows)} rows -> {out_csv}")


if __name__ == "__main__":
    main()
