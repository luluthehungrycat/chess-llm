"""Chess board widget for Textual TUI."""

from typing import Optional

import chess
from rich.segment import Segment
from rich.style import Style
from textual.widget import Widget
from textual.strip import Strip

from .common import (
    PIECE_MAP, LIGHT_SQUARE, DARK_SQUARE, SELECTED_SQUARE,
    LAST_MOVE_LIGHT, LAST_MOVE_DARK, CURSOR_BORDER, TEXT_PRIMARY,
)


class BoardWidget(Widget):
    """Renders an 8×8 chess board with Unicode pieces."""

    WIDTH = 29
    DEFAULT_CSS = f"""
    BoardWidget {{
        width: {WIDTH};
        height: 10;
        padding: 0 1;
    }}
    """

    def __init__(
        self,
        board: chess.Board | None = None,
        flipped: bool = False,
        selected_square: Optional[int] = None,
        legal_moves: Optional[set[int]] = None,
        last_move: Optional[chess.Move] = None,
        name: str | None = None,
        *,
        id: str | None = None,
    ):
        super().__init__(name=name, id=id)
        self.board = board or chess.Board()
        self.flipped = flipped
        self.selected_square = selected_square
        self.legal_moves = legal_moves or set()
        self.last_move = last_move

    def render_line(self, y: int) -> Strip:
        """Render one line of the board widget."""
        if y == 9:
            cols = "abcdefgh"
            if self.flipped:
                cols = cols[::-1]
            text = "    " + "  ".join(cols)
            return Strip([Segment(text, Style(color=TEXT_PRIMARY.hex, bold=True))])
        if not 0 <= y < 8:
            return Strip.blank(self.WIDTH, Style())

        # Board rows (y=0 → rank 8, y=7 → rank 1 when not flipped)
        rank_idx = y if self.flipped else 7 - y

        parts = [Segment(f" {rank_idx + 1} ", Style(color=TEXT_PRIMARY.hex))]

        for file_idx in range(8):
            col = file_idx if not self.flipped else 7 - file_idx
            square = chess.square(col, rank_idx)
            piece = self.board.piece_at(square)

            # Square styling
            is_light = (rank_idx + col) % 2 == 1
            base_color = LIGHT_SQUARE if is_light else DARK_SQUARE

            # Last move highlight
            if self.last_move and square in (self.last_move.from_square,
                                              self.last_move.to_square):
                base_color = LAST_MOVE_LIGHT if is_light else LAST_MOVE_DARK

            # Selected square
            if square == self.selected_square:
                base_color = SELECTED_SQUARE

            # Piece or empty
            if piece:
                symbol = PIECE_MAP[piece.symbol()]
                char = f" {symbol} "
            elif square in self.legal_moves:
                char = " · "  # legal move dot
            else:
                char = "   "

            bg_hex = CURSOR_BORDER.hex if square == self.selected_square else base_color.hex
            fg = "#000000" if is_light or square == self.selected_square else "#ffffff"
            parts.append(Segment(char, Style(color=fg, bgcolor=bg_hex)))

        return Strip(parts)

    def update_state(
        self,
        board: chess.Board | None = None,
        selected_square: Optional[int] = None,
        legal_moves: Optional[set[int]] = None,
        last_move: Optional[chess.Move] = None,
    ):
        """Update the board state and refresh."""
        if board is not None:
            self.board = board
        self.selected_square = selected_square
        self.legal_moves = legal_moves or set()
        self.last_move = last_move
        self.refresh()
