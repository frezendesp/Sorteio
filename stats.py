#!/usr/bin/env python3
"""Análises estatísticas para loterias com presets, ciclo, afinidade e backtest."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DATA_DIR = Path("data")
RESULTS_PATH = DATA_DIR / "results.json"
FILTERS_PATH = DATA_DIR / "filters_history.json"
GROUPS_PATH = DATA_DIR / "filter_groups.json"
PLAYED_PATH = DATA_DIR / "played_blocks.json"

API_BASE = "https://loteriascaixa-api.herokuapp.com/api"
GAME_ENDPOINT = {"lotofacil": "lotofacil", "megasena": "megasena", "lotomania": "lotomania"}


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text(json.dumps({"lotofacil": [], "megasena": [], "lotomania": []}, indent=2), encoding="utf-8")
    if not FILTERS_PATH.exists():
        FILTERS_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")
    if not GROUPS_PATH.exists():
        GROUPS_PATH.write_text(json.dumps({}, indent=2), encoding="utf-8")
    if not PLAYED_PATH.exists():
        PLAYED_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True


def fetch_latest(endpoint: str) -> list[int]:
    with urlopen(f"{API_BASE}/{endpoint}/latest", timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    dezenas = data.get("dezenas") or []
    return sorted(int(n) for n in dezenas)


def sync_results() -> None:
    db = load_json(RESULTS_PATH)
    updates = {}
    for game_name, endpoint in GAME_ENDPOINT.items():
        try:
            latest = fetch_latest(endpoint)
        except URLError as exc:
            updates[game_name] = f"falha: {exc.reason}"
            continue

        current = [tuple(sorted(draw)) for draw in db.get(game_name, [])]
        marker = tuple(latest)
        if marker and marker not in current:
            db.setdefault(game_name, []).append(latest)
            updates[game_name] = "novo concurso salvo"
        else:
            updates[game_name] = "sem mudanças"

    save_json(RESULTS_PATH, db)
    print(json.dumps({"sync": updates}, ensure_ascii=False))


def stat_block(draws: list[list[int]]) -> dict[str, Any]:
    numbers = [n for draw in draws for n in draw]
    if not numbers:
        return {"draws": 0, "top_numbers": [], "odd_even_ratio": {"odd": 0, "even": 0}}

    counter = Counter(numbers)
    odd = sum(1 for n in numbers if n % 2)
    even = len(numbers) - odd
    return {"draws": len(draws), "top_numbers": counter.most_common(10), "odd_even_ratio": {"odd": odd, "even": even}}


def build_filters_snapshot(game_name: str, draws: list[list[int]], history: int) -> dict[str, Any]:
    limited = draws[-history:] if history > 0 else draws
    parity = Counter(sum(1 for n in draw if n % 2 == 0) for draw in limited)
    primes = Counter(sum(1 for n in draw if is_prime(n)) for draw in limited)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "game": game_name,
        "history": history,
        "parity": parity,
        "primes": primes,
        "blocks_50": [stat_block(limited[i : i + 50]) for i in range(0, len(limited), 50)],
        "global": stat_block(limited),
    }


def append_filter_history(history: int) -> None:
    db = load_json(RESULTS_PATH)
    archive = load_json(FILTERS_PATH)
    for game_name, draws in db.items():
        archive.append(build_filters_snapshot(game_name, draws, history))
    save_json(FILTERS_PATH, archive)
    print(json.dumps({"saved_snapshots": len(db)}, ensure_ascii=False))


def prime_stats_per_draw(game_name: str, history: int) -> None:
    db = load_json(RESULTS_PATH)
    draws = db.get(game_name, [])
    limited = draws[-history:] if history > 0 else draws
    distribution = Counter()
    per_draw = []
    for idx, draw in enumerate(limited, start=1):
        prime_count = sum(1 for n in draw if is_prime(n))
        distribution[prime_count] += 1
        per_draw.append({"index": idx, "draw": sorted(draw), "prime_count": prime_count})
    print(json.dumps({"game": game_name, "history": history, "distribution": dict(sorted(distribution.items())), "draws": per_draw}, ensure_ascii=False))


def create_group(name: str, filters: list[str]) -> None:
    groups = load_json(GROUPS_PATH)
    groups[name] = {"filters": filters, "created_at": datetime.now(timezone.utc).isoformat()}
    save_json(GROUPS_PATH, groups)
    print(json.dumps({"created_group": name, "filters": filters}, ensure_ascii=False))


def cycle_analysis() -> None:
    db = load_json(RESULTS_PATH)
    draws = db.get("lotofacil", [])
    seen = set()
    contests = 0
    for draw in reversed(draws):
        contests += 1
        seen.update(draw)
        if len(seen) == 25:
            break
    missing = sorted(set(range(1, 26)) - seen)
    print(json.dumps({"cycle_contests": contests, "missing_numbers": missing, "seen_count": len(seen)}, ensure_ascii=False))


def affinity(game_name: str, size: int, history: int, top: int = 20) -> None:
    db = load_json(RESULTS_PATH)
    draws = db.get(game_name, [])
    limited = draws[-history:] if history > 0 else draws
    counts = Counter()
    for draw in limited:
        for combo in combinations(sorted(draw), size):
            counts[combo] += 1
    top_items = [{"combo": list(c), "freq": f} for c, f in counts.most_common(top)]
    print(json.dumps({"game": game_name, "group_size": size, "history": history, "top": top_items}, ensure_ascii=False))


def get_block_by_id(block_id: int) -> dict[str, Any] | None:
    blocks = load_json(PLAYED_PATH)
    for b in blocks:
        if b.get("id") == block_id:
            return b
    return None


def coverage(block_id: int) -> None:
    block = get_block_by_id(block_id)
    if not block:
        print(json.dumps({"error": "Bloco não encontrado"}, ensure_ascii=False))
        return
    db = load_json(RESULTS_PATH)
    draws = db.get("lotofacil", [])
    if not draws:
        print(json.dumps({"error": "Sem resultados para cobertura"}, ensure_ascii=False))
        return

    block_sets = [set(g) for g in block.get("games", [])]
    max_hits = []
    for d in draws:
        ds = set(d)
        max_hits.append(max((len(ds & g) for g in block_sets), default=0))

    dist = Counter(max_hits)
    total = len(max_hits)
    probs = {str(k): round(v / total, 4) for k, v in sorted(dist.items())}
    print(json.dumps({"block_id": block_id, "historical_draws": total, "max_hit_distribution": probs}, ensure_ascii=False))


def backtest(block_id: int, history: int) -> None:
    block = get_block_by_id(block_id)
    if not block:
        print(json.dumps({"error": "Bloco não encontrado"}, ensure_ascii=False))
        return

    db = load_json(RESULTS_PATH)
    draws = db.get("lotofacil", [])
    limited = draws[-history:] if history > 0 else draws
    block_sets = [set(g) for g in block.get("games", [])]

    summary = Counter()
    details = []
    for i, draw in enumerate(limited, start=1):
        ds = set(draw)
        best = max((len(ds & g) for g in block_sets), default=0)
        summary[best] += 1
        details.append({"contest_index": i, "draw": draw, "best_hit": best})

    print(json.dumps({"block_id": block_id, "history": history, "summary": dict(sorted(summary.items())), "details": details}, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sincroniza dados e calcula estatísticas", add_help=False)
    p.add_argument("--help", action="help", help="Mostra ajuda")
    p.add_argument("-h", "--history", type=int, default=200, dest="history", help="Histórico usado nas análises")
    p.add_argument("-sync", action="store_true", help="Sincroniza resultados")
    p.add_argument("-prime-stats", action="store_true", help="Primos por sorteio")
    p.add_argument("-g", "--game", choices=["lotofacil", "megasena", "lotomania"], default="lotofacil")

    p.add_argument("--create-group", nargs="+", metavar=("NOME", "FILTRO"), help="Cria preset de filtros")
    p.add_argument("--ciclo", action="store_true", help="Mostra números faltantes para fechar ciclo da Lotofácil")
    p.add_argument("--affinity", type=int, choices=[2, 3, 4], help="Ranking de duplas/trios/quadras por frequência")
    p.add_argument("--coverage", type=int, metavar="ID_BLOCO", help="Cobertura histórica do bloco")
    p.add_argument("--backtest", type=int, metavar="ID_BLOCO", help="Backtest do bloco")
    return p


def main() -> None:
    args = parser().parse_args()
    ensure_data_files()

    if args.sync:
        sync_results()

    append_filter_history(args.history)

    if args.create_group:
        name, *filters = args.create_group
        create_group(name, filters)

    if args.ciclo:
        cycle_analysis()

    if args.affinity:
        affinity(args.game, args.affinity, args.history)

    if args.coverage is not None:
        coverage(args.coverage)

    if args.backtest is not None:
        backtest(args.backtest, args.history)

    if args.prime_stats:
        prime_stats_per_draw(args.game, args.history)


if __name__ == "__main__":
    main()
