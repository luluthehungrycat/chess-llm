"""Shared pytest fixtures for LLM Chess test suite."""

import pytest
import chess


# ── Board Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def empty_board():
    """Return an empty chess board."""
    return chess.Board()


@pytest.fixture
def starting_board():
    """Return a board at the starting position."""
    return chess.Board()


@pytest.fixture
def mid_game_board():
    """Return a board at a mid-game position."""
    board = chess.Board()
    # Play some moves to get to a mid-game position
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("g1f3"),
        chess.Move.from_uci("b8c6"),
        chess.Move.from_uci("f1c4"),
        chess.Move.from_uci("g8f6"),
        chess.Move.from_uci("d2d4"),
        chess.Move.from_uci("e5d4"),
    ]
    for move in moves:
        board.push(move)
    return board


@pytest.fixture
def checkmate_board():
    """Return a board with checkmate position (scholar's mate)."""
    board = chess.Board()
    # Scholar's mate
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("d1h5"),
        chess.Move.from_uci("b8c6"),
        chess.Move.from_uci("f1c4"),
        chess.Move.from_uci("g8f6"),
        chess.Move.from_uci("h5f7"),
    ]
    for move in moves:
        board.push(move)
    return board


@pytest.fixture
def limited_moves_board():
    """Return a board with very limited legal moves."""
    board = chess.Board()
    # Create a position with only a few legal moves
    moves = [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
        chess.Move.from_uci("d2d4"),
        chess.Move.from_uci("e5d4"),
    ]
    for move in moves:
        board.push(move)
    return board


@pytest.fixture
def promotion_board():
    """Return a board where a pawn can promote."""
    board = chess.Board()
    # Set up a position where white can promote
    board.set_fen("8/7P/8/8/8/8/8/8 w - - 0 1")
    return board


# ── PGN Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def simple_pgn():
    """Return a simple PGN string."""
    return "1. e4 e5 2. Nf3 Nc6"


@pytest.fixture
def full_pgn():
    """Return a full PGN with headers."""
    return """[Event "Test Game"]
[Site "Test Site"]
[Date "2024.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6 5. d4 exd4 6. Nxd4 Nxd4 7. Qxd4 Qxd4 8. Bxd4"""


@pytest.fixture
def pgn_with_comments():
    """Return a PGN with comments."""
    return "1. e4 {good move} e5 2. Nf3 Nc6 {developing}"


# ── Mock LLM Response Fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_llm_response_uci():
    """Mock LLM response with UCI move."""
    return {
        "content": "I will play e2e4. This is a good opening move.",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 20, "total": 120}
    }


@pytest.fixture
def mock_llm_response_san():
    """Mock LLM response with SAN move."""
    return {
        "content": "My move is Nf3. I think this develops the knight well.",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 20, "total": 120}
    }


@pytest.fixture
def mock_llm_response_tool_call():
    """Mock LLM response with tool call."""
    return {
        "content": "I'm making my move.",
        "tool_calls": [
            {
                "name": "make_move",
                "arguments": {"move": "e2e4"}
            }
        ],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 20, "total": 120}
    }


@pytest.fixture
def mock_llm_response_move_prefix():
    """Mock LLM response with MOVE: prefix."""
    return {
        "content": "MOVE: e2e4",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 20, "total": 120}
    }


@pytest.fixture
def mock_llm_response_make_move():
    """Mock LLM response with make_move prefix."""
    return {
        "content": "make_move e2e4",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 20, "total": 120}
    }


@pytest.fixture
def mock_llm_response_empty():
    """Mock empty LLM response."""
    return {
        "content": "",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 0, "total": 100}
    }


@pytest.fixture
def mock_llm_response_no_move():
    """Mock LLM response with no move."""
    return {
        "content": "I'm thinking about the position...",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt": 100, "completion": 20, "total": 120}
    }
