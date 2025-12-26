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
    GAMES_ROOT = Path(__file__).parent / "games"

GAMES_ROOT.mkdir(parents=True, exist_ok=True)

# ----------- NEW: board size 12 × 12 -----------------------------------
BOARD_SIZE = 12

# Ship definitions
SHIP_SIZES = {"A": 5, "B": 4, "S": 3, "D": 3, "P": 2}   # Aircraft, Battleship, Sub, Destroyer, Patrol

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------
def _rand_id():
    """Human‑readable random word (6 lower‑case letters)."""
    return "".join(random.choice(string.ascii_lowercase) for _ in range(6))


def _empty_board():
    return [["~"] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def _game_path(game_id: str) -> Path:
    return GAMES_ROOT / f"{game_id}.json"


def _save_game(game_id, data):
    _game_path(game_id).write_text(json.dumps(data))


def _load_game(game_id):
    p = _game_path(game_id)
    if not p.is_file():
        abort(404, description="Game not found")
    return json.loads(p.read_text())


def _coord_from_rc(row: int, col: int) -> str:
    """Convert numeric row/col to a Battleship coordinate string, e.g. (0,0) → 'A1'."""
    return f"{chr(ord('A') + col)}{row + 1}"


def _place_ships_randomly(board, blocked_coords=None):
    """
    Randomly place ships on *board*.

    *blocked_coords* – a set of coordinate strings (e.g. {'A1','B2'})
    that must **not** be used for any ship cell.  This is used when the
    second player joins, to avoid overlapping the first player's ships.
    """
    blocked_coords = blocked_coords or set()

    for ship, size in SHIP_SIZES.items():
        placed = False
        while not placed:
            horiz = random.choice([True, False])
            if horiz:
                r = random.randint(0, BOARD_SIZE - 1)
                c = random.randint(0, BOARD_SIZE - size)
                cells = [(r, c + i) for i in range(size)]
            else:
                r = random.randint(0, BOARD_SIZE - size)
                c = random.randint(0, BOARD_SIZE - 1)
                cells = [(r + i, c) for i in range(size)]

            # 1️⃣  Ensure none of the candidate cells overlap existing ships
            # 2️⃣  Ensure none of the candidate cells are in *blocked_coords*
            if any(board[x][y] != "~" for x, y in cells):
                continue
            if any(_coord_from_rc(x, y) in blocked_coords for x, y in cells):
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
        "created": uuid.uuid4().hex,
        "winner": None,              # will hold the winning token when the game ends
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

    # ------------------------------------------------------------------
    # If a player is already in the game, collect all of *their* ship
    # coordinates so we can forbid them for the newcomer.
    # ------------------------------------------------------------------
    blocked = set()
    if game["players"]:                     # there is already one player
        existing_board = next(iter(game["players"].values()))["board"]
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if existing_board[r][c] != "~":
                    blocked.add(_coord_from_rc(r, c))

    # Place ships respecting the blocked set (may be empty for the first player)
    _place_ships_randomly(board, blocked_coords=blocked)

    game["players"][token] = {
        "board": board,
        "hits": [],      # opponent's successful shots on this board
        "misses": []     # opponent's missed shots on this board
    }

    # First player to join gets the first turn
    if game["turn"] is None:
        game["turn"] = token

    _save_game(game_id, game)
    return jsonify({"token": token}), 200


@app.route("/games/<game_id>/state", methods=["GET"])
def get_state(game_id):
    """
    Return the public game state **plus**:
      * the caller’s private board (if a valid token is supplied)
      * a per‑player list ``sunk_ships`` – the enemy ships that this
        player has already sunk (derived from their hit list).
      * the existing ``winner`` field.
    """
    game = _load_game(game_id)

    # -----------------------------------------------------------------
    # Public part – hits/misses for both players, whose turn it is.
    # -----------------------------------------------------------------
    public_players = {}
    for token, pdata in game["players"].items():
        public_players[token] = {
            "hits":   pdata["hits"],
            "misses": pdata["misses"]
        }

    # -----------------------------------------------------------------
    # Compute, for each player, which enemy ships they have already sunk.
    # -----------------------------------------------------------------
    sunk_info = {}   # token → list of ship letters that the *opponent* has lost
    for token in game["players"]:
        # Find the opponent token (the other player)
        opponent_token = next(t for t in game["players"] if t != token)
        opponent_board = game["players"][opponent_token]["board"]
        hits = set(game["players"][token]["hits"])

        sunk_this_player = []
        for ship_letter, size in SHIP_SIZES.items():
            # Count how many cells of this ship type are present in the hit list
            hit_count = sum(
                1
                for r in range(BOARD_SIZE)
                for c in range(BOARD_SIZE)
                if opponent_board[r][c] == ship_letter
                and _coord_from_rc(r, c) in hits
            )
            if hit_count == size:
                sunk_this_player.append(ship_letter)

        sunk_info[token] = sunk_this_player

    # -----------------------------------------------------------------
    # Private board – only for the caller (if they passed a valid token)
    # -----------------------------------------------------------------
    requester_token = request.args.get("token")
    private_board = None
    if requester_token and requester_token in game["players"]:
        private_board = game["players"][requester_token]["board"]

    # -----------------------------------------------------------------
    # Assemble the full JSON response
    # -----------------------------------------------------------------
    response = {
        "id":            game_id,
        "turn":          game["turn"],
        "players":       public_players,
        "private_board": private_board,          # may be None for unauthenticated callers
        "sunk_ships":    sunk_info,              # per‑player sunk‑enemy‑ship list
        "winner":        game.get("winner")      # unchanged from earlier version
    }
    return jsonify(response), 200


@app.route("/games/<game_id>/move", methods=["POST"])
def make_move(game_id):
    """
    Fire a shot at the opponent.
    Expected JSON body: {"token":"…","coord":"B5"}
    Returns JSON with result, hit flag, and optional sunk info.
    """
    payload = request.get_json(force=True)
    token = payload.get("token")
    coord = payload.get("coord")

    if not token or not coord:
        abort(400, description="Missing token or coord")

    game = _load_game(game_id)

    if token not in game["players"]:
        abort(403, description="Invalid token for this game")

    if game["turn"] != token:
        abort(400, description="Not your turn")

    if len(game["players"]) < 2:
        abort(400, description="Opponent has not joined the game yet")

    # ------------------------------------------------------------------
    # Locate opponent (the other token)
    # ------------------------------------------------------------------
    opponent_token = next(t for t in game["players"] if t != token)
    opponent = game["players"][opponent_token]

    # ------------------------------------------------------------------
    # Translate coordinate (e.g. "B5")
    # ------------------------------------------------------------------
    try:
        col = ord(coord[0].upper()) - ord("A")
        row = int(coord[1:]) - 1
    except Exception:
        abort(400, description="Coordinate format invalid (expected LetterNumber, e.g. B5)")

    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        abort(400, description="Coordinate out of bounds")

    cell = opponent["board"][row][col]
    hit = cell != "~"

    if hit:
        opponent["hits"].append(coord.upper())
        result = "hit"
    else:
        opponent["misses"].append(coord.upper())
        result = "miss"

    # ------------------------------------------------------------------
    # Check for a sunk ship (optional, nice UX)
    # ------------------------------------------------------------------
    sunk_letter = None
    sunk_name = None
    if hit:
        ship_letter = cell
        # Count how many hits we have on this particular ship type
        hits_on_this_ship = sum(
            1 for c in opponent["hits"]
            if _coord_from_rc(int(c[1:]) - 1, ord(c[0].upper()) - ord("A")) == ship_letter
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

    # ------------------------------------------------------------------
    # Switch turn and persist
    # ------------------------------------------------------------------
    game["turn"] = opponent_token

    # --------------------------------------------------------------
    # WIN DETECTION – if the opponent has no remaining ships, declare winner
    # --------------------------------------------------------------
    if sunk_letter:
        # After this hit we may have sunk the *last* ship of the opponent.
        # Verify that **every** ship type of the opponent is fully hit.
        all_sunk = True
        for s_letter, s_size in SHIP_SIZES.items():
            hits_on_type = sum(
                1 for c in opponent["hits"]
                if _coord_from_rc(int(c[1:]) - 1, ord(c[0].upper()) - ord("A")) == s_letter
            )
            if hits_on_type < s_size:
                all_sunk = False
                break
        if all_sunk:
            game["winner"] = token   # the player who just moved wins

    _save_game(game_id, game)

    return jsonify({
        "result": result,
        "hit": hit,
        "sunk": sunk_letter,
        "sunk_name": sunk_name,
    }), 200


# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Run with: FLASK_APP=app.py flask run --host=0.0.0.0 --port=5000
    app.run(host="0.0.0.0", port=5000, debug=True)
