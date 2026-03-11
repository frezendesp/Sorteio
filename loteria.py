#!/usr/bin/env python3
"""CLI para geração de jogos de loteria com filtros e validação histórica."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Callable

DATA_DIR = Path("data")
RESULTS_PATH = DATA_DIR / "results.json"
BLOCKS_PATH = DATA_DIR / "generated_blocks.json"

GAME_CONFIG = {
    "lf": {"name": "lotofacil", "pool": 25, "pick": 15},
    "ms": {"name": "megasena", "pool": 60, "pick": 6},
    "lm": {"name": "lotomania", "pool": 100, "pick": 50},
}


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text(json.dumps({"lotofacil": [], "megasena": [], "lotomania": []}, indent=2), encoding="utf-8")
    if not BLOCKS_PATH.exists():
        BLOCKS_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_game(raw_game: list[int]) -> tuple[int, ...]:
    return tuple(sorted(raw_game))


def parity_filter(game: tuple[int, ...], value: int) -> bool:
    evens = sum(1 for n in game if n % 2 == 0)
    return evens == value


def prime_filter(game: tuple[int, ...], value: int) -> bool:
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

    return sum(1 for n in game if is_prime(n)) == value


def border_filter(game: tuple[int, ...], game_key: str, value: int) -> bool:
    cfg = GAME_CONFIG[game_key]
    cols = 5 if game_key in {"lf", "lm"} else 10
    rows = cfg["pool"] // cols
    border = 0
    for n in game:
        idx = n - 1
        r = idx // cols
        c = idx % cols
        if r in {0, rows - 1} or c in {0, cols - 1}:
            border += 1
    return border == value


def parse_filters(filters: list[str], game_key: str) -> list[Callable[[tuple[int, ...]], bool]]:
    parsed: list[Callable[[tuple[int, ...]], bool]] = []
    for raw in filters:
        key = raw[:1].lower()
        try:
            value = int(raw[1:])
        except ValueError as exc:
            raise ValueError(f"Filtro inválido: {raw}") from exc

        if key == "p":
            parsed.append(lambda g, v=value: parity_filter(g, v))
        elif key == "m":
            parsed.append(lambda g, v=value: border_filter(g, game_key, v))
        elif key == "r":
            parsed.append(lambda g, v=value: prime_filter(g, v))
        else:
            raise ValueError(f"Filtro não suportado: {raw}. Use pN, mN, rN")
    return parsed


def generate_games(game_key: str, quantity: int, filters: list[Callable[[tuple[int, ...]], bool]]) -> list[tuple[int, ...]]:
    cfg = GAME_CONFIG[game_key]
    results_db = load_json(RESULTS_PATH)
    past_draws = {normalize_game(draw) for draw in results_db.get(cfg["name"], [])}

    blocks = load_json(BLOCKS_PATH)
    generated_before = {
        tuple(game) for block in blocks if block.get("game") == cfg["name"] for game in block.get("games", [])
    }

    chosen: set[tuple[int, ...]] = set()
    attempts = 0
    max_attempts = max(5000, quantity * 800)
    while len(chosen) < quantity and attempts < max_attempts:
        attempts += 1
        game = normalize_game(random.sample(range(1, cfg["pool"] + 1), cfg["pick"]))
        if game in past_draws or game in generated_before or game in chosen:
            continue
        if all(check(game) for check in filters):
            chosen.add(game)

    if len(chosen) < quantity:
        raise RuntimeError(
            f"Não foi possível gerar {quantity} jogos com os filtros aplicados. "
            f"Obtidos: {len(chosen)}"
        )
    return sorted(chosen)


def save_block(game_key: str, games: list[tuple[int, ...]], filters: list[str]) -> None:
    blocks = load_json(BLOCKS_PATH)
    blocks.append(
        {
            "game": GAME_CONFIG[game_key]["name"],
            "filters": filters,
            "games": [list(game) for game in games],
        }
    )
    BLOCKS_PATH.write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera jogos com filtros para Lotofácil, Mega-Sena e Lotomania")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-lf", action="store_true", help="Lotofácil")
    group.add_argument("-ms", action="store_true", help="Mega-Sena")
    group.add_argument("-lm", action="store_true", help="Lotomania")
    parser.add_argument("-f", nargs="*", default=[], help="Filtros (ex: p7 m8 r5)")
    parser.add_argument("-q", type=int, default=10, help="Quantidade de jogos")
    parser.add_argument("-o", choices=["json", "txt"], default="txt", help="Formato de saída")
    parser.add_argument("--save", action="store_true", help="Salva bloco gerado no histórico")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    ensure_data_files()

    game_key = "lf" if args.lf else "ms" if args.ms else "lm"
    checks = parse_filters(args.f, game_key)
    games = generate_games(game_key, args.q, checks)

    if args.save:
        save_block(game_key, games, args.f)

    if args.o == "json":
        payload = {
            "game": GAME_CONFIG[game_key]["name"],
            "filters": args.f,
            "quantity": len(games),
            "games": [list(game) for game in games],
            "saved": bool(args.save),
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for game in games:
            print(" ".join(f"{n:02d}" for n in game))
        if args.save:
            print("Bloco salvo.")


if __name__ == "__main__":
    main()
