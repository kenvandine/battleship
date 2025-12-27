
import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
import json
from pathlib import Path
import io

# Add client directory to sys.path
sys.path.append(str(Path(__file__).parents[2] / 'client'))

import battleship

class TestBattleshipClient(unittest.TestCase):

    def setUp(self):
        # Redirect stdout/stderr to capture output
        self.held, sys.stdout = sys.stdout, io.StringIO()
        self.held_err, sys.stderr = sys.stderr, io.StringIO()

    def tearDown(self):
        sys.stdout = self.held
        sys.stderr = self.held_err

    @patch('battleship.TOKEN_FILE')
    def test_save_load_token(self, mock_token_file):
        mock_token_file.parent.mkdir = MagicMock()
        mock_token_file.write_text = MagicMock()
        mock_token_file.read_text = MagicMock(return_value='{"game_id": "123", "token": "abc"}')
        mock_token_file.is_file = MagicMock(return_value=True)

        battleship._save_token("123", "abc")
        mock_token_file.write_text.assert_called_with('{"game_id": "123", "token": "abc"}')

        token_data = battleship._load_token()
        self.assertEqual(token_data, {"game_id": "123", "token": "abc"})

    @patch('battleship.requests')
    @patch('battleship._save_token')
    def test_cmd_start(self, mock_save_token, mock_requests):
        # Mock responses
        # The client uses _api which uses requests.request
        mock_requests.request.return_value.ok = True
        mock_requests.request.return_value.json.side_effect = [
            {"game_id": "test_game"}, # start response
            {"token": "test_token"}   # join response
        ]

        battleship.cmd_start([])

        mock_save_token.assert_called_with("test_game", "test_token")
        self.assertIn("New game created! ID = test_game", sys.stdout.getvalue())

    @patch('battleship.requests')
    @patch('battleship._save_token')
    def test_cmd_join(self, mock_save_token, mock_requests):
        # The client uses _api which uses requests.request
        mock_requests.request.return_value.ok = True
        mock_requests.request.return_value.json.return_value = {"token": "test_token"}

        battleship.cmd_join(["test_game"])

        mock_save_token.assert_called_with("test_game", "test_token")
        self.assertIn("Joined game test_game", sys.stdout.getvalue())

    @patch('battleship._load_token')
    @patch('battleship._fetch_state')
    def test_cmd_status(self, mock_fetch_state, mock_load_token):
        mock_load_token.return_value = {"game_id": "test_game", "token": "my_token"}

        # Mock state
        mock_state = {
            "turn": "my_token",
            "players": {
                "my_token": {"hits": [], "misses": []},
                "op_token": {"hits": [], "misses": []}
            },
            "private_board": [["~"]*12 for _ in range(12)],
            "winner": None
        }
        mock_fetch_state.return_value = mock_state

        battleship.cmd_status([])

        output = sys.stdout.getvalue()
        self.assertIn("Game ID: test_game", output)
        self.assertIn("Turn: you", output)
        self.assertIn("Game in progress", output)

    @patch('battleship._load_token')
    @patch('battleship._fetch_state')
    @patch('battleship.requests')
    def test_cmd_fire(self, mock_requests, mock_fetch_state, mock_load_token):
        mock_load_token.return_value = {"game_id": "test_game", "token": "my_token"}

        # Initial state: my turn
        mock_state = {
            "turn": "my_token",
            "players": {
                "my_token": {"hits": [], "misses": []},
                "op_token": {"hits": [], "misses": []}
            },
            "private_board": [["~"]*12 for _ in range(12)],
            "winner": None
        }
        mock_fetch_state.return_value = mock_state

        # Mock fire response
        # The client uses requests.post for fire
        mock_requests.post.return_value.ok = True
        mock_requests.post.return_value.json.return_value = {
            "result": "hit",
            "hit": True,
            "sunk": "S",
            "sunk_name": "Submarine"
        }

        battleship.cmd_fire(["A1"])

        output = sys.stdout.getvalue()
        self.assertIn("You fired at A1: HIT", output)
        self.assertIn("You SUNK the opponent's Submarine", output)

    @patch('battleship.TOKEN_FILE')
    def test_cmd_quit(self, mock_token_file):
        mock_token_file.is_file.return_value = True
        mock_token_file.unlink = MagicMock()

        battleship.cmd_quit([])

        mock_token_file.unlink.assert_called_once()
        self.assertIn("Current game cleared", sys.stdout.getvalue())

    def test_coord_logic(self):
        # Testing internal logic for board printing if needed,
        # but integration tests cover this better.
        pass

if __name__ == '__main__':
    unittest.main()
