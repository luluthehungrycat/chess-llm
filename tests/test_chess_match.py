"""Integration tests for ChessMatch class from chess_llm.py."""

import os
import tempfile
import chess
import pytest

# Import from parent directory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chess_llm import ChessMatch, RandomPlayer, render_board


class TestChessMatchInitialization:
    """Test ChessMatch initialization with different player types."""

    def test_init_with_random_players(self):
        """Test initialization with RandomPlayer vs RandomPlayer."""
        white = RandomPlayer("WhiteRandom")
        black = RandomPlayer("BlackRandom")
        match = ChessMatch(white, black, delay=0)
        
        assert match.white == white
        assert match.black == black
        assert match.delay == 0
        assert isinstance(match.board, chess.Board)
        assert len(match.board.move_stack) == 0
        assert match.pgn_game.headers["Event"] == "LLM Chess Match"
        assert match.pgn_game.headers["White"] == "WhiteRandom"
        assert match.pgn_game.headers["Black"] == "BlackRandom"

    def test_init_with_custom_event_name(self):
        """Test initialization with custom event name."""
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, event="Custom Tournament", round_name="5")
        
        assert match.pgn_game.headers["Event"] == "Custom Tournament"
        assert match.pgn_game.headers["Round"] == "5"

    def test_init_with_starting_board(self):
        """Test initialization with a custom starting board position."""
        custom_board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/R1BQKBNR w KQkq - 0 1")
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0, starting_board=custom_board)
        
        assert match.board.fen() == custom_board.fen()
        # Verify PGN has opening moves seeded
        assert len(match.board.move_stack) == 0  # custom_board has no moves yet

    def test_init_with_starting_board_with_moves(self):
        """Test initialization with a starting board that has moves."""
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        board.push(move)
        
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0, starting_board=board)
        
        assert match.board.fen() == board.fen()
        assert len(match.board.move_stack) == 1


class TestChessMatchPlay:
    """Test ChessMatch.play() functionality."""

    def test_play_random_vs_random_completes(self):
        """Test that RandomPlayer vs RandomPlayer completes quickly."""
        white = RandomPlayer("WhiteRandom")
        black = RandomPlayer("BlackRandom")
        match = ChessMatch(white, black, delay=0)
        
        result = match.play()
        
        # Game should complete with a valid result
        assert result in ["1-0", "0-1", "1/2-1/2"]
        
        # Board should be in game-over state
        assert match.board.is_game_over(claim_draw=True)
        
        # PGN should have a result
        assert "Result" in match.pgn_game.headers
        assert match.pgn_game.headers["Result"] == result

    def test_play_generates_move_history(self):
        """Test that play() generates move history."""
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0)
        
        result = match.play()
        
        # Should have at least some moves
        assert len(match.board.move_stack) > 0
        
        # PGN should contain moves
        exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
        pgn_text = match.pgn_game.accept(exporter)
        assert len(pgn_text) > 0

    def test_play_completes_without_errors(self):
        """Test that play() completes without errors with random players."""
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0)
        
        # Should not raise any exceptions
        result = match.play()
        assert result in ["1-0", "0-1", "1/2-1/2"]


class TestPGNGeneration:
    """Test PGN generation and saving."""

    def test_save_pgn_creates_file(self):
        """Test that save_pgn creates a valid PGN file."""
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0)
        match.play()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pgn', delete=False) as f:
            temp_path = f.name
        
        try:
            match.save_pgn(temp_path)
            
            # Verify file exists and is readable
            assert os.path.exists(temp_path)
            
            # Read and verify PGN content
            with open(temp_path, 'r') as f:
                content = f.read()
            
            assert "[Event \"LLM Chess Match\"]" in content
            assert "[White \"White\"]" in content
            assert "[Black \"Black\"]" in content
            assert "[Result" in content
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_pgn_headers_set_correctly(self):
        """Test that PGN headers are set correctly."""
        white = RandomPlayer("TestWhite")
        black = RandomPlayer("TestBlack")
        match = ChessMatch(white, black, delay=0, event="Test Event", round_name="3")
        
        assert match.pgn_game.headers["Event"] == "Test Event"
        assert match.pgn_game.headers["Round"] == "3"
        assert match.pgn_game.headers["White"] == "TestWhite"
        assert match.pgn_game.headers["Black"] == "TestBlack"
        assert match.pgn_game.headers["Site"] == "LLM Chess CLI"


class TestBoardRendering:
    """Test render_board function."""

    def test_render_board_initial_position(self):
        """Test rendering the initial board position."""
        board = chess.Board()
        rendered = render_board(board)
        
        # Check that it contains expected elements
        assert "♜" in rendered  # Black rook
        assert "♔" in rendered  # White king
        assert "a" in rendered  # File labels
        assert "8" in rendered  # Rank labels
        assert "┌" in rendered  # Border characters

    def test_render_board_with_last_move(self):
        """Test rendering with last move highlighted."""
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        board.push(move)
        
        rendered = render_board(board, last_move=move)
        
        # Should contain ANSI color codes for highlighting
        assert "\033[43m" in rendered  # Yellow background
        assert "\033[0m" in rendered   # Reset code

    def test_render_board_empty_squares(self):
        """Test that empty squares are rendered as spaces."""
        board = chess.Board("8/8/8/8/8/8/8/8 w - - 0 1")  # Empty board
        rendered = render_board(board)
        
        # Should have spaces for empty squares
        assert " │" in rendered


class TestGameResultDetection:
    """Test game result detection."""

    def test_checkmate_result_from_scholars_mate(self):
        """Test that checkmate produces correct result using scholar's mate."""
        # Create a checkmate position using scholar's mate
        board = chess.Board()
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
        
        # Board should be in checkmate
        assert board.is_checkmate()
        assert board.result() == "1-0"

    def test_stalemate_result(self):
        """Test that stalemate produces correct result."""
        # Create a stalemate position
        board = chess.Board("k7/8/8/8/8/8/7p/K7 b - - 0 1")
        # Black has no legal moves but is not in check
        
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0, starting_board=board)
        
        if match.board.is_stalemate():
            assert match.board.result() == "1/2-1/2"


class TestMoveHistoryTracking:
    """Test move history tracking."""

    def test_move_stack_grows(self):
        """Test that move stack grows as moves are made."""
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0)
        
        initial_count = len(match.board.move_stack)
        assert initial_count == 0
        
        # Play a few moves manually
        move1 = chess.Move.from_uci("e2e4")
        match.board.push(move1)
        match.node = match.node.add_variation(move1)
        
        assert len(match.board.move_stack) == 1
        
        move2 = chess.Move.from_uci("e7e5")
        match.board.push(move2)
        match.node = match.node.add_variation(move2)
        
        assert len(match.board.move_stack) == 2

    def test_history_text_generation(self):
        """Test that _history_text generates correct PGN."""
        white = RandomPlayer("White")
        black = RandomPlayer("Black")
        match = ChessMatch(white, black, delay=0)
        
        # Initially empty
        assert match._history_text() == ""
        
        # Add a move
        move = chess.Move.from_uci("e2e4")
        match.board.push(move)
        match.node = match.node.add_variation(move)
        
        history = match._history_text()
        assert "e4" in history
