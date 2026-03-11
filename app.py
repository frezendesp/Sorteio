#!/usr/bin/env python3
from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)

DATA_DIR = Path("data")
RESULTS_PATH = DATA_DIR / "results.json"
BUFFER_PATH = DATA_DIR / "buffer_blocks.json"
PLAYED_PATH = DATA_DIR / "played_blocks.json"
GROUPS_PATH = DATA_DIR / "filter_groups.json"

API_LOTOFACIL = "https://loteriascaixa-api.herokuapp.com/api/lotofacil/latest"

MOLDURA = {1, 2, 3, 4, 5, 6, 10, 11, 15, 16, 20, 21, 22, 23, 24, 25}
CENTRO = {7, 8, 9, 12, 13, 14, 17, 18, 19}
CRUZ = {3, 8, 11, 12, 13, 14, 15, 18, 23}
X_SET = {1, 5, 7, 9, 13, 17, 19, 21, 25}
PRIMOS = {2, 3, 5, 7, 11, 13, 17, 19, 23}
FIBONACCI = {1, 2, 3, 5, 8, 13, 21}
ALL_NUMBERS = set(range(1, 26))


def ensure_data() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not RESULTS_PATH.exists():
        RESULTS_PATH.write_text(json.dumps({"lotofacil": []}, indent=2), encoding="utf-8")
    if not BUFFER_PATH.exists():
        BUFFER_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")
    if not PLAYED_PATH.exists():
        PLAYED_PATH.write_text(json.dumps([], indent=2), encoding="utf-8")
    if not GROUPS_PATH.exists():
        GROUPS_PATH.write_text(
            json.dumps(
                {
                    "default": {
                        "filters": ["m9", "p5", "f4", "s180-220", "e7", "r8", "a15"],
                        "quantity": 12,
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_draw() -> list[int]:
    resp = requests.get(API_LOTOFACIL, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return sorted(int(x) for x in data.get("dezenas", []))


def sync_latest_result() -> str:
    db = load_json(RESULTS_PATH)
    try:
        draw = latest_draw()
    except Exception as exc:
        return f"falha sync: {exc}"
    current = [tuple(sorted(x)) for x in db.get("lotofacil", [])]
    if tuple(draw) not in current:
        db.setdefault("lotofacil", []).append(draw)
        save_json(RESULTS_PATH, db)
        return "novo resultado salvo"
    return "sem alterações"


def parse_filter_token(token: str):
    k = token[0].lower()
    v = token[1:]
    if k in {"m", "c", "p", "f", "x", "+", "e", "r", "a"}:
        return k, int(v)
    if k == "s":
        if "-" in v:
            a, b = v.split("-", 1)
            return k, (int(a), int(b))
        return k, int(v)
    return k, v


def count_in(game: tuple[int, ...], group: set[int]) -> int:
    return sum(1 for n in game if n in group)


def previous_draw() -> set[int]:
    draws = load_json(RESULTS_PATH).get("lotofacil", [])
    return set(draws[-1]) if draws else set()


def gaps_counter() -> Counter:
    draws = load_json(RESULTS_PATH).get("lotofacil", [])
    gap = Counter({n: 999 for n in range(1, 26)})
    for n in range(1, 26):
        for i, draw in enumerate(reversed(draws), start=1):
            if n in draw:
                gap[n] = i
                break
    return gap


def build_checks(tokens: list[str]):
    last = previous_draw()
    gaps = gaps_counter()
    cyc = cycle_missing_set()
    checks = []
    for t in tokens:
        k, v = parse_filter_token(t)
        if k == "m":
            checks.append(lambda g, v=v: count_in(g, MOLDURA) == v)
        elif k == "c":
            checks.append(lambda g, v=v: count_in(g, CENTRO) == v)
        elif k == "x":
            checks.append(lambda g, v=v: count_in(g, X_SET) == v)
        elif k == "+":
            checks.append(lambda g, v=v: count_in(g, CRUZ) == v)
        elif k == "p":
            checks.append(lambda g, v=v: count_in(g, PRIMOS) == v)
        elif k == "f":
            checks.append(lambda g, v=v: count_in(g, FIBONACCI) == v)
        elif k == "e":
            checks.append(lambda g, v=v: sum(1 for n in g if n % 2 == 0) == v)
        elif k == "s":
            if isinstance(v, tuple):
                checks.append(lambda g, a=v[0], b=v[1]: a <= sum(g) <= b)
            else:
                checks.append(lambda g, v=v: sum(g) == v)
        elif k == "r":
            checks.append(lambda g, v=v: len(set(g) & last) <= v)
        elif k == "a":
            checks.append(lambda g, v=v: sum(1 for n in g if gaps[n] >= 8) >= v)
        elif k == "y":
            checks.append(lambda g, cyc=cyc: len(set(g) & cyc) >= 6)
    return checks


def cycle_missing_set() -> set[int]:
    draws = load_json(RESULTS_PATH).get("lotofacil", [])
    seen = set()
    for d in reversed(draws):
        seen.update(d)
        if len(seen) == 25:
            break
    return ALL_NUMBERS - seen


def generate_block(filters: list[str], quantity: int, optimize: bool = True):
    checks = build_checks(filters)
    draws = load_json(RESULTS_PATH).get("lotofacil", [])
    history = {tuple(sorted(d)) for d in draws}
    played = load_json(PLAYED_PATH)
    historic_games = {tuple(g) for b in played for g in b.get("games", [])}

    found: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    attempts = 0
    while len(found) < quantity and attempts < quantity * 6000:
        attempts += 1
        g = tuple(sorted(random.sample(range(1, 26), 15)))
        if g in seen or g in history or g in historic_games:
            continue
        if all(chk(g) for chk in checks):
            seen.add(g)
            found.append(g)

    if optimize:
        found = optimize_games(found)
    return found[:quantity]


def optimize_games(games: list[tuple[int, ...]], threshold: float = 0.75):
    out: list[tuple[int, ...]] = []
    for g in games:
        sg = set(g)
        if all(len(sg & set(k)) / len(sg | set(k)) < threshold for k in out):
            out.append(g)
    return out


def new_id(blocks: list[dict]) -> int:
    return max((b.get("id", 0) for b in blocks), default=0) + 1


def create_played_block(filters: list[str], quantity: int = 12) -> dict:
    games = generate_block(filters, quantity, optimize=True)
    played = load_json(PLAYED_PATH)
    block = {
        "id": new_id(played),
        "created_at": now_utc(),
        "filters": filters,
        "games": [list(g) for g in games],
        "checked": False,
        "awards": {"11": 0, "12": 0, "13": 0, "14": 0, "15": 0},
        "best_hit": 0,
    }
    played.append(block)
    save_json(PLAYED_PATH, played)
    return block


def validate_pending_blocks() -> str:
    played = load_json(PLAYED_PATH)
    if not played:
        return "sem blocos"
    draws = load_json(RESULTS_PATH).get("lotofacil", [])
    if not draws:
        return "sem resultados"
    latest = set(draws[-1])
    changed = False
    for b in played:
        if b.get("checked"):
            continue
        awards = {"11": 0, "12": 0, "13": 0, "14": 0, "15": 0}
        best = 0
        for g in b.get("games", []):
            hit = len(set(g) & latest)
            best = max(best, hit)
            if str(hit) in awards:
                awards[str(hit)] += 1
        b["checked"] = True
        b["checked_at"] = now_utc()
        b["awards"] = awards
        b["best_hit"] = best
        changed = True
    if changed:
        save_json(PLAYED_PATH, played)
    return "blocos validados"


def recent_kpis(days: int = 30) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    played = load_json(PLAYED_PATH)
    considered = []
    for b in played:
        created = b.get("created_at")
        if not created:
            continue
        dt = datetime.fromisoformat(created)
        if dt >= cutoff:
            considered.append(b)
    total_games = sum(len(b.get("games", [])) for b in considered)
    hit14 = sum(b.get("awards", {}).get("14", 0) for b in considered)
    hit15 = sum(b.get("awards", {}).get("15", 0) for b in considered)
    avg_best = round(sum(b.get("best_hit", 0) for b in considered) / len(considered), 2) if considered else 0
    return {
        "blocks_30d": len(considered),
        "games_30d": total_games,
        "premios_14": hit14,
        "premios_15": hit15,
        "media_melhor_acerto": avg_best,
    }


def today_blocks() -> list[dict]:
    played = load_json(PLAYED_PATH)
    today = datetime.now(timezone.utc).date()
    out = []
    for b in played:
        if "created_at" not in b:
            continue
        if datetime.fromisoformat(b["created_at"]).date() == today:
            out.append(b)
    return out[-3:]


@app.route("/")
def dashboard():
    kpis = recent_kpis(30)
    return render_template("dashboard.html", kpis=kpis)


@app.route("/hoje")
def hoje():
    blocks = today_blocks()
    return render_template(
        "hoje.html",
        blocks=blocks,
        primos=PRIMOS,
        moldura=MOLDURA,
        fibonacci=FIBONACCI,
    )


@app.route("/historico")
def historico():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 10
    played = list(reversed(load_json(PLAYED_PATH)))
    start = (page - 1) * per_page
    end = start + per_page
    total_pages = max(1, (len(played) + per_page - 1) // per_page)
    return render_template("historico.html", blocks=played[start:end], page=page, total_pages=total_pages)


@app.route("/estrategia", methods=["GET", "POST"])
def estrategia():
    msg = None
    if request.method == "POST":
        raw = request.form.get("json_content", "{}")
        try:
            parsed = json.loads(raw)
            save_json(GROUPS_PATH, parsed)
            msg = "Estratégia atualizada com sucesso"
        except Exception as exc:
            msg = f"Erro ao salvar JSON: {exc}"
    content = GROUPS_PATH.read_text(encoding="utf-8")
    return render_template("estrategia.html", json_content=content, msg=msg)


@app.route("/forcar-geracao", methods=["POST"])
def forcar_geracao():
    groups = load_json(GROUPS_PATH)
    base = groups.get("default", {"filters": ["m9", "p5", "s180-220"], "quantity": 12})
    block = create_played_block(base.get("filters", []), int(base.get("quantity", 12)))
    return redirect(url_for("hoje", block=block["id"]))


def scheduler_job():
    sync_latest_result()
    validate_pending_blocks()


def bootstrap() -> None:
    ensure_data()
    sync_latest_result()
    validate_pending_blocks()


scheduler = BackgroundScheduler()
scheduler.add_job(scheduler_job, "interval", hours=6, id="lottery-refresh", replace_existing=True)


if __name__ == "__main__":
    bootstrap()
    scheduler.start()
    app.run(host="127.0.0.1", port=5000, debug=False)
