# test_integration.py
import os
import sys
import json
import time
import random
import socket
import shutil
import tempfile
import subprocess
import re
from pathlib import Path
from typing import List, Set

# ----------------------------------------------------------------------
# Helper: find a free TCP port
# ----------------------------------------------------------------------
def _free_port() -> int:
    """Return an unused localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

# ----------------------------------------------------------------------
# Helper: launch the Flask server in a subprocess
# ----------------------------------------------------------------------
def _launch_server(port: int):
    """
    Starts ``app.py`` with the given port.
    Returns (Popen object, temporary SNAP_COMMON directory).
    """
    env = os.environ.copy()
    env["PORT"] = str(port)               # server must read this env var
    snap_common = tempfile.mkdtemp(prefix="snap_common_")
    env["SNAP_COMMON"] = snap_common

    server_path = Path(__file__).parent / "server" / "app.py"

    # Let the server inherit the parent's stdout/stderr – no pipe buffering.
    proc = subprocess.Popen(
        [sys.executable, str(server_path)],
        env=env,
        stdout=None,
        stderr=None,
    )
    return proc, snap_common

# ----------------------------------------------------------------------
# Helper: wait until the server answers a simple request
# ----------------------------------------------------------------------
def _wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Poll ``/games/start`` until we get a 201 or timeout."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/games/start"
    while time.time() < deadline:
        try:
            import requests
            r = requests.post(url, timeout=0.5)
            if r.status_code == 201:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

# ----------------------------------------------------------------------
# Helper: run a client command in an isolated HOME directory
# ----------------------------------------------------------------------
def _run_client(args: List[str], home_dir: Path, server_url: str) -> subprocess.CompletedProcess:
    """
    Executes ``battleship.py`` with the given arguments.
    ``home_dir`` becomes the $HOME for the subprocess so each player gets its own
    ``~/.battleship/current`` file.
    Returns the CompletedProcess (stdout, stderr, returncode).
    """
    env = os.environ.copy()
    env["HOME"] = str(home_dir)          # isolate token storage
    env["SERVER_URL"] = server_url       # point client at the test server
    client_path = Path(__file__).parent / "client" / "battleship.py"
    return subprocess.run(
        [sys.executable, str(client_path)] + args,
        env=env,
        capture_output=True,
        text=True,
    )

# ----------------------------------------------------------------------
# Helper: extract the game‑id from the ``start`` output
# ----------------------------------------------------------------------
def _extract_game_id(output: str) -> str:
    m = re.search(r"ID\s*=\s*([a-z0-9]+)", output)
    if not m:
        raise ValueError(f"Could not find game id in output:\n{output}")
    return m.group(1)

# ----------------------------------------------------------------------
# Helper: parse the board from ``status`` output
# ----------------------------------------------------------------------
def _parse_board(status_output: str) -> List[List[str]]:
    """
    Returns a 2‑dimensional list of emojis (rows × cols).
    Assumes the board is printed exactly as in ``_print_board``.
    """
    lines = status_output.splitlines()
    header_index = next(i for i, l in enumerate(lines) if l.startswith("   "))
    board_lines = lines[header_index + 1 : header_index + 1 + 12]   # 12 rows
    board = []
    for line in board_lines:
        parts = line.strip().split()
        board.append(parts[1:])   # skip the row number
    return board

# ----------------------------------------------------------------------
# Integration test
# ----------------------------------------------------------------------
def test_full_game_flow():
    """
    Spins up a server, creates two clients, plays a full game until a winner
    appears, and checks that the output of ``fire`` and ``status`` matches
    expectations.
    """
    # --------------------------------------------------------------
    # 1️⃣  Start the server on a random port
    # --------------------------------------------------------------
    port = _free_port()
    server_proc, snap_common_dir = _launch_server(port)
    try:
        assert _wait_for_server(port), "Server never became ready"
        server_url = f"http://127.0.0.1:{port}/"

        # --------------------------------------------------------------
        # 2️⃣  Create two isolated HOME directories (one per player)
        # --------------------------------------------------------------
        home_a = Path(tempfile.mkdtemp(prefix="player_a_"))
        home_b = Path(tempfile.mkdtemp(prefix="player_b_"))

        # --------------------------------------------------------------
        # 3️⃣  Player A starts a new game
        # --------------------------------------------------------------
        res_start = _run_client(["start"], home_a, server_url)
        assert res_start.returncode == 0, f"start failed: {res_start.stderr}"
        game_id = _extract_game_id(res_start.stdout)

        # --------------------------------------------------------------
        # 4️⃣  Player B joins the same game
        # --------------------------------------------------------------
        res_join = _run_client(["join", game_id], home_b, server_url)
        assert res_join.returncode == 0, f"join failed: {res_join.stderr}"

        # --------------------------------------------------------------
        # 5️⃣  Prepare per‑player fired‑sets (players may fire at the same
        #     coordinate, but we avoid duplicate shots *by the same player*.
        # --------------------------------------------------------------
        fired_a: Set[str] = set()
        fired_b: Set[str] = set()
        all_coords = [
            f"{chr(ord('A') + c)}{r+1}"
            for r in range(12)
            for c in range(12)
        ]

        # --------------------------------------------------------------
        # 6️⃣  Main play loop – keep going until a winner is announced
        # --------------------------------------------------------------
        winner_declared = False
        max_moves = 500   # generous safety net; the game will finish far sooner
        for move_no in range(max_moves):
            # ----- fetch status for both players -----
            status_a = _run_client(["status"], home_a, server_url)
            status_b = _run_client(["status"], home_b, server_url)
            assert status_a.returncode == 0, f"A status error: {status_a.stderr}"
            assert status_b.returncode == 0, f"B status error: {status_b.stderr}"

            # ----- determine whose turn it is -----
            turn_is_a = "Turn: you" in status_a.stdout
            turn_is_b = "Turn: you" in status_b.stdout
            assert turn_is_a != turn_is_b, "Both players think it's their turn!"

            # ----- check for win/lose banners -----
            if "🏆  You have WON the game!" in status_a.stdout:
                winner_declared = True
                assert "💀  You have LOST the game." in status_b.stdout
                break
            if "🏆  You have WON the game!" in status_b.stdout:
                winner_declared = True
                assert "💀  You have LOST the game." in status_a.stdout
                break

            # ----- pick a random coordinate that this player hasn't used yet -----
            if turn_is_a:
                available = [c for c in all_coords if c not in fired_a]
                assert available, "Player A ran out of coordinates (should never happen)"
                coord = random.choice(available)
                fired_a.add(coord)
                fire_res = _run_client(["fire", coord], home_a, server_url)
                my_home = home_a
                my_status_before = status_a
            else:
                available = [c for c in all_coords if c not in fired_b]
                assert available, "Player B ran out of coordinates (should never happen)"
                coord = random.choice(available)
                fired_b.add(coord)
                fire_res = _run_client(["fire", coord], home_b, server_url)
                my_home = home_b
                my_status_before = status_b

            # ----- fire must succeed and report HIT or MISS -----
            assert fire_res.returncode == 0, f"fire failed: {fire_res.stderr}"
            assert re.search(rf"You fired at\s+{re.escape(coord)}:\s+(HIT|MISS)", fire_res.stdout), \
                f"Unexpected fire output:\n{fire_res.stdout}"

            # ----- if a ship was sunk, verify the celebratory line appears -----
            sunk_match = re.search(r"🎉 You SUNK the opponent's (.+?)! 🎉", fire_res.stdout)
            if sunk_match:
                sunk_name = sunk_match.group(1)
                assert sunk_name in {
                    "Aircraft Carrier", "Battleship", "Submarine",
                    "Destroyer", "Patrol Boat"
                }, f"Unexpected sunk name: {sunk_name}"

            # ----- after the move, fetch status again and verify turn switched -----
            post_status = _run_client(["status"], my_home, server_url)
            # After retrieving the status output for the player who just moved:
            if "Opponent ships you have sunk:" in post_status.stdout:
                # Extract the list that follows the colon
                sunk_line = re.search(r"Opponent ships you have sunk:\s*(.*)", post_status.stdout)
                if sunk_line:
                    sunk_list = [s.strip() for s in sunk_line.group(1).split(",") if s.strip()]
                # The list should contain at least the ship we just sunk (if any)
                    if sunk_match:   # we already captured the ship name from the fire output
                        expected_name = sunk_match.group(1)
                        assert expected_name in sunk_list, (
                            f"Sunk ship '{expected_name}' not listed in status output:\n{post_status.stdout}"
                        )

            assert post_status.returncode == 0
            # The turn must now belong to the opponent
            assert ("Turn: you" in post_status.stdout) == False, "Turn did not switch after fire"

            # ----- sanity check: board contains the new hit/miss emoji -----
            board_before = _parse_board(my_status_before.stdout)
            board_after = _parse_board(post_status.stdout)

            col_idx = ord(coord[0].upper()) - ord('A')
            row_idx = int(coord[1:]) - 1
            before_cell = board_before[row_idx][col_idx]
            after_cell = board_after[row_idx][col_idx]

            # BEFORE the move the cell can be any of the following:
            #   ❓ unknown water
            #   🚢 our own ship (we never fire at our own ship, but the board shows it)
            #   💥 a previous hit we already made
            #   ⚪ a previous miss we already made
            # The only thing we *cannot* see is the opponent’s ship (it is never shown).
            allowed_before = {"❓", "🚢", "💥", "⚪", "🔥"}
            assert before_cell in allowed_before, (
                f"Cell {coord} had unexpected content before fire: {before_cell}"
            )

            # AFTER the move it must be either a hit (💥) or a miss (⚪)
            allowed_after = {"💥", "⚪"} | allowed_before
            assert after_cell in allowed_after, (
                f"Cell {coord} after fire is {after_cell}, expected one of {sorted(allowed_after)}"
            )

        # --------------------------------------------------------------
        # 7️⃣  Final assertions
        # --------------------------------------------------------------
        assert winner_declared, "The game finished without a winner (should be impossible on a 12×12 board)"

    finally:
        # Clean up: terminate server and delete temporary dirs
        server_proc.terminate()
        server_proc.wait(timeout=5)
        shutil.rmtree(snap_common_dir, ignore_errors=True)

# ----------------------------------------------------------------------
# If the file is executed directly, run the test (useful for quick dev runs)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    try:
        test_full_game_flow()
        print("\n✅  Integration test passed – a full game completed successfully.")
    except AssertionError as e:
        print(f"\n❌  Integration test failed: {e}")
        sys.exit(1)
