"""Test the ELO rating system from elo.py."""

import os
import tempfile
import json
import math
import pytest

# Import from parent directory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from elo import (
    EloTracker, 
    DEFAULT_K, 
    PROVISIONAL_K, 
    DEFAULT_RATING, 
    PROVISIONAL_GAMES
)


class TestEloTrackerInitialization:
    """Test EloTracker initialization and persistence."""

    def test_init_creates_empty_db(self):
        """Test that initialization creates an empty database."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            # Write empty JSON object
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            assert os.path.exists(temp_path)
            
            # Read the file to verify it's valid JSON
            with open(temp_path, 'r') as f:
                data = json.load(f)
            assert data == {}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_init_loads_existing_db(self):
        """Test that initialization loads existing database."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            existing_data = {
                "player1": {"rating": 1500, "games": 5, "wins": 3, "losses": 1, "draws": 1}
            }
            json.dump(existing_data, f)
        
        try:
            tracker = EloTracker(temp_path)
            player_data = tracker.get("player1")
            assert player_data["rating"] == 1500
            assert player_data["games"] == 5
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestGetMethods:
    """Test get() and get_rating() methods."""

    def test_get_existing_player(self):
        """Test get() with existing player."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            # Add a player first
            tracker.update("player1", "player2", "1-0")
            
            data = tracker.get("player1")
            assert "rating" in data
            assert "games" in data
            assert "wins" in data
            assert "losses" in data
            assert "draws" in data
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_get_nonexistent_player_returns_defaults(self):
        """Test get() with non-existing player returns defaults."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            data = tracker.get("nonexistent")
            
            assert data["rating"] == DEFAULT_RATING
            assert data["games"] == 0
            assert data["wins"] == 0
            assert data["losses"] == 0
            assert data["draws"] == 0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_get_rating_returns_correct_rating(self):
        """Test get_rating() returns correct rating."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            # Add a player with a specific rating
            tracker._ratings["test_player"] = {"rating": 1800, "games": 10, "wins": 5, "losses": 3, "draws": 2}
            tracker._save()
            
            rating = tracker.get_rating("test_player")
            assert rating == 1800
            
            # Non-existent player should return default
            rating = tracker.get_rating("nonexistent")
            assert rating == DEFAULT_RATING
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestUpdateMethod:
    """Test update() method with various results."""

    def test_update_white_wins(self):
        """Test update() with white win (1-0)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            result = tracker.update("white_player", "black_player", "1-0")
            
            white_data = result["white"]
            black_data = result["black"]
            
            # White should have won
            assert white_data["wins"] == 1
            assert white_data["losses"] == 0
            assert black_data["wins"] == 0
            assert black_data["losses"] == 1
            
            # Both should have 1 game
            assert white_data["games"] == 1
            assert black_data["games"] == 1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_update_black_wins(self):
        """Test update() with black win (0-1)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            result = tracker.update("white_player", "black_player", "0-1")
            
            white_data = result["white"]
            black_data = result["black"]
            
            # Black should have won
            assert white_data["wins"] == 0
            assert white_data["losses"] == 1
            assert black_data["wins"] == 1
            assert black_data["losses"] == 0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_update_draw(self):
        """Test update() with draw (1/2-1/2)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            result = tracker.update("white_player", "black_player", "1/2-1/2")
            
            white_data = result["white"]
            black_data = result["black"]
            
            # Both should have a draw
            assert white_data["draws"] == 1
            assert black_data["draws"] == 1
            assert white_data["wins"] == 0
            assert black_data["wins"] == 0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_update_elo_formula_white_wins(self):
        """Test ELO formula: new_rating = old_rating + K * (actual_score - expected_score)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Set up players with known ratings
            white_rating = 1500
            black_rating = 1500
            
            # Manually set ratings to bypass defaults
            tracker._ratings["white"] = {"rating": white_rating, "games": 10, "wins": 0, "losses": 0, "draws": 0}
            tracker._ratings["black"] = {"rating": black_rating, "games": 10, "wins": 0, "losses": 0, "draws": 0}
            tracker._save()
            
            # White wins
            result = tracker.update("white", "black", "1-0")
            
            white_new = result["white"]["rating"]
            black_new = result["black"]["rating"]
            
            # Expected scores when ratings are equal
            w_expected = 1.0 / (1.0 + 10.0 ** ((black_rating - white_rating) / 400.0))
            b_expected = 1.0 - w_expected
            
            # K-factor for established players
            k = DEFAULT_K
            
            # Calculate expected new ratings
            w_expected_new = white_rating + k * (1.0 - w_expected)
            b_expected_new = black_rating + k * (0.0 - b_expected)
            
            # Round to match implementation
            assert white_new == round(w_expected_new)
            assert black_new == round(b_expected_new)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_update_elo_formula_with_rating_difference(self):
        """Test ELO formula with different ratings."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # White is stronger (2000 vs 1500)
            white_rating = 2000
            black_rating = 1500
            
            tracker._ratings["white"] = {"rating": white_rating, "games": 10, "wins": 0, "losses": 0, "draws": 0}
            tracker._ratings["black"] = {"rating": black_rating, "games": 10, "wins": 0, "losses": 0, "draws": 0}
            tracker._save()
            
            # Black wins (upset!)
            result = tracker.update("white", "black", "0-1")
            
            white_new = result["white"]["rating"]
            black_new = result["black"]["rating"]
            
            # Expected scores
            w_expected = 1.0 / (1.0 + 10.0 ** ((black_rating - white_rating) / 400.0))
            b_expected = 1.0 - w_expected
            
            k = DEFAULT_K
            
            # Black wins: white gets 0, black gets 1
            w_expected_new = white_rating + k * (0.0 - w_expected)
            b_expected_new = black_rating + k * (1.0 - b_expected)
            
            assert white_new == round(w_expected_new)
            assert black_new == round(b_expected_new)
            
            # Equal K-factors conserve the rating sum after rounding.
            assert (white_rating - white_new) == (black_new - black_rating)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_white_win_conserves_rating_sum_with_uneven_established_ratings(self):
        tracker = EloTracker(":memory:")
        tracker._ratings["white"] = {"rating": 1600, "games": 10, "wins": 0, "losses": 0, "draws": 0}
        tracker._ratings["black"] = {"rating": 1400, "games": 10, "wins": 0, "losses": 0, "draws": 0}

        result = tracker.update("white", "black", "1-0")

        w_expected = 1.0 / (1.0 + 10.0 ** ((1400 - 1600) / 400.0))
        b_expected = 1.0 - w_expected
        assert result["white"]["rating"] == round(1600 + DEFAULT_K * (1 - w_expected))
        assert result["black"]["rating"] == round(1400 + DEFAULT_K * (0 - b_expected))
        assert result["white"]["rating"] + result["black"]["rating"] == 3000

    @pytest.mark.parametrize("result", ["error", "*", "win"])
    def test_update_rejects_unknown_result(self, result):
        tracker = EloTracker(":memory:")
        with pytest.raises(ValueError):
            tracker.update("white", "black", result)

    def test_self_play_is_unrated(self):
        tracker = EloTracker(":memory:")
        out = tracker.update("player", "player", "1-0")
        assert out["skipped"] is True
        assert tracker.get("player")["games"] == 0
        assert tracker.get("player")["rating"] == 1200


class TestKFactorLogic:
    """Test K-factor logic for provisional vs established players."""

    def test_provisional_players_use_higher_k(self):
        """Test that provisional players (<10 games) use K=64."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Create provisional players (0 games)
            tracker._ratings["provisional"] = {"rating": 1200, "games": 0, "wins": 0, "losses": 0, "draws": 0}
            tracker._save()
            
            # Update with provisional player
            result = tracker.update("provisional", "opponent", "1-0")
            
            # Check that the provisional player used PROVISIONAL_K
            # We can verify by checking the rating change is larger than with DEFAULT_K
            provisional_data = result["white"]
            
            # Calculate what the change would be with both K values
            # For a win against a default-rated opponent
            opponent_rating = DEFAULT_RATING
            w_expected = 1.0 / (1.0 + 10.0 ** ((opponent_rating - 1200) / 400.0))
            
            change_with_provisional_k = PROVISIONAL_K * (1.0 - w_expected)
            change_with_default_k = DEFAULT_K * (1.0 - w_expected)
            
            actual_change = provisional_data["rating"] - 1200
            
            # Should use provisional K
            assert abs(actual_change - round(change_with_provisional_k)) < 1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_established_players_use_lower_k(self):
        """Test that established players (>=10 games) use K=32."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Create established player (10+ games)
            tracker._ratings["established"] = {"rating": 1500, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._save()
            
            # Update with established player
            result = tracker.update("established", "opponent", "1-0")
            
            established_data = result["white"]
            
            # Calculate expected change with DEFAULT_K
            opponent_rating = DEFAULT_RATING
            w_expected = 1.0 / (1.0 + 10.0 ** ((opponent_rating - 1500) / 400.0))
            
            change_with_default_k = DEFAULT_K * (1.0 - w_expected)
            
            actual_change = established_data["rating"] - 1500
            
            # Should use default K
            assert abs(actual_change - round(change_with_default_k)) < 1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_k_factor_transition_at_10_games(self):
        """Test that K-factor transitions at exactly 10 games."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Player with exactly 9 games should use PROVISIONAL_K
            tracker._ratings["player9"] = {"rating": 1200, "games": 9, "wins": 5, "losses": 4, "draws": 0}
            tracker._save()
            result9 = tracker.update("player9", "opponent", "1-0")
            
            # Player with exactly 10 games should use DEFAULT_K
            tracker._ratings["player10"] = {"rating": 1200, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._save()
            result10 = tracker.update("player10", "opponent", "1-0")
            
            # The rating change should be different
            change9 = result9["white"]["rating"] - 1200
            change10 = result10["white"]["rating"] - 1200
            
            # PROVISIONAL_K is 2x DEFAULT_K, so change should be ~2x
            assert abs(change9) > abs(change10)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestLeaderboard:
    """Test leaderboard() method."""

    def test_leaderboard_sorts_by_rating_descending(self):
        """Test that leaderboard returns players sorted by rating descending."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Add players with different ratings
            tracker._ratings["player_a"] = {"rating": 2000, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._ratings["player_b"] = {"rating": 1500, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._ratings["player_c"] = {"rating": 2500, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._save()
            
            leaderboard = tracker.leaderboard()
            
            # Should be sorted by rating descending
            assert leaderboard[0][0] == "player_c"
            assert leaderboard[0][1]["rating"] == 2500
            assert leaderboard[1][0] == "player_a"
            assert leaderboard[1][1]["rating"] == 2000
            assert leaderboard[2][0] == "player_b"
            assert leaderboard[2][1]["rating"] == 1500
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_leaderboard_limits_to_n(self):
        """Test that leaderboard limits to N players."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Add 5 players
            for i in range(5):
                tracker._ratings[f"player_{i}"] = {"rating": 1000 + i * 100, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._save()
            
            leaderboard = tracker.leaderboard(n=3)
            
            assert len(leaderboard) == 3
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestPredict:
    """Test predict() method."""

    def test_predict_equal_ratings(self):
        """Test predict with equal ratings."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Both players have same rating
            tracker._ratings["white"] = {"rating": 1500, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._ratings["black"] = {"rating": 1500, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._save()
            
            w_exp, b_exp = tracker.predict("white", "black")
            
            # Expected score should be 0.5 for both
            assert abs(w_exp - 0.5) < 0.001
            assert abs(b_exp - 0.5) < 0.001
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_predict_rating_difference(self):
        """Test predict with rating difference."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # White is stronger
            tracker._ratings["white"] = {"rating": 2000, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._ratings["black"] = {"rating": 1500, "games": 10, "wins": 5, "losses": 5, "draws": 0}
            tracker._save()
            
            w_exp, b_exp = tracker.predict("white", "black")
            
            # White should have higher expected score
            assert w_exp > b_exp
            assert w_exp > 0.5
            assert b_exp < 0.5
            
            # Verify formula: 1 / (1 + 10^((b - w) / 400))
            expected_w = 1.0 / (1.0 + 10.0 ** ((1500 - 2000) / 400.0))
            assert abs(w_exp - expected_w) < 0.001
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_predict_nonexistent_players_use_default(self):
        """Test predict with non-existent players uses default rating."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            w_exp, b_exp = tracker.predict("nonexistent_white", "nonexistent_black")
            
            # Both should be 0.5 since both use default rating
            assert abs(w_exp - 0.5) < 0.001
            assert abs(b_exp - 0.5) < 0.001
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestStatsTracking:
    """Test stats tracking (wins, losses, draws, games)."""

    def test_stats_initialized_correctly(self):
        """Test that stats are initialized correctly for new players."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # New player should have all stats at 0
            data = tracker.get("new_player")
            assert data["games"] == 0
            assert data["wins"] == 0
            assert data["losses"] == 0
            assert data["draws"] == 0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_stats_updated_on_win(self):
        """Test that stats are updated correctly on win."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # White wins
            tracker.update("white", "black", "1-0")
            
            white_data = tracker.get("white")
            black_data = tracker.get("black")
            
            assert white_data["games"] == 1
            assert white_data["wins"] == 1
            assert white_data["losses"] == 0
            assert white_data["draws"] == 0
            
            assert black_data["games"] == 1
            assert black_data["wins"] == 0
            assert black_data["losses"] == 1
            assert black_data["draws"] == 0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_stats_updated_on_multiple_games(self):
        """Test that stats accumulate correctly over multiple games."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{}')
        
        try:
            tracker = EloTracker(temp_path)
            
            # Play multiple games
            tracker.update("player1", "player2", "1-0")  # player1 wins
            tracker.update("player1", "player2", "0-1")  # player2 wins
            tracker.update("player1", "player2", "1/2-1/2")  # draw
            
            p1_data = tracker.get("player1")
            p2_data = tracker.get("player2")
            
            assert p1_data["games"] == 3
            assert p1_data["wins"] == 1
            assert p1_data["losses"] == 1
            assert p1_data["draws"] == 1
            
            assert p2_data["games"] == 3
            assert p2_data["wins"] == 1
            assert p2_data["losses"] == 1
            assert p2_data["draws"] == 1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestConstants:
    """Test that constants are set correctly."""

    def test_default_rating_is_1200(self):
        """Test that DEFAULT_RATING is 1200."""
        assert DEFAULT_RATING == 1200

    def test_default_k_is_32(self):
        """Test that DEFAULT_K is 32."""
        assert DEFAULT_K == 32

    def test_provisional_k_is_64(self):
        """Test that PROVISIONAL_K is 64."""
        assert PROVISIONAL_K == 64

    def test_provisional_games_is_10(self):
        """Test that PROVISIONAL_GAMES is 10."""
        assert PROVISIONAL_GAMES == 10


class TestEphemeralTracker:
    """The ':memory:' sentinel must NOT touch the filesystem.

    Regression test for a bug where EloTracker(":memory:") would create a
    literal ':memory:' file because it treated the path as a filename
    instead of an in-memory-only marker. Mirrors sqlite3's convention.
    """

    def test_memory_sentinel_does_not_create_file(self, tmp_path, monkeypatch):
        # chdir into a clean dir so any leak would land here
        monkeypatch.chdir(tmp_path)
        t = EloTracker(":memory:")
        t.update("a", "b", "1-0")
        t.update("a", "b", "0-1")
        t.update("a", "b", "1/2-1/2")
        # No ':memory:' file should be created
        assert not (tmp_path / ":memory:").exists()
        # In-memory state still works
        assert t.get_rating("a") != DEFAULT_RATING

    def test_memory_sentinel_does_not_load_existing(self, tmp_path, monkeypatch):
        # Even if a ':memory:' file exists on disk (from the old bug),
        # the ephemeral tracker must ignore it.
        monkeypatch.chdir(tmp_path)
        (tmp_path / ":memory:").write_text(
            '{"preexisting": {"rating": 9999, "games": 0, "wins": 0, "losses": 0, "draws": 0}}'
        )
        t = EloTracker(":memory:")
        assert t.get("preexisting")["rating"] == DEFAULT_RATING

    def test_save_skipped_for_ephemeral(self, tmp_path, monkeypatch):
        """update() calls _save() — verify it doesn't write for ephemeral."""
        monkeypatch.chdir(tmp_path)
        t = EloTracker(":memory:")
        t.update("x", "y", "1-0")
        assert list(tmp_path.iterdir()) == []
