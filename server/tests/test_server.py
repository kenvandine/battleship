
import os
import sys
import shutil
import tempfile
import pytest
from pathlib import Path

# Add server directory to sys.path so we can import app
# We try to locate the server directory relative to this test file.
# If running from repo root: server/tests/test_server.py -> parents[2] is repo root.
# Repo root / 'server' is the server directory.
SERVER_DIR = Path(__file__).parents[2] / 'server'
if str(SERVER_DIR) not in sys.path:
    sys.path.append(str(SERVER_DIR))

try:
    from app import app, GAMES_ROOT, BOARD_SIZE, SHIP_SIZES
except ImportError as e:
    if "No module named" in str(e):
        print(f"\nERROR: Missing dependencies. Please install server requirements:\n"
              f"       pip install -r {SERVER_DIR}/requirements.txt\n")
    raise e

@pytest.fixture
def client():
    # Create a temporary directory for games
    temp_dir = tempfile.mkdtemp()

    # We need to monkeypatch the GAMES_ROOT in the app module because it's calculated at module level.
    import app as app_module
    original_games_root = app_module.GAMES_ROOT
    app_module.GAMES_ROOT = Path(temp_dir)

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

    # Cleanup
    shutil.rmtree(temp_dir)
    app_module.GAMES_ROOT = original_games_root

def test_start_game(client):
    response = client.post('/games/start')
    assert response.status_code == 201
    data = response.get_json()
    assert 'game_id' in data
    assert len(data['game_id']) == 6

def test_join_game(client):
    # Start a game
    start_resp = client.post('/games/start')
    game_id = start_resp.get_json()['game_id']

    # Join the game
    join_resp = client.post(f'/games/{game_id}/join')
    assert join_resp.status_code == 200
    data = join_resp.get_json()
    assert 'token' in data

    # Try to join with a second player
    join_resp2 = client.post(f'/games/{game_id}/join')
    assert join_resp2.status_code == 200
    assert 'token' in join_resp2.get_json()

    # Try to join with a third player (should fail)
    join_resp3 = client.post(f'/games/{game_id}/join')
    assert join_resp3.status_code == 400

def test_get_state(client):
    # Start and join
    start_resp = client.post('/games/start')
    game_id = start_resp.get_json()['game_id']
    token1 = client.post(f'/games/{game_id}/join').get_json()['token']
    token2 = client.post(f'/games/{game_id}/join').get_json()['token']

    # Get state without token (public state)
    resp = client.get(f'/games/{game_id}/state')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['id'] == game_id
    assert 'players' in data
    assert 'private_board' in data
    assert data['private_board'] is None

    # Get state with token (private state)
    resp = client.get(f'/games/{game_id}/state?token={token1}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['private_board'] is not None
    assert len(data['private_board']) == BOARD_SIZE

def test_make_move(client):
    # Setup game
    start_resp = client.post('/games/start')
    game_id = start_resp.get_json()['game_id']
    token1 = client.post(f'/games/{game_id}/join').get_json()['token']
    token2 = client.post(f'/games/{game_id}/join').get_json()['token']

    # Get initial state to find who's turn it is
    state = client.get(f'/games/{game_id}/state').get_json()
    turn = state['turn']

    player_token = turn
    other_token = token2 if token1 == turn else token1

    # Make a move (miss likely, but we can't be sure without peeking, but let's just fire at A1)
    move_payload = {"token": player_token, "coord": "A1"}
    resp = client.post(f'/games/{game_id}/move', json=move_payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'result' in data
    assert 'hit' in data

    # Verify turn switched
    state = client.get(f'/games/{game_id}/state').get_json()
    assert state['turn'] == other_token

def test_move_validation(client):
    start_resp = client.post('/games/start')
    game_id = start_resp.get_json()['game_id']
    token1 = client.post(f'/games/{game_id}/join').get_json()['token']

    # Move without opponent
    move_payload = {"token": token1, "coord": "A1"}
    resp = client.post(f'/games/{game_id}/move', json=move_payload)
    assert resp.status_code == 400 # Opponent has not joined

    token2 = client.post(f'/games/{game_id}/join').get_json()['token']

    # Get turn
    state = client.get(f'/games/{game_id}/state').get_json()
    turn = state['turn']
    not_turn_token = token2 if token1 == turn else token1

    # Move with wrong turn
    move_payload = {"token": not_turn_token, "coord": "A1"}
    resp = client.post(f'/games/{game_id}/move', json=move_payload)
    assert resp.status_code == 400

    # Move with invalid coord
    move_payload = {"token": turn, "coord": "Z99"}
    resp = client.post(f'/games/{game_id}/move', json=move_payload)
    assert resp.status_code == 400

def test_game_persistence(client):
    # Verify game is saved to disk
    start_resp = client.post('/games/start')
    game_id = start_resp.get_json()['game_id']

    import app as app_module
    game_path = app_module.GAMES_ROOT / f"{game_id}.json"
    assert game_path.exists()
