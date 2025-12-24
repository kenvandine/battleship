### `server/README.md`

```markdown
# Battleship Server

This directory contains the Flask‑based REST API that powers the asynchronous Battleship game.

## Requirements

- Python 3.9+
- `flask`

## Installation (development)

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install flask
Running the server
export FLASK_APP=app.py           # tells Flask which module to run
# Optional: set SNAP_COMMON if you want the JSON files stored elsewhere
# export SNAP_COMMON=/var/snap/battleship/common
flask run --host=0.0.0.0 --port=5000

The server will automatically create a games/ directory inside $SNAP_COMMON (if the variable is set) or next to app.py otherwise. Each game is a single JSON file named <game_id>.json.

API Overview
Method	Endpoint	Description
POST	/games/start	Create a new game – returns game_id.
POST	/games/<game_id>/join	Join an existing game – returns a player token.
GET	/games/<game_id>/state	Get public game state (hits/misses, turn).
POST	/games/<game_id>/move (JSON body)	Fire a shot – requires token and coord.
All responses are JSON. Errors are returned with appropriate HTTP status codes and a short message.

Persistence Details
Game files live in: $SNAP_COMMON/games/<game_id>.json (or ./games/ during dev).
The directory is created automatically on first request.
Deleting a JSON file removes the corresponding game permanently.
Testing
You can use curl or any HTTP client:

curl -X POST http://localhost:5000/games/start
curl -X POST http://localhost:5000/games/<id>/join
curl http://localhost:5000/games/<id>/state
curl -X POST -H "Content-Type: application/json" \
     -d '{"token":"<your-token>", "coord":"B5"}' \
     http://localhost:5000/games/<id>/move
