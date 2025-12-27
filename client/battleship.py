#!/usr/bin/env python3
"""
Command‑line Battleship client.

Commands
--------
battleship start                 → create a new game, store token locally
battleship join <game_id>        → join an existing game, store token locally
battleship status                → show current board, turn, sunk ships & win state
battleship fire <coord>          → fire at opponent (e.g. "E7")
battleship quit                  → forget the locally‑saved token
battleship help                  → show this help screen
"""

import sys, os, json, pathlib, requests
from urllib.parse import urljoin

# -----------------------------------------------------------------
# Server URL – read from the environment, ensure it ends with "/"
# -----------------------------------------------------------------
_raw_url = os.getenv(
    "SERVER_URL",
    "http://localhost:5000/"
)
SERVER_URL = _raw_url.rstrip("/") + "/"

# -----------------------------------------------------------------
# Local token storage (kept under $HOME/.battleship/current)
# -----------------------------------------------------------------
TOKEN_FILE = pathlib.Path.home() / ".battleship" / "current"

# -----------------------------------------------------------------
# Emoji palette
# -----------------------------------------------------------------
EMOJI = {
    "unknown": "❓",   # unseen / water
    "miss":    "⚪",   # our miss on opponent board
    "hit":     "💥",   # our hit on opponent board
    "ship":    "🚢",   # our own healthy ship segment
    "ship_hit":"🔥",   # our own ship segment that opponent has hit
}

# -----------------------------------------------------------------
# Board size – 12 × 12 as requested
# -----------------------------------------------------------------
BOARD_SIZE = 12

# -----------------------------------------------------------------
# Helper functions for token handling
# -----------------------------------------------------------------
def _ensure_dir():
    """Make sure the directory that holds the token file exists."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)


def _save_token(game_id, token):
    """Write the current game ID and token to $HOME/.battleship/current."""
    _ensure_dir()
    data = {"game_id": game_id, "token": token}
    TOKEN_FILE.write_text(json.dumps(data))


def _load_token():
    """Read the stored token file; return None if it does not exist."""
    if not TOKEN_FILE.is_file():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception:
        return None


def _clear_token():
    """Remove the stored token file (used by the `quit` command)."""
    if TOKEN_FILE.is_file():
        TOKEN_FILE.unlink()


# -----------------------------------------------------------------
# Low‑level API wrapper
# -----------------------------------------------------------------
def _api(path, method="GET", json_body=None):
    """Perform a request against the Battleship REST API."""
    url = urljoin(SERVER_URL, path)
    resp = requests.request(method, url, json=json_body)
    if not resp.ok:
        print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def _fetch_state(game_id, token):
    """
    Pull the game state from the server, passing our token so we receive
    our private board and the optional `winner` field.
    """
    url = f"{SERVER_URL}games/{game_id}/state?token={token}"
    resp = requests.get(url)
    if not resp.ok:
        print(f"Error fetching state: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


# -----------------------------------------------------------------
# Board rendering – works for a 12×12 board
# -----------------------------------------------------------------
def _print_board(state, my_token):
    """
    Render a 12×12 grid.

    Legend:
        🚢  – your ship segment (still afloat)
        🔥  – your ship segment that the opponent has hit
        💥  – a hit you scored on the opponent
        ⚪  – a miss you scored on the opponent
        ❓  – unknown / water
    """
    # Empty visual grid (all unknown)
    grid = [[EMOJI["unknown"] for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

    # Determine whether an opponent exists
    player_tokens = list(state["players"].keys())
    try:
        opponent_token = next(t for t in player_tokens if t != my_token)
        opponent_exists = True
    except StopIteration:
        opponent_token = None
        opponent_exists = False

    # Opponent‑side hits/misses (only if opponent has joined)
    if opponent_exists:
        opp_data = state["players"][opponent_token]

        for coord in opp_data["hits"]:
            col = ord(coord[0]) - ord('A')
            row = int(coord[1:]) - 1
            grid[row][col] = EMOJI["hit"]          # 💥

        for coord in opp_data["misses"]:
            col = ord(coord[0]) - ord('A')
            row = int(coord[1:]) - 1
            grid[row][col] = EMOJI["miss"]         # ⚪

    # Overlay YOUR own ships and mark any hits the opponent already made
    private_board = state.get("private_board")
    if private_board:
        opponent_hits = set()
        if opponent_exists:
            opponent_hits = set(state["players"][my_token]["hits"])

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cell = private_board[r][c]
                if cell != "~":                     # there is a ship here
                    coord = f"{chr(ord('A')+c)}{r+1}"
                    if coord in opponent_hits:
                        grid[r][c] = EMOJI["ship_hit"]   # 🔥
                    else:
                        if grid[r][c] == EMOJI["unknown"]:
                            grid[r][c] = EMOJI["ship"]   # 🚢

    # Header line (aligned with cells)
    col_header = "   " + " ".join(chr(ord('A') + i) + " " for i in range(BOARD_SIZE))
    print(col_header.rstrip())

    # Rows (right‑aligned row numbers)
    for r in range(BOARD_SIZE):
        row_label = f"{r+1:2d}"
        row_cells = " ".join(grid[r]) + " "
        print(f"{row_label} {row_cells.rstrip()}")

    # If opponent hasn't joined yet, show a friendly note.
    if not opponent_exists:
        print("\n🕒 Waiting for the opponent to join this game...")


# -----------------------------------------------------------------
# Helper: list which of *your* ships have been hit (used in status)
# -----------------------------------------------------------------
def _list_my_damaged_ships(state, my_token):
    """
    Return a list of ship letters that have at least one hit on them.
    """
    private_board = state.get("private_board")
    if not private_board:
        return []

    # Opponent's hits against us
    opponent_hits = set(state["players"][my_token]["hits"])
    damaged = set()
    for coord in opponent_hits:
        col = ord(coord[0]) - ord('A')
        row = int(coord[1:]) - 1
        ship_letter = private_board[row][col]
        if ship_letter != "~":
            damaged.add(ship_letter)

    # Friendly names (same mapping used on the server)
    names = {
        "A": "Aircraft Carrier",
        "B": "Battleship",
        "S": "Submarine",
        "D": "Destroyer",
        "P": "Patrol Boat",
    }
    return [names.get(l, l) for l in sorted(damaged)]


# -----------------------------------------------------------------
# Helper: list which opponent ships you have already sunk
# -----------------------------------------------------------------
def _list_opponent_sunk_ships(state, my_token):
    """
    Return a list of ship letters that you have already sunk.
    The server does not keep a cumulative list, so we infer it from
    the opponent's board: any ship type for which *all* its cells are
    present in our hit list is considered sunk.
    """
    # Find opponent token
    player_tokens = list(state["players"].keys())
    try:
        opponent_token = next(t for t in player_tokens if t != my_token)
    except StopIteration:
        return []   # no opponent yet

    # We need the opponent's *private* board – unfortunately the public
    # endpoint does not expose it.  Instead we infer sunk ships from the
    # hit list we have on the opponent: when we have hit enough cells
    # equal to the ship's size, we know it is sunk.
    #
    # The server already returns `sunk`/`sunk_name` for the *last* move,
    # but here we want the cumulative list.  We'll reconstruct it by
    # counting hits per ship type.
    #
    # NOTE: This works only because ships never overlap and each ship
    # type appears at most once per player.
    #
    # First, fetch the opponent's board via a *private* request.
    # The client already knows its own token, but not the opponent's.
    # The server does not expose the opponent's board publicly, so we
    # cannot reliably compute the full list without an extra endpoint.
    # For simplicity, we'll rely on the fact that the server returns
    # `sunk` for each move and store those in a local cache file.
    #
    # To avoid persisting extra state, we will just return the ships
    # that were reported as sunk in the most recent move (if any).
    # This keeps the client simple and matches the server's design.
    #
    # If you want a full cumulative list you could extend the server
    # to include a `sunk_ships` array in the state response.
    return []   # placeholder – no cumulative data available


# -----------------------------------------------------------------
# Command implementations
# -----------------------------------------------------------------
def cmd_start(_):
    """Create a new game and automatically join as the first player."""
    data = _api("games/start", "POST")
    game_id = data["game_id"]
    # Join as the first player
    join = _api(f"games/{game_id}/join", "POST")
    token = join["token"]
    _save_token(game_id, token)
    print(f"New game created! ID = {game_id}")
    print(f"Your token is stored at {TOKEN_FILE}")


def cmd_join(args):
    """Join an existing game (requires a game ID)."""
    if len(args) != 1:
        print("Usage: battleship join <GAME_ID>")
        sys.exit(1)
    game_id = args[0]
    join = _api(f"games/{game_id}/join", "POST")
    token = join["token"]
    _save_token(game_id, token)
    print(f"Joined game {game_id}. Token saved to {TOKEN_FILE}")


def cmd_status(_):
    """
    Show the board, turn information, which of *your* ships have been hit,
    and which opponent ships you have already sunk.  Also prints the win/
    loss message if the game is over.
    """
    cur = _load_token()
    if not cur:
        print("No active game. Use 'battleship start' or 'battleship join <id>'.")
        return

    state = _fetch_state(cur["game_id"], cur["token"])

    print(f"Game ID: {cur['game_id']}")
    print(f"Turn: {'you' if state['turn'] == cur['token'] else 'opponent'}")

    winner = state.get("winner")
    if winner:
        if winner == cur["token"]:
            print("\n🏆  You have WON the game!")
        else:
            print("\n💀  You have LOST the game.")
        # Still render the final board for reference.
    else:
        print("\nGame in progress…")

    # -----------------------------------------------------------------
    # Render the board (includes your own ships)
    # -----------------------------------------------------------------
    _print_board(state, cur["token"])

    # -----------------------------------------------------------------
    # List which of *your* ships have been hit
    # -----------------------------------------------------------------
    damaged = _list_my_damaged_ships(state, cur["token"])
    if damaged:
        print("\nYour ships that have been hit:", ", ".join(damaged))
    else:
        print("\nAll your ships are still intact.")

    opponent_sunk_letters = (
        state.get("sunk_ships", {})
            .get(cur["token"], [])
        or state.get("players", {})
            .get(cur["token"], {})
            .get("sunk_ships", [])
    )

    if opponent_sunk_letters:
        ship_names = {
            "A": "Aircraft Carrier",
            "B": "Battleship",
            "S": "Submarine",
            "D": "Destroyer",
            "P": "Patrol Boat",
        }
        opponent_sunk_names = [ship_names.get(l, l) for l in opponent_sunk_letters]
        print("\nOpponent ships you have sunk:", ", ".join(opponent_sunk_names))
    else:
        print("\nYou have not sunk any opponent ships yet.")


def cmd_fire(args):
    """Fire a shot at the opponent."""
    if len(args) != 1:
        print("Usage: battleship fire <COORD>")
        sys.exit(1)

    coord = args[0].upper()
    cur = _load_token()
    if not cur:
        print("No active game.")
        sys.exit(1)

    # Verify it's our turn first
    state = _fetch_state(cur["game_id"], cur["token"])
    if state["turn"] != cur["token"]:
        print("It's not your turn yet.")
        return

    payload = {"token": cur["token"], "coord": coord}
    resp = requests.post(f"{SERVER_URL}games/{cur['game_id']}/move", json=payload)
    if not resp.ok:
        print(f"Move failed: {resp.text}")
        return

    result = resp.json()
    print(f"You fired at {coord}: {result['result'].upper()}")

    # Did we sink a ship?
    if result.get("sunk"):
        sunk_name = result.get("sunk_name") or "a ship"
        print(f"🎉 You SUNK the opponent's {sunk_name}! 🎉")

    # Refresh and display the updated board
    new_state = _fetch_state(cur["game_id"], cur["token"])
    _print_board(new_state, cur["token"])


def cmd_quit(_):
    """Forget the locally stored token (useful to switch games)."""
    _clear_token()
    print("Current game cleared from local storage.")


def cmd_help(_):
    """Display a quick reference for all commands and the emoji legend."""
    commands_desc = [
        ("start",   "Create a brand‑new game and store the token locally."),
        ("join ID", "Join an existing game identified by <ID>. Saves its token."),
        ("status",  "Show the board, turn, which of your ships are hit, and win state."),
        ("fire XY", "Fire a shot at coordinate XY (e.g. B5). Must be your turn."),
        ("quit",    "Forget the locally‑saved token – useful if you want to switch games."),
        ("help",    "Show this help screen."),
    ]

    print("\n=== Battleship – command reference ===\n")
    for cmd, desc in commands_desc:
        print(f"  {cmd:<12} {desc}")

    legend = [
        ("🚢", "Your ship segment (still afloat)"),
        ("🔥", "Your ship segment that the opponent has hit"),
        ("💥", "A hit you scored on the opponent"),
        ("⚪", "A miss you scored on the opponent"),
        ("❓", "Unknown / water (no information yet)"),
    ]

    print("\n=== Emoji legend ===\n")
    for emoji, meaning in legend:
        print(f"  {emoji}  – {meaning}")

    print("\nTip: Run `battleship help` anytime to see this again.\n")


def main():
    if len(sys.argv) < 2:
        cmd_help(None)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "start":  cmd_start,
        "join":   cmd_join,
        "status": cmd_status,
        "fire":   cmd_fire,
        "quit":   cmd_quit,
        "help":   cmd_help,
    }

    if cmd not in commands:
        print(f"Unknown command '{cmd}'. Available: {', '.join(commands)}")
        sys.exit(1)

    commands[cmd](args)


if __name__ == "__main__":
    main()
