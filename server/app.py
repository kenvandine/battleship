#!/usr/bin/env python3
"""
Flask REST API for async Battleship.

Games are persisted as JSON files inside:
    $SNAP_COMMON/games/<game_id>.json

If $SNAP_COMMON is not defined, the server falls back to a local
"./games" directory (useful for development).
"""

import os, json, uuid, random, string
from pathlib import Path
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

# ----------------------------------------------------------------------
# Determine where the JSON files will live
# ----------------------------------------------------------------------
SNAP_COMMON = os.getenv("SNAP_COMMON")
if SNAP_COMMON:
    GAMES_ROOT = Path(SNAP_COMMON) / "games"
else:
    # Development fallback – a sibling folder called "games"
    GAMES_ROOT = Path(__file__).parent / "games"

GAMES_ROOT.mkdir(parents=True, exist_ok=True)   # create if missing

BOARD_SIZE = 10
SHIP_SIZES = {"A":5, "B":4, "S":3, "D":3, "P":2}   # Aircraft, Battleship, Sub, Destroyer, Patrol

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------
def _rand_id():
    """Human‑readable random word (6 lower‑case letters)."""
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(6))

def _empty_board():
    return [["~"]*BOARD_SIZE for _ in range(BOARD_SIZE)]

def _game_path(game_id: str) -> Path:
    """Full path to the JSON file for a given game."""
    return GAMES_ROOT / f"{game_id}.json"

def _save_game(game_id, data):
    _game_path(game_id).write_text(json.dumps(data))

def _load_game(game_id):
    p = _game_path(game_id)
    if not p.is_file():
        abort(404, description="Game not found")
    return json.loads(p.read_text())

def _place_ships_randomly(board):
    """Naïve random placement – fine for a demo."""
    for ship, size in SHIP_SIZES.items():
        placed = False
        while not placed:
            horiz = random.choice([True, False])
            if horiz:
                r = random.randint(0, BOARD_SIZE-1)
                c = random.randint(0, BOARD_SIZE-size)
                cells = [(r, c+i) for i in range(size)]
            else:
                r = random.randint(0, BOARD_SIZE-size)
                c = random.randint(0, BOARD_SIZE-1)
                cells = [(r+i, c) for i in range(size)]

            if any(board[x][y] != "~" for x, y in cells):
                continue
            for x, y in cells:
                board[x][y] = ship
            placed = True

# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/games/start", methods=["POST"])
def start_game():
    game_id = _rand_id()
    game = {
        "id": game_id,
        "players": {},               # token → {"board":…, "hits": [], "misses": []}
        "turn": None,
        "created": uuid.uuid4().hex
    }
    _save_game(game_id, game)
    return jsonify({"game_id": game_id}), 201

@app.route("/games/<game_id>/join", methods=["POST"])
def join_game(game_id):
    game = _load_game(game_id)

    if len(game["players"]) >= 2:
        abort(400, description="Game already has two players")

    token = uuid.uuid4().hex
    board = _empty_board()
    _place_ships_randomly(board)

    game["players"][token] = {
        "board": board,
        "hits": [],
        "misses": []
    }

    if game["turn"] is None:
        game["turn"] = token

    _save_game(game_id, game)
    return jsonify({"token": token}), 200

@app.route("/games/<game_id>/state", methods=["GET"])
def get_state(game_id):
    game = _load_game(game_id)
    public_players = {}
    for token, pdata in game["players"].items():
        public_players[token] = {
            "hits": pdata["hits"],
            "misses": pdata["misses"]
        }
    return jsonify({
        "id": game_id,
        "turn": game["turn"],
        "players": public_players
    })

@app.route("/games/<game_id>/move", methods=["POST"])
def make_move(game_id):
    payload = request.get_json(force=True)
    token   = payload.get("token")
    coord   = payload.get("coord")          # e.g. "B5"

    if not token or not coord:
        abort(400, description="Missing token or coord")

    game = _load_game(game_id)

    if token not in game["players"]:
        abort(403, description="Invalid token for this game")

    if game["turn"] != token:
        abort(400, description="Not your turn")

    # Find opponent token
    opp_token = next(t for t in game["players"] if t != token)
    opp = game["players"][opp_token]

    # Translate coordinate
    col = ord(coord[0].upper()) - ord('A')
    row = int(coord[1:]) - 1
    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        abort(400, description="Coordinate out of bounds")

    cell = opp["board"][row][col]
