#!/usr/bin/env python3
"""Ferramenta de sincronização e estatística para loterias."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DATA_DIR = Path("data")
RESULTS_PATH = DATA_DIR / "results.json"
FILTERS_PATH = DATA_DIR / "filters_history.json"
BLOCKS_PATH = DATA_DIR / "generated_blocks.json"

API_BASE = "https://loteriascaixa-api.herokuapp.com/api"
GAME_ENDPOINT = {
    "lotofacil": "lotofacil",
    "megasena": "megasena",
    "lotomania": "lotomania",
}


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text(json.dumps({"lotofacil": [], "megasena": [], "lotomania": []}, indent=2), encoding="utf-8")
    if not FILTERS_PATH.exists():
        FILTERS_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")
    if not BLOCKS_PATH.exists():
        BLOCKS_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    return {
        "draws": len(draws),
        "top_numbers": counter.most_common(10),
        "odd_even_ratio": {"odd": odd, "even": even},
    }


def build_filters_snapshot(game_name: str, draws: list[list[int]], history: int) -> dict[str, Any]:
    limited = draws[-history:] if history > 0 else draws

    parity = Counter(sum(1 for n in draw if n % 2 == 0) for draw in limited)
    primes = Counter(sum(1 for n in draw if is_prime(n)) for draw in limited)

    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "game": game_name,
        "history": history,
        "parity": parity,
        "primes": primes,
        "blocks_50": [stat_block(limited[i : i + 50]) for i in range(0, len(limited), 50)],
        "global": stat_block(limited),
    }
    return snapshot


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


def append_filter_history(history: int) -> None:
    db = load_json(RESULTS_PATH)
    archive = load_json(FILTERS_PATH)

    for game_name, draws in db.items():
        archive.append(build_filters_snapshot(game_name, draws, history))

    save_json(FILTERS_PATH, archive)
    print(json.dumps({"saved_snapshots": len(db)}, ensure_ascii=False))


def check_blocks() -> None:
    db = load_json(RESULTS_PATH)
    blocks = load_json(BLOCKS_PATH)
    report = []

    for block in blocks:
        game = block.get("game")
        draws = [set(draw) for draw in db.get(game, [])]
        for game_played in block.get("games", []):
            candidate = set(game_played)
            best = max((len(candidate & draw) for draw in draws), default=0)
            report.append({"game": game, "candidate": game_played, "best_hit": best})

    print(json.dumps({"checks": report}, ensure_ascii=False))


def prime_stats_per_draw(game_name: str, history: int) -> None:
    db = load_json(RESULTS_PATH)
    draws = db.get(game_name, [])
    if not draws:
        print(json.dumps({"game": game_name, "history": history, "draws": [], "distribution": {}}, ensure_ascii=False))
        return

    limited = draws[-history:] if history > 0 else draws
    per_draw = []
    distribution = Counter()

    for idx, draw in enumerate(limited, start=1):
        prime_count = sum(1 for n in draw if is_prime(n))
        distribution[prime_count] += 1
        per_draw.append({"index": idx, "draw": sorted(draw), "prime_count": prime_count})

    payload = {
        "game": game_name,
        "history": history,
        "analyzed_draws": len(limited),
        "distribution": dict(sorted(distribution.items())),
        "draws": per_draw,
    }
    print(json.dumps(payload, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sincroniza dados e calcula estatísticas de loterias", add_help=False)
    p.add_argument("--help", action="help", help="Mostra esta ajuda e sai")
    p.add_argument("-h", "--history", type=int, default=200, dest="history", help="Quantidade de concursos para cálculo")
    p.add_argument("-sync", action="store_true", help="Sincroniza base local via API")
    p.add_argument("-check", action="store_true", help="Valida blocos antigos")
    p.add_argument("-prime-stats", action="store_true", help="Exibe primos por sorteio no histórico selecionado")
    p.add_argument(
        "-g",
        "--game",
        choices=["lotofacil", "megasena", "lotomania"],
        default="lotofacil",
        help="Modalidade usada em -prime-stats",
    )
    return p


def main() -> None:
    args = parser().parse_args()
    ensure_data_files()

    if args.sync:
        sync_results()

    append_filter_history(args.history)

    if args.check:
        check_blocks()

    if args.prime_stats:
        prime_stats_per_draw(args.game, args.history)


if __name__ == "__main__":
    main()
