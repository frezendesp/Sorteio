#!/usr/bin/env python3
"""Gerador Lotofácil com buffer, commit, auditoria, fechamento e visualização."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen

DATA_DIR = Path("data")
RESULTS_PATH = DATA_DIR / "results.json"
BUFFER_PATH = DATA_DIR / "buffer_blocks.json"
PLAYED_PATH = DATA_DIR / "played_blocks.json"

NUMBERS = set(range(1, 26))
MOLDURA = {1, 2, 3, 4, 5, 6, 10, 11, 15, 16, 20, 21, 22, 23, 24, 25}
CENTRO = {7, 8, 9, 12, 13, 14, 17, 18, 19}
CRUZ = {3, 8, 11, 12, 13, 14, 15, 18, 23}
X_SET = {1, 5, 7, 9, 13, 17, 19, 21, 25}
PRIMOS = {2, 3, 5, 7, 11, 13, 17, 19, 23}
FIBONACCI = {1, 2, 3, 5, 8, 13, 21}

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
YELLOW = "\033[33m"


def ensure_data() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text(json.dumps({"lotofacil": []}, indent=2), encoding="utf-8")
    if not BUFFER_PATH.exists():
        BUFFER_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")
    if not PLAYED_PATH.exists():
        PLAYED_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload) -> None:
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


def count_in(game: tuple[int, ...], group: set[int]) -> int:
    return sum(1 for n in game if n in group)


def consecutive_empties_ok(game: tuple[int, ...], max_empty: int) -> bool:
    selected = set(game)
    for row in range(5):
        line = [row * 5 + c + 1 for c in range(5)]
        if max_run_empty(line, selected) > max_empty:
            return False
    for col in range(5):
        line = [r * 5 + col + 1 for r in range(5)]
        if max_run_empty(line, selected) > max_empty:
            return False
    return True


def max_run_empty(line: list[int], selected: set[int]) -> int:
    run = 0
    best = 0
    for n in line:
        if n in selected:
            run = 0
        else:
            run += 1
            best = max(best, run)
    return best


def parse_filters(raw_filters: list[str]) -> tuple[list[Callable[[tuple[int, ...]], bool]], dict[str, str]]:
    checks: list[Callable[[tuple[int, ...]], bool]] = []
    parsed: dict[str, str] = {}
    for token in raw_filters:
        lower = token.lower()
        key = lower[0]
        value = lower[1:]

        if key in {"m", "c", "p", "f", "x", "+", "e", "v"}:
            n = int(value)
            parsed[key] = token
            if key == "m":
                checks.append(lambda g, n=n: count_in(g, MOLDURA) == n)
            elif key == "c":
                checks.append(lambda g, n=n: count_in(g, CENTRO) == n)
            elif key == "p":
                checks.append(lambda g, n=n: count_in(g, PRIMOS) == n)
            elif key == "f":
                checks.append(lambda g, n=n: count_in(g, FIBONACCI) == n)
            elif key == "x":
                checks.append(lambda g, n=n: count_in(g, X_SET) == n)
            elif key == "+":
                checks.append(lambda g, n=n: count_in(g, CRUZ) == n)
            elif key == "e":
                checks.append(lambda g, n=n: sum(1 for x in g if x % 2 == 0) == n)
            elif key == "v":
                checks.append(lambda g, n=n: consecutive_empties_ok(g, n))
        elif key == "s":
            parsed[key] = token
            if "-" in value:
                lo, hi = value.split("-", 1)
                lo_i, hi_i = int(lo), int(hi)
                checks.append(lambda g, lo_i=lo_i, hi_i=hi_i: lo_i <= sum(g) <= hi_i)
            else:
                exact = int(value)
                checks.append(lambda g, exact=exact: sum(g) == exact)
        else:
            raise ValueError(f"Filtro não suportado: {token}")
    return checks, parsed


def generate_games(quantity: int, checks: list[Callable[[tuple[int, ...]], bool]], base_multiplier: int = 1) -> list[tuple[int, ...]]:
    results = load_json(RESULTS_PATH)
    past = {tuple(sorted(draw)) for draw in results.get("lotofacil", [])}
    played = load_json(PLAYED_PATH)
    past_played = {tuple(game) for b in played for game in b.get("games", [])}

    target = quantity * max(1, base_multiplier)
    chosen: set[tuple[int, ...]] = set()
    attempts = 0
    max_attempts = max(25000, target * 1500)
    while len(chosen) < target and attempts < max_attempts:
        attempts += 1
        game = tuple(sorted(random.sample(range(1, 26), 15)))
        if game in chosen or game in past or game in past_played:
            continue
        if all(fn(game) for fn in checks):
            chosen.add(game)
    if not chosen:
        raise RuntimeError("Nenhum jogo encontrado para os filtros informados.")
    return sorted(chosen)


def similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def optimize_block(games: list[tuple[int, ...]], threshold: float = 0.72) -> list[tuple[int, ...]]:
    optimized: list[tuple[int, ...]] = []
    for game in games:
        if all(similarity(game, keep) < threshold for keep in optimized):
            optimized.append(game)
    return optimized


def apply_fechamento(games: list[tuple[int, ...]], target_guarantee: int, desired_qty: int) -> list[tuple[int, ...]]:
    scored = sorted(games, key=lambda g: abs(count_in(g, PRIMOS) - 5) + abs(sum(g) - 200) / 20)
    if target_guarantee >= 14:
        reduced = optimize_block(scored, threshold=0.68)
    else:
        reduced = optimize_block(scored, threshold=0.75)
    return reduced[:desired_qty] if len(reduced) >= desired_qty else scored[:desired_qty]


def next_id(blocks: list[dict]) -> int:
    return max((b.get("id", 0) for b in blocks), default=0) + 1


def save_to_buffer(games: list[tuple[int, ...]], filters: list[str], fechamento: int | None, optimized: bool) -> int:
    blocks = load_json(BUFFER_PATH)
    block_id = next_id(blocks)
    blocks.append(
        {
            "id": block_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filters": filters,
            "fechamento": fechamento,
            "optimized": optimized,
            "games": [list(g) for g in games],
        }
    )
    save_json(BUFFER_PATH, blocks)
    return block_id


def commit_block(block_id: int) -> dict:
    buffer_blocks = load_json(BUFFER_PATH)
    played = load_json(PLAYED_PATH)
    found = None
    remaining = []
    for b in buffer_blocks:
        if b.get("id") == block_id and found is None:
            found = b
        else:
            remaining.append(b)
    if not found:
        raise ValueError(f"Bloco {block_id} não encontrado no buffer")

    found["committed_at"] = datetime.now(timezone.utc).isoformat()
    played.append(found)
    save_json(BUFFER_PATH, remaining)
    save_json(PLAYED_PATH, played)
    return found


def render_matrix(game: list[int], filter_tokens: list[str]) -> str:
    selected = set(game)
    lines: list[str] = []
    for r in range(5):
        row = []
        for c in range(5):
            n = r * 5 + c + 1
            txt = f"{n:02d}" if n in selected else ".."
            style = ""
            if n in selected and n in PRIMOS:
                style += BOLD + GREEN
            if n in selected and n in MOLDURA:
                style += CYAN
            if n in selected and n in FIBONACCI:
                style += MAGENTA
            if n in selected and n in CRUZ:
                style += YELLOW
            row.append(f"{style}{txt}{RESET}" if style else txt)
        lines.append(" ".join(row))
    header = f"Filtros: {' '.join(filter_tokens) if filter_tokens else '(sem filtros)'}"
    return header + "\n" + "\n".join(lines)


def view_block(block_id: int | None, source: str) -> None:
    blocks = load_json(BUFFER_PATH if source == "buffer" else PLAYED_PATH)
    if not blocks:
        print("Nenhum bloco disponível para visualização.")
        return
    if block_id is None:
        block = blocks[-1]
    else:
        block = next((b for b in blocks if b.get("id") == block_id), None)
    if not block:
        print(f"Bloco {block_id} não encontrado em {source}.")
        return

    print(f"Bloco {block['id']} ({source}) | jogos: {len(block.get('games', []))}")
    for idx, game in enumerate(block.get("games", []), start=1):
        print(f"\nJogo {idx}")
        print(render_matrix(game, block.get("filters", [])))


def fetch_latest_lotofacil() -> list[int]:
    with urlopen("https://loteriascaixa-api.herokuapp.com/api/lotofacil/latest", timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    dezenas = payload.get("dezenas") or []
    return sorted(int(x) for x in dezenas)


def check_last() -> None:
    played = load_json(PLAYED_PATH)
    if not played:
        print(json.dumps({"error": "Nenhum bloco jogado para auditar."}, ensure_ascii=False))
        return
    block = played[-1]
    try:
        latest = fetch_latest_lotofacil()
    except URLError as exc:
        print(json.dumps({"error": f"Falha ao consultar API: {exc.reason}"}, ensure_ascii=False))
        return

    result = set(latest)
    hits_count = {11: 0, 12: 0, 13: 0, 14: 0, 15: 0}
    per_game = []
    for game in block.get("games", []):
        hits = len(set(game) & result)
        if hits in hits_count:
            hits_count[hits] += 1
        per_game.append({"game": game, "hits": hits})

    print(json.dumps({"block_id": block.get("id"), "latest": latest, "awards": hits_count, "games": per_game}, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lotofácil com buffer, fechamento, view e auditoria", add_help=False)
    p.add_argument("--help", action="help", help="Mostra ajuda")
    p.add_argument("-f", nargs="*", default=[], help="Filtros: m,c,+,x,p,f,s,v (ex: p5 m9 s190-220)")
    p.add_argument("-q", type=int, default=10, help="Quantidade de jogos")
    p.add_argument("-o", choices=["txt", "json"], default="txt", help="Formato saída")
    p.add_argument("--view", action="store_true", help="Visualiza bloco em matriz 5x5")
    p.add_argument("--view-id", type=int, help="ID do bloco para --view")
    p.add_argument("--view-source", choices=["buffer", "played"], default="buffer", help="Fonte do --view")
    p.add_argument("--buffer", action="store_true", help="Grava bloco em buffer temporário")
    p.add_argument("--commit", type=int, help="Move ID do buffer para histórico jogado")
    p.add_argument("--check-last", action="store_true", help="Audita último bloco jogado contra último resultado")
    p.add_argument("--fechamento", type=int, help="Garantia pretendida (ex: 14)")
    p.add_argument("--optimize", action="store_true", help="Remove jogos redundantes no bloco")
    return p.parse_args()


def main() -> None:
    ensure_data()
    args = parse_args()

    if args.commit is not None:
        committed = commit_block(args.commit)
        print(json.dumps({"committed_id": committed["id"], "games": len(committed.get("games", []))}, ensure_ascii=False))
        return

    if args.view:
        view_block(args.view_id, args.view_source)
        return

    if args.check_last:
        check_last()
        return

    checks, _ = parse_filters(args.f)
    base_multiplier = 3 if args.fechamento else 1
    games = generate_games(args.q, checks, base_multiplier=base_multiplier)

    if args.fechamento:
        games = apply_fechamento(games, args.fechamento, args.q)

    optimized = False
    if args.optimize:
        games = optimize_block(games)
        optimized = True

    if args.buffer:
        block_id = save_to_buffer(games, args.f, args.fechamento, optimized)
        print(json.dumps({"buffer_id": block_id, "games": len(games)}, ensure_ascii=False))
        return

    if args.o == "json":
        print(json.dumps({"games": [list(g) for g in games], "quantity": len(games)}, ensure_ascii=False))
    else:
        for g in games:
            print(" ".join(f"{n:02d}" for n in g))


if __name__ == "__main__":
    main()
