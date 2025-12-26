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
    """
    Public state plus (optionally) the private board of the requester.

    Query parameters:
        token (optional) – the player's secret token.
    """
    game = _load_game(game_id)

    # ------------------------------------------------------------------
    # Gather the public portion (hits/misses + whose turn)
    # ------------------------------------------------------------------
    public_players = {}
    for token, pdata in game["players"].items():
        public_players[token] = {
            "hits":   pdata["hits"],
            "misses": pdata["misses"]
        }

    # ------------------------------------------------------------------
    # If the caller supplies a valid token, also attach THEIR board.
    # This board is **private** – it is never sent to the opponent.
    # ------------------------------------------------------------------
    requester_token = request.args.get("token")
    private_board = None
    if requester_token and requester_token in game["players"]:
        private_board = game["players"][requester_token]["board"]

    response = {
        "id":    game_id,
        "turn":  game["turn"],
        "players": public_players,
        # Include the private board only for the owner of the token.
        "private_board": private_board
    }
    return jsonify(response), 200

@app.route("/games/<game_id>/move", methods=["POST"])
def make_move(game_id):
    """
    Fire a shot at the opponent.

    Expected JSON body:
        {
            "token": "<player‑token>",
            "coord": "B5"
        }

    Returns (JSON):
        {
            "result": "hit" | "miss",
            "hit": true | false,
            "sunk": "<letter>" | null,          # optional – ship that was sunk
            "sunk_name": "<friendly name>" | null
        }
    """
    # -----------------------------------------------------------------
    # 1️⃣ Validate payload
    # -----------------------------------------------------------------
    payload = request.get_json(force=True)
    token   = payload.get("token")
    coord   = payload.get("coord")          # e.g. "B5"

    if not token or not coord:
        abort(400, description="Missing 'token' or 'coord' in request body")

    # -----------------------------------------------------------------
    # 2️⃣ Load the game and basic sanity checks
    # -----------------------------------------------------------------
    game = _load_game(game_id)

    if token not in game["players"]:
        abort(403, description="Invalid token for this game")

    if game["turn"] != token:
        abort(400, description="Not your turn")

    # -----------------------------------------------------------------
    # 3️⃣ **Make sure an opponent exists** before we try to pick one.
    # -----------------------------------------------------------------
    if len(game["players"]) < 2:
        abort(400, description="Opponent has not joined the game yet")

    # -----------------------------------------------------------------
    # 4️⃣ Locate opponent token (the one that is NOT the caller)
    # -----------------------------------------------------------------
    opponent_token = next(t for t in game["players"] if t != token)
    opponent = game["players"][opponent_token]

    # -----------------------------------------------------------------
    # 5️⃣ Translate coordinate (e.g. "B5")
    # -----------------------------------------------------------------
    try:
        col = ord(coord[0].upper()) - ord('A')
        row = int(coord[1:]) - 1
    except Exception:
        abort(400, description="Coordinate format invalid (expected LetterNumber, e.g. B5)")

    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        abort(400, description="Coordinate out of bounds")

    # -----------------------------------------------------------------
    # 6️⃣ Resolve hit / miss
    # -----------------------------------------------------------------
    cell = opponent["board"][row][col]
    hit = cell != "~"

    if hit:
        opponent["hits"].append(coord.upper())
        result = "hit"
    else:
        opponent["misses"].append(coord.upper())
        result = "miss"

    # -----------------------------------------------------------------
    # 7️⃣ **Check for a sunk ship** (optional, but nice UX)
    # -----------------------------------------------------------------
    sunk_letter = None
    sunk_name   = None
    if hit:
        # Count how many cells of this ship have been hit so far
        ship_letter = cell
        hits_on_this_ship = sum(
            1 for c in opponent["hits"] if _coord_to_letter(c) == ship_letter
        )
        if hits_on_this_ship == SHIP_SIZES.get(ship_letter, 0):
            sunk_letter = ship_letter
            ship_names = {
                "A": "Aircraft Carrier",
                "B": "Battleship",
                "S": "Submarine",
                "D": "Destroyer",
                "P": "Patrol Boat",
            }
            sunk_name = ship_names.get(ship_letter, "Unknown Ship")

    # -----------------------------------------------------------------
    # 8️⃣ Switch turn and persist the updated game state
    # -----------------------------------------------------------------
    game["turn"] = opponent_token
    _save_game(game_id, game)

    # -----------------------------------------------------------------
    # 9️⃣ Return a well‑structured JSON response
    # -----------------------------------------------------------------
    response_payload = {
        "result": result,
        "hit": hit,
        "sunk": sunk_letter,
        "sunk_name": sunk_name,
    }
    return jsonify(response_payload), 200

def _coord_to_letter(coord: str) -> str:
    """
    Given a coordinate string like "B5", return the character that sits on the
    opponent's board at that position (e.g. "A", "B", "~").
    This function is only used inside `make_move` after we already have the
    opponent's board, so we read the current game file again to keep the
    implementation simple.
    """
    # Retrieve the most recent game (the file was already written by _save_game)
    # The game_id is available in the outer scope of `make_move`.
    # We'll pull it from Flask's request view_args.
    game_id = request.view_args["game_id"]
    game = _load_game(game_id)

    # Find the opponent token (the one that is NOT the caller)
    caller_token = request.get_json(silent=True).get("token")
    opponent_token = next(t for t in game["players"] if t != caller_token)
    opponent_board = game["players"][opponent_token]["board"]

    col = ord(coord[0].upper()) - ord("A")
    row = int(coord[1:]) - 1
    return opponent_board[row][col]
