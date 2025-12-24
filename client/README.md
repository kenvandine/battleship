### `client/README.md`

```markdown
# Battleship Client

A tiny command‑line program that talks to the Battleship server via its REST API.

## Requirements

- Python 3.9+
- `requests`

## Installation

```bash
cd client
python -m venv .venv
source .venv/bin/activate
pip install requests
chmod +x battleship          # make the script executable
# (optional) copy to a folder in your $PATH
sudo cp battleship /usr/local/bin/
Usage
battleship <command> [arguments]
Command	Arguments	Description
start	–	Creates a new game on the server and stores the returned token in $HOME/.battleship/current.
join	<GAME_ID>	Joins an existing game and saves the token locally.
status	–	Shows the current board, whose turn it is, and hit/miss markers.
fire	<COORD> (e.g. E7)	Fires a shot at the opponent (only allowed on your turn).
quit	–	Clears the local token file – useful if you want to abandon the current game locally.
Example session (two players)
Player A

battleship start          # → creates game, prints ID
battleship status         # → shows empty board, you have the turn
battleship fire D4        # → fires at D4

Player B (on another machine or later)

battleship join abcxyz    # ← use the ID printed by Player A
battleship status         # ← sees opponent’s miss/hit markers
battleship fire H9        # ← takes their turn

The client stores the token in:

$HOME/.battleship/current
so you can close the terminal, reboot, or switch machines (as long as you copy the token file) and resume the game later with battleship status or battleship fire ….

Configuration
If the server runs on a non‑default host/port, edit the SERVER_URL constant near the top of battleship:

SERVER_URL = "http://my.server.address:8080/"
