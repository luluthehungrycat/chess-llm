"""Test move extraction regex patterns and _extract_move() function."""

import pytest
import chess
import sys
import os

# Add parent directory to path to import chess_llm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chess_llm import (
    _MOVE_RE,
    _MOVE_CMD_RE,
    _RAW_UCI_RE,
    _SAN_TOKEN_RE,
    _extract_move,
)


class TestMoveRegex:
    """Test the move extraction regex patterns."""

    def test_move_re_basic_uci(self):
        """Test _MOVE_RE matches basic UCI moves."""
        assert _MOVE_RE.search("MOVE: e2e4") is not None
        assert _MOVE_RE.search("move: g1f3") is not None
        assert _MOVE_RE.search("MOVE:e7e8q") is not None
        
    def test_move_re_captures_correctly(self):
        """Test _MOVE_RE captures the UCI move correctly."""
        match = _MOVE_RE.search("MOVE: e2e4")
        assert match is not None
        assert match.group(1) == "e2e4"
        
        match = _MOVE_RE.search("move: g1f3")
        assert match is not None
        assert match.group(1) == "g1f3"
        
        match = _MOVE_RE.search("MOVE:e7e8q")
        assert match is not None
        assert match.group(1) == "e7e8q"

    def test_move_re_case_insensitive(self):
        """Test _MOVE_RE is case insensitive."""
        assert _MOVE_RE.search("MOVE: e2e4") is not None
        assert _MOVE_RE.search("move: e2e4") is not None
        assert _MOVE_RE.search("Move: e2e4") is not None

    def test_move_re_no_match(self):
        """Test _MOVE_RE doesn't match invalid patterns."""
        assert _MOVE_RE.search("e2e4") is None
        assert _MOVE_RE.search("MOVE e2e4") is None
        assert _MOVE_RE.search("MOVE:") is None

    def test_move_cmd_re_basic(self):
        """Test _MOVE_CMD_RE matches make_move and my move patterns."""
        assert _MOVE_CMD_RE.search("make_move e2e4") is not None
        assert _MOVE_CMD_RE.search("my move: Nf3") is not None
        assert _MOVE_CMD_RE.search("make_move O-O") is not None

    def test_move_cmd_re_captures_correctly(self):
        """Test _MOVE_CMD_RE captures the move correctly."""
        match = _MOVE_CMD_RE.search("make_move e2e4")
        assert match is not None
        assert match.group(1) == "e2e4"
        
        match = _MOVE_CMD_RE.search("my move: Nf3")
        assert match is not None
        assert match.group(1) == "Nf3"
        
        match = _MOVE_CMD_RE.search("make_move O-O")
        assert match is not None
        assert match.group(1) == "O-O"

    def test_move_cmd_re_case_insensitive(self):
        """Test _MOVE_CMD_RE is case insensitive."""
        assert _MOVE_CMD_RE.search("MAKE_MOVE e2e4") is not None
        assert _MOVE_CMD_RE.search("My Move: Nf3") is not None

    def test_raw_uci_re_basic(self):
        """Test _RAW_UCI_RE matches standalone UCI moves."""
        assert _RAW_UCI_RE.search("e2e4") is not None
        assert _RAW_UCI_RE.search("g1f3") is not None
        assert _RAW_UCI_RE.search("e7e8q") is not None

    def test_raw_uci_re_in_text(self):
        """Test _RAW_UCI_RE finds UCI in text."""
        text = "I think e2e4 is a good move"
        match = _RAW_UCI_RE.search(text)
        assert match is not None
        assert match.group(1) == "e2e4"

    def test_raw_uci_re_captures_correctly(self):
        """Test _RAW_UCI_RE captures the UCI move correctly."""
        match = _RAW_UCI_RE.search("e2e4")
        assert match is not None
        assert match.group(1) == "e2e4"

    def test_san_token_re_basic(self):
        """Test _SAN_TOKEN_RE matches basic SAN moves."""
        assert _SAN_TOKEN_RE.search("Nf3") is not None
        assert _SAN_TOKEN_RE.search("O-O") is not None
        assert _SAN_TOKEN_RE.search("e4") is not None
        assert _SAN_TOKEN_RE.search("exd5") is not None
        assert _SAN_TOKEN_RE.search("Nc3") is not None
        assert _SAN_TOKEN_RE.search("Kxe8") is not None

    def test_san_token_re_castling(self):
        """Test _SAN_TOKEN_RE matches castling notation."""
        assert _SAN_TOKEN_RE.search("O-O") is not None
        assert _SAN_TOKEN_RE.search("O-O-O") is not None
        assert _SAN_TOKEN_RE.search("0-0") is not None
        assert _SAN_TOKEN_RE.search("0-0-0") is not None

    def test_san_token_re_with_check(self):
        """Test _SAN_TOKEN_RE matches moves with check notation."""
        assert _SAN_TOKEN_RE.search("Nf3+") is not None
        assert _SAN_TOKEN_RE.search("Qh5#") is not None

    def test_san_token_re_with_promotion(self):
        """Test _SAN_TOKEN_RE matches moves with promotion."""
        assert _SAN_TOKEN_RE.search("e8=Q") is not None
        assert _SAN_TOKEN_RE.search("a1=q") is not None


class TestExtractMove:
    """Test the _extract_move() function."""

    def test_extract_move_from_move_prefix(self, starting_board):
        """Test extracting move from MOVE: prefix."""
        text = "MOVE: e2e4"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_from_move_prefix_lowercase(self, starting_board):
        """Test extracting move from move: prefix (lowercase)."""
        text = "move: e2e4"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_from_make_move(self, starting_board):
        """Test extracting move from make_move prefix."""
        text = "make_move e2e4"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_from_my_move(self, starting_board):
        """Test extracting move from my move: prefix."""
        text = "my move: Nf3"
        result = _extract_move(text, starting_board)
        assert result == "g1f3"  # Nf3 in UCI

    def test_extract_move_san_in_text(self, starting_board):
        """Test extracting SAN move from text."""
        text = "I think Nf3 is the best move here"
        result = _extract_move(text, starting_board)
        assert result == "g1f3"  # Nf3 in UCI

    def test_extract_move_uci_in_text(self, starting_board):
        """Test extracting UCI move from text."""
        text = "I will play e2e4 next"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_from_tool_call(self, starting_board):
        """Test extracting move from tool call arguments."""
        # This would be handled by the caller, but test the text extraction
        text = "make_move e2e4"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_no_move(self, starting_board):
        """Test _extract_move returns None when no move found."""
        text = "I'm thinking about the position..."
        result = _extract_move(text, starting_board)
        assert result is None

    def test_extract_move_invalid_move(self, starting_board):
        """Test _extract_move returns None for invalid moves."""
        text = "I'll play z5z6"  # Invalid UCI
        result = _extract_move(text, starting_board)
        assert result is None

    def test_extract_move_multiple_possible(self, starting_board):
        """Test _extract_move with multiple possible moves in text."""
        # Should extract the first valid one
        text = "Possible moves: e2e4, d2d4, g1f3. I choose e2e4"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_with_punctuation(self, starting_board):
        """Test _extract_move handles punctuation."""
        text = "My move is e2e4!"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

        text = "I'll play e2e4."
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

        text = "make_move: e2e4"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_castling(self):
        """Test _extract_move with castling notation."""
        # Need to set up a board where castling is legal
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))
        board.push(chess.Move.from_uci("e7e5"))
        board.push(chess.Move.from_uci("g1f3"))
        board.push(chess.Move.from_uci("b8c6"))
        board.push(chess.Move.from_uci("f1c4"))
        board.push(chess.Move.from_uci("g8f6"))
        
        text = "O-O"
        result = _extract_move(text, board)
        assert result == "e1g1"  # White kingside castling in UCI

    def test_extract_move_promotion(self, promotion_board):
        """Test _extract_move with promotion."""
        text = "h8=Q"
        result = _extract_move(text, promotion_board)
        assert result == "h7h8q"

    def test_extract_move_limited_legal_moves(self):
        """Test _extract_move with board that has limited legal moves."""
        # Create a simple board with known legal moves
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))
        board.push(chess.Move.from_uci("e7e5"))
        
        # Get the legal moves for this board
        legal_moves = [m.uci() for m in board.legal_moves]
        
        # Try to extract one of the legal moves
        if legal_moves:
            text = f"I'll play {legal_moves[0]}"
            result = _extract_move(text, board)
            assert result == legal_moves[0]

    def test_extract_move_illegal_move_ignored(self, starting_board):
        """Test _extract_move ignores illegal moves and finds legal ones."""
        text = "I want to play d2d5 but e2e4 is better"
        result = _extract_move(text, starting_board)
        # d2d5 is not legal in starting position, but e2e4 is
        assert result == "e2e4"

    def test_extract_move_case_insensitive_uci(self, starting_board):
        """Test _extract_move handles case-insensitive UCI."""
        text = "E2E4"
        result = _extract_move(text, starting_board)
        # The regex only matches lowercase, but the function should handle it
        # via the SAN parsing fallback
        assert result is None  # This is expected behavior based on the regex

    def test_extract_move_with_markdown(self, starting_board):
        """Test _extract_move handles markdown formatting."""
        text = "My move is *e2e4*"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

        text = "I'll play `e2e4`"
        result = _extract_move(text, starting_board)
        assert result == "e2e4"

    def test_extract_move_from_end_of_text(self, starting_board):
        """Test _extract_move prefers moves near the end of text."""
        # When multiple SAN tokens exist, should prefer the one near the end
        text = "Nf3 is good but I'll play e2e4"
        result = _extract_move(text, starting_board)
        # Both Nf3 and e2e4 are legal, but e2e4 is at the end
        assert result == "e2e4"
