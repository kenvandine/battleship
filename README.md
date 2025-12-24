# Battleship – Async Terminal Game

A lightweight, asynchronous Battleship implementation that runs on a **Flask REST API** (server) and a tiny **Python CLI client**.  

- **Server** stores each game's state as a JSON file.  
- **Client** talks to the server via HTTP, saves a tiny token in `$HOME/.battleship/current`, and lets you resume games later.  
- Games can be played live or asynchronously – you can quit the client and come back whenever you like.

## Project Layout

battleship/ │ ├─ README.md # ← you are here │ ├─ server/ │ ├─ README.md # server setup & usage │ └─ app.py # Flask API (stores games under $SNAP_COMMON/games) │ └─ client/ ├─ README.md # client installation & commands └─ battleship # executable script (chmod +x)


## Quick Start (local development)

```bash
# 1️⃣ Clone the repo
git clone <repo‑url>
cd battleship

# 2️⃣ Server
cd server
python -m venv .venv && source .venv/bin/activate
pip install flask
export FLASK_APP=app.py
flask run --host=127.0.0.1 --port=5000   # server now listening

# 3️⃣ Client (in another terminal)
cd ../client
chmod +x battleship
# optionally move it to a folder in your $PATH, e.g. /usr/local/bin
sudo mv battleship /usr/local/bin/

# 4️⃣ Play!
battleship start          # creates a new game, stores token locally
battleship status         # shows board & whose turn it is
battleship fire B5        # fire a shot (when it’s your turn)
Environment Variable
$SNAP_COMMON – If set, the server will store all game JSON files under $SNAP_COMMON/games.
This is useful when packaging the server as a Snap or when you want a central, write‑protected location.
If $SNAP_COMMON is not defined, the server defaults to a local games/ folder next to app.py.
License
MIT – feel free to fork, improve, or embed in your own projects.
