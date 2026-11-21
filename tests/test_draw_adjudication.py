"""Test draw adjudication: 3-fold, 50-move, insufficient material, max-moves.

These conditions are auto-detected by python-chess via
board.is_game_over(claim_draw=True) and board.is_insufficient_material().
This test file locks down the contract so future refactors don't
break draw handling.
"""

import os
import sys
import chess
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chess_llm import ChessMatch, RandomPlayer


def _play_to_fen(moves_uci: list[str]) -> chess.Board:
    b = chess.Board()
    for u in moves_uci:
        b.push_uci(u)
    return b


class TestThreefoldRepetition:
    def test_threefold_position_is_game_over(self):
        """After 3-fold repetition, the position is game-over with claim_draw."""
        # Walk to a forced 3-fold: Ng1-f3-g1, Ng8-f6-g8, repeated 3 times
        b = _play_to_fen([
            "g1f3", "g8f6", "f3g1", "f6g8",
            "g1f3", "g8f6", "f3g1", "f6g8",
        ])
        assert b.can_claim_threefold_repetition()
        assert b.is_game_over(claim_draw=True)
        # But not game-over without claim — chess rules require a player to claim.
        # (After 5-fold repetition, it's automatic; 3-fold is claim-only.)
        # We use claim_draw=True in ChessMatch.play() so this is treated as game-over.

    def test_match_ends_in_draw_on_threefold(self):
        """ChessMatch.play() with claim_draw=True must return 1/2-1/2 on 3-fold."""
        # Two stubs that bounce the knights back and forth to force repetition
        class _Bouncer:
            def __init__(self):
                self.name = "B"
                self.illegal_count = 0
            def get_move(self, board, history):
                # Find a legal knight move that returns a piece to its origin.
                # Simplest: just play any legal move; the position itself
                # cycles via our fixed sequence.
                if board.turn == chess.WHITE:
                    # white's "turn" — play a knight if possible
                    moves = [m for m in board.legal_moves
                             if board.piece_at(m.from_square) and
                             board.piece_at(m.from_square).piece_type == chess.KNIGHT]
                    if moves:
                        return moves[0]
                else:
                    moves = [m for m in board.legal_moves
                             if board.piece_at(m.from_square) and
                             board.piece_at(m.from_square).piece_type == chess.KNIGHT]
                    if moves:
                        return moves[0]
                return next(iter(board.legal_moves))

        # Manually set up a 3-fold starting board (after 8 plies of bouncing)
        start = _play_to_fen([
            "g1f3", "g8f6", "f3g1", "f6g8",
            "g1f3", "g8f6", "f3g1", "f6g8",
        ])
        # Now play one more knight round → 3-fold achieved
        start.push_uci("g1f3"); start.push_uci("g8f6")
        # start is now in 3-fold claim territory
        assert start.can_claim_threefold_repetition()

        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, starting_board=start,
        )
        # With claim_draw=True, the game should end in a draw at move 1
        # (the RandomPlayer plays one move, then is_game_over(claim_draw=True) returns True).
        result = match.play()
        assert result == "1/2-1/2"


class TestInsufficientMaterial:
    def test_k_vs_k_ends_in_draw(self):
        """King vs King is insufficient material — game over as draw."""
        start = chess.Board("8/8/8/4k3/8/8/4K3/8 w - - 0 1")
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, starting_board=start,
        )
        result = match.play()
        assert result == "1/2-1/2"


class TestFiftyMoveRule:
    def test_fifty_move_position_is_game_over(self):
        """After 50 plies without a pawn move / capture, game is draw."""
        b = chess.Board()
        # Walk 100 plies of pure knight moves (no pawn, no capture)
        moves = ["g1f3", "g8f6", "f3g1", "f6g8"]
        for u in (moves * 25):  # 100 plies
            b.push_uci(u)
        assert b.is_fifty_moves() or b.halfmove_clock >= 100
        assert b.is_game_over(claim_draw=True)


class TestMaxMovesAdjudication:
    @pytest.mark.xfail(reason="ChessMatch max_moves limit not implemented", strict=True)
    def test_max_moves_caps_the_game(self):
        """--max-moves 4 must end the game after 4 plies as 1/2-1/2."""
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, max_moves=4,
        )
        result = match.play()
        assert result == "1/2-1/2"
        assert len(match.board.move_stack) <= 4
