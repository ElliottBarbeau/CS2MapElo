from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class MatchRow:
    mapstats_id: int
    event_name: str
    map_name: str
    team1_name: str
    team2_name: str
    team1_rounds: int
    team2_rounds: int
    team1_player_ids: List[int]
    team2_player_ids: List[int]
    team1_player_names: List[str]
    team2_player_names: List[str]
    source_path: str


def _parse_int_list(s: str) -> List[int]:
    s = (s or "").strip()
    if not s:
        return []
    out: List[int] = []
    for part in s.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _parse_str_list(s: str) -> List[str]:
    s = (s or "").strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _read_matches(csv_path: Path) -> List[MatchRow]:
    matches: List[MatchRow] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        required = [
            "mapstats_id",
            "event_name",
            "map_name",
            "team1_name",
            "team2_name",
            "team1_rounds",
            "team2_rounds",
            "team1_player_ids",
            "team2_player_ids",
            "team1_player_names",
            "team2_player_names",
            "source_path",
        ]
        for k in required:
            if k not in (r.fieldnames or []):
                raise ValueError(f"Missing required column: {k}")

        for row in r:
            try:
                matches.append(
                    MatchRow(
                        mapstats_id=int(row["mapstats_id"]),
                        event_name=row["event_name"] or "",
                        map_name=row["map_name"] or "",
                        team1_name=row["team1_name"] or "",
                        team2_name=row["team2_name"] or "",
                        team1_rounds=int(row["team1_rounds"]),
                        team2_rounds=int(row["team2_rounds"]),
                        team1_player_ids=_parse_int_list(row["team1_player_ids"]),
                        team2_player_ids=_parse_int_list(row["team2_player_ids"]),
                        team1_player_names=_parse_str_list(row["team1_player_names"]),
                        team2_player_names=_parse_str_list(row["team2_player_names"]),
                        source_path=row["source_path"] or "",
                    )
                )
            except Exception:
                continue
    return matches


def _mean(vals: List[float]) -> float:
    if not vals:
        return 0.0
    return sum(vals) / float(len(vals))


def _expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def _round_weight(r1: int, r2: int, mode: str, cap: float) -> float:
    if mode == "none":
        return 1.0
    rd = abs(r1 - r2)
    if mode == "linear":
        w = 1.0 + (rd / 12.0)
        return min(cap, w)
    if mode == "sqrt":
        w = 1.0 + math.sqrt(rd) / math.sqrt(12.0)
        return min(cap, w)
    raise ValueError(f"Unknown weight mode: {mode}")


def _winner_score(r1: int, r2: int) -> float:
    if r1 == r2:
        return 0.5
    return 1.0 if r1 > r2 else 0.0


def _validate_teams(ids1: List[int], ids2: List[int], names1: List[str], names2: List[str]) -> bool:
    if len(ids1) != 5 or len(ids2) != 5:
        return False
    if len(names1) != 5 or len(names2) != 5:
        return False
    if len(set(ids1)) != 5 or len(set(ids2)) != 5:
        return False
    if set(ids1).intersection(set(ids2)):
        return False
    return True


def _build_canonical_name_map(matches: List[MatchRow]) -> Dict[int, str]:
    counts: Dict[int, Dict[str, int]] = {}

    def add(pid: int, name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        if pid not in counts:
            counts[pid] = {}
        counts[pid][name] = counts[pid].get(name, 0) + 1

    for m in matches:
        if (m.map_name or "").lower() != "anubis":
            continue
        if len(m.team1_player_ids) == len(m.team1_player_names):
            for pid, nm in zip(m.team1_player_ids, m.team1_player_names):
                add(pid, nm)
        if len(m.team2_player_ids) == len(m.team2_player_names):
            for pid, nm in zip(m.team2_player_ids, m.team2_player_names):
                add(pid, nm)

    out: Dict[int, str] = {}
    for pid, name_counts in counts.items():
        best = sorted(name_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)[0][0]
        out[pid] = best
    return out


def _make_unique_names(pid_to_name: Dict[int, str]) -> Dict[int, str]:
    name_to_pids: Dict[str, List[int]] = {}
    for pid, name in pid_to_name.items():
        name_to_pids.setdefault(name, []).append(pid)

    out: Dict[int, str] = dict(pid_to_name)
    for name, pids in name_to_pids.items():
        if len(pids) <= 1:
            continue
        for pid in sorted(pids):
            out[pid] = f"{name} ({pid})"
    return out


def backtest(
    matches: List[MatchRow],
    pid_to_name: Dict[int, str],
    k: float,
    init_rating: float,
    weight_mode: str,
    weight_cap: float,
    start_id: Optional[int],
    end_id: Optional[int],
) -> Tuple[Dict[int, float], Dict[int, Dict[str, int]], Dict[str, float]]:
    ratings: Dict[int, float] = {}
    stats: Dict[int, Dict[str, int]] = {}
    n = 0
    correct = 0
    ll_sum = 0.0

    def get_r(pid: int) -> float:
        return ratings.get(pid, init_rating)

    def ensure(pid: int) -> None:
        if pid not in ratings:
            ratings[pid] = init_rating
        if pid not in stats:
            stats[pid] = {"games": 0, "wins": 0, "losses": 0}

    matches_sorted = sorted(matches, key=lambda m: m.mapstats_id)

    for m in matches_sorted:
        if start_id is not None and m.mapstats_id < start_id:
            continue
        if end_id is not None and m.mapstats_id > end_id:
            continue
        if (m.map_name or "").lower() != "anubis":
            continue

        t1_ids = m.team1_player_ids
        t2_ids = m.team2_player_ids
        t1_names = m.team1_player_names
        t2_names = m.team2_player_names

        if not _validate_teams(t1_ids, t2_ids, t1_names, t2_names):
            continue

        for pid, nm in zip(t1_ids, t1_names):
            if pid not in pid_to_name and (nm or "").strip():
                pid_to_name[pid] = nm.strip()

        for pid, nm in zip(t2_ids, t2_names):
            if pid not in pid_to_name and (nm or "").strip():
                pid_to_name[pid] = nm.strip()

        for pid in t1_ids + t2_ids:
            ensure(pid)

        r1 = _mean([get_r(pid) for pid in t1_ids])
        r2 = _mean([get_r(pid) for pid in t2_ids])

        e1 = _expected_score(r1, r2)
        s1 = _winner_score(m.team1_rounds, m.team2_rounds)
        w = _round_weight(m.team1_rounds, m.team2_rounds, weight_mode, weight_cap)

        eps = 1e-12
        p = min(1.0 - eps, max(eps, e1))
        ll_sum += -(s1 * math.log(p) + (1.0 - s1) * math.log(1.0 - p))
        n += 1
        if (e1 >= 0.5 and s1 == 1.0) or (e1 < 0.5 and s1 == 0.0):
            correct += 1

        delta1 = k * w * (s1 - e1)
        delta2 = -delta1

        for pid in t1_ids:
            ratings[pid] = get_r(pid) + delta1
            stats[pid]["games"] += 1
            if s1 == 1.0:
                stats[pid]["wins"] += 1
            elif s1 == 0.0:
                stats[pid]["losses"] += 1

        for pid in t2_ids:
            ratings[pid] = get_r(pid) + delta2
            stats[pid]["games"] += 1
            if s1 == 0.0:
                stats[pid]["wins"] += 1
            elif s1 == 1.0:
                stats[pid]["losses"] += 1

    metrics = {
        "matches_used": float(n),
        "accuracy": float(correct) / float(n) if n else 0.0,
        "log_loss": float(ll_sum) / float(n) if n else 0.0,
    }
    return ratings, stats, metrics


def write_ratings(out_path: Path, ratings: Dict[int, float], stats: Dict[int, Dict[str, int]], pid_to_name: Dict[int, str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for pid, r in ratings.items():
        name = pid_to_name.get(pid, str(pid))
        s = stats.get(pid, {"games": 0, "wins": 0, "losses": 0})
        rows.append((name, r, s["games"], s["wins"], s["losses"]))
    rows.sort(key=lambda x: x[1], reverse=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player_name", "elo", "games", "wins", "losses"])
        for name, r, g, wi, lo in rows:
            w.writerow([name, f"{r:.2f}", g, wi, lo])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-csv", default="data/processed/anubis_mapstats_parsed.csv")
    ap.add_argument("--out-csv", default="data/processed/anubis_player_elo_2025.csv")
    ap.add_argument("--k", type=float, default=24.0)
    ap.add_argument("--init", type=float, default=1500.0)
    ap.add_argument("--weight", choices=["none", "linear", "sqrt"], default="linear")
    ap.add_argument("--weight-cap", type=float, default=2.0)
    ap.add_argument("--start-id", type=int, default=None)
    ap.add_argument("--end-id", type=int, default=None)
    args = ap.parse_args()

    in_csv = Path(args.in_csv)
    matches = _read_matches(in_csv)

    pid_to_name = _build_canonical_name_map(matches)
    pid_to_name = _make_unique_names(pid_to_name)

    ratings, stats, metrics = backtest(
        matches=matches,
        pid_to_name=pid_to_name,
        k=args.k,
        init_rating=args.init,
        weight_mode=args.weight,
        weight_cap=args.weight_cap,
        start_id=args.start_id,
        end_id=args.end_id,
    )

    out_csv = Path(args.out_csv)
    write_ratings(out_csv, ratings, stats, pid_to_name)

    top_items = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
    print(f"matches_used={int(metrics['matches_used'])} accuracy={metrics['accuracy']:.4f} log_loss={metrics['log_loss']:.4f}")
    print(f"wrote -> {out_csv}")
    for pid, r in top_items:
        name = pid_to_name.get(pid, str(pid))
        s = stats.get(pid, {"games": 0, "wins": 0, "losses": 0})
        print(f"{name}\t{r:.2f}\tgames={s['games']}\twins={s['wins']}\tlosses={s['losses']}")


if __name__ == "__main__":
    main()
