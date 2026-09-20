#!/usr/bin/env python3
"""
Test script for agent harness integration.

This script tests the agent harness implementations without requiring
actual agent harnesses to be installed.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all imports work correctly."""
    print("🧪 Testing imports...")
    
    try:
        # Test base imports
        from agents.harnesses import BaseAgentHarness, get_harness
        from agents.harnesses.base import GameState, AgentResponse
        print("✅ Base harness imports successful")
        
        # Test specific harness imports
        from agents.harnesses.opencode import OpenCodeAgentHarness
        from agents.harnesses.hermes import HermesAgentHarness
        from agents.harnesses.vibe_cli import VibeCLIAgentHarness
        print("✅ Specific harness imports successful")
        
        # Test integration imports
        from agents.agent_player_integration import (
            AgentHarnessPlayer, 
            parse_agent_harness_spec, 
            create_agent_harness_player,
            is_agent_harness_spec
        )
        print("✅ Integration imports successful")
        
        # Test chess_llm imports
        from chess_llm import parse_player
        print("✅ chess_llm imports successful")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_parse_agent_harness_spec():
    """Test the parse_agent_harness_spec function."""
    print("\n🧪 Testing parse_agent_harness_spec...")
    
    from agents.agent_player_integration import parse_agent_harness_spec
    
    test_cases = [
        ("hermes:qwen3.5-27B", ("hermes", "qwen3.5-27B", {})),
        ("opencode-agent:deepseek-v4-flash-free", ("opencode-agent", "deepseek-v4-flash-free", {})),
        ("vibe-cli:mistral-medium-3.5", ("vibe-cli", "mistral-medium-3.5", {})),
        ("hermes:llama-3.3-70b?timeout=60", ("hermes", "llama-3.3-70b", {"timeout": "60"})),
        ("opencode", ("opencode", None, {})),
        ("hermes-agent", ("hermes-agent", None, {})),
        # Hermes profile support tests
        ("hermes:chess-profile:qwen3.5-27B", ("hermes", "qwen3.5-27B", {"profile": "chess-profile"})),
        ("hermes:chess-profile", ("hermes", None, {"profile": "chess-profile"})),
        ("hermes:qwen3.5-27B?profile=chess", ("hermes", "qwen3.5-27B", {"profile": "chess"})),
        ("hermes-agent:chess-profile:qwen3.5-27B", ("hermes-agent", "qwen3.5-27B", {"profile": "chess-profile"})),
        ("hermes:chess", ("hermes", None, {"profile": "chess"})),
        ("hermes:default", ("hermes", None, {"profile": "default"})),
    ]
    
    for spec, expected in test_cases:
        result = parse_agent_harness_spec(spec)
        if result == expected:
            print(f"✅ {spec} -> {result}")
        else:
            print(f"❌ {spec} -> {result} (expected {expected})")
            return False
    
    return True


def test_is_agent_harness_spec():
    """Test the is_agent_harness_spec function."""
    print("\n🧪 Testing is_agent_harness_spec...")
    
    from agents.agent_player_integration import is_agent_harness_spec
    
    test_cases = [
        ("hermes:qwen3.5-27B", True),
        ("opencode-agent:deepseek-v4", True),
        ("vibe-cli:mistral-medium", True),
        ("hermes", True),
        ("opencode", True),
        ("vibe-cli", True),
        ("opencode-go/deepseek-v4-pro", False),
        ("stockfish", False),
        ("human", False),
        ("random", False),
    ]
    
    for spec, expected in test_cases:
        result = is_agent_harness_spec(spec)
        if result == expected:
            print(f"✅ {spec} -> {result}")
        else:
            print(f"❌ {spec} -> {result} (expected {expected})")
            return False
    
    return True


def test_parse_player():
    """Test the updated parse_player function."""
    print("\n🧪 Testing parse_player...")
    
    from chess_llm import parse_player
    
    test_cases = [
        ("hermes:qwen3.5-27B", ("agent_harness", {"spec": "hermes:qwen3.5-27B", "harness_name": "hermes", "model": "qwen3.5-27B"})),
        ("opencode-agent:deepseek-v4-flash-free", ("agent_harness", {"spec": "opencode-agent:deepseek-v4-flash-free", "harness_name": "opencode-agent", "model": "deepseek-v4-flash-free"})),
        ("vibe-cli:mistral-medium-3.5", ("agent_harness", {"spec": "vibe-cli:mistral-medium-3.5", "harness_name": "vibe-cli", "model": "mistral-medium-3.5"})),
        ("stockfish", ("stockfish", {"name": "Stockfish", "skill": 20})),
        ("human", ("human", {"name": "Human"})),
        ("random", ("random", {"name": "Random"})),
    ]
    
    for spec, expected in test_cases:
        result = parse_player(spec)
        if result == expected:
            print(f"✅ {spec} -> {result[0]}")
        else:
            print(f"❌ {spec} -> {result} (expected {expected})")
            return False
    
    return True


def test_game_state():
    """Test the GameState class."""
    print("\n🧪 Testing GameState...")
    
    import chess
    from agents.harnesses.base import GameState
    
    # Create a board with some moves
    board = chess.Board()
    board.push_uci("e2e4")  # White move 1
    board.push_uci("e7e5")  # Black move 1
    # Now it's White's turn again
    
    # Create game state
    game_state = GameState.from_board(board, "test-agent", "game-123")
    
    # Check properties
    if game_state.fen != board.fen():
        print(f"❌ FEN mismatch: {game_state.fen} != {board.fen()}")
        return False
    
    # After 2 moves (e4, e5), it should be White's turn
    if game_state.color != "white":
        print(f"❌ Color mismatch: {game_state.color} != white")
        return False
    
    # move_number counts individual moves (plies), so after 2 moves it should be 3
    # (next move will be the 3rd ply: White's second move)
    if game_state.move_number != 3:
        print(f"❌ Move number mismatch: {game_state.move_number} != 3")
        return False
    
    if len(game_state.legal_moves) == 0:
        print("❌ No legal moves found")
        return False
    
    print(f"✅ GameState created successfully")
    print(f"   FEN: {game_state.fen}")
    print(f"   Color: {game_state.color}")
    print(f"   Move #: {game_state.move_number}")
    print(f"   Legal moves: {len(game_state.legal_moves)}")
    print(f"   Phase: {game_state.phase}")
    
    return True


def test_hermes_profile_support():
    """Test Hermes profile support in harness creation."""
    print("\n🧪 Testing Hermes profile support...")
    
    from agents.harnesses.hermes import HermesAgentHarness
    from agents.harnesses.base import GameState
    import chess
    
    # Mock the CLI verification to test command building
    class MockHermesHarness(HermesAgentHarness):
        def _verify_cli_available(self):
            # Skip CLI verification for testing
            pass
        
        def _get_move_cli(self, game_state, timeout):
            # Build the command without actually executing it
            # This mimics the real method but returns the command string
            prompt = self.build_prompt(game_state)
            system_prompt = self._get_system_prompt()
            
            cmd = [self.cli_command]
            
            # Add profile if specified (hermes -p <profile>)
            if self.profile:
                cmd.extend(['-p', self.profile])
            
            # Add model and other parameters
            cmd.extend([
                '--model', self.model or 'default',
                '--prompt', prompt,
                '--system', system_prompt,
                '--temperature', str(self.temperature),
                '--max-tokens', '256'
            ])
            
            # Add skill if specified
            if self.skill_name:
                cmd.extend(['--skill', self.skill_name])
            
            # Add reasoning if specified
            if self.reasoning:
                cmd.extend(['--reasoning', self.reasoning])
            
            return ' '.join(cmd)
    
    # Create a test board
    board = chess.Board()
    game_state = GameState.from_board(board, agent_id='test', game_id='test-game')
    
    # Test cases for profile support
    test_cases = [
        {
            'kwargs': {'model': 'qwen3.5-27B', 'profile': 'chess', 'use_cli': True, 'cli_command': 'hermes'},
            'expected_profile': 'chess',
            'expected_model': 'qwen3.5-27B',
            'should_contain': ['-p', 'chess', '--model', 'qwen3.5-27B']
        },
        {
            'kwargs': {'model': 'qwen3.5-27B', 'profile': None, 'use_cli': True, 'cli_command': 'hermes'},
            'expected_profile': None,
            'expected_model': 'qwen3.5-27B',
            'should_contain': ['--model', 'qwen3.5-27B'],
            'should_not_contain': ['-p']
        },
        {
            'kwargs': {'model': None, 'profile': 'chess-profile', 'use_cli': True, 'cli_command': 'hermes'},
            'expected_profile': 'chess-profile',
            'expected_model': None,  # Model remains None until CLI command building
            'should_contain': ['-p', 'chess-profile', '--model', 'default']
        },
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        try:
            harness = MockHermesHarness(**test_case['kwargs'])
            cmd = harness._get_move_cli(game_state, 120)
            
            # Check profile
            if harness.profile != test_case['expected_profile']:
                print(f"❌ Test {i}: Profile mismatch: {harness.profile} != {test_case['expected_profile']}")
                return False
            
            # Check model
            if harness.model != test_case['expected_model']:
                print(f"❌ Test {i}: Model mismatch: {harness.model} != {test_case['expected_model']}")
                return False
            
            # Check command contains expected parts
            for part in test_case.get('should_contain', []):
                if part not in cmd:
                    print(f"❌ Test {i}: Command missing '{part}': {cmd}")
                    return False
            
            # Check command doesn't contain unwanted parts (as whole words)
            for part in test_case.get('should_not_contain', []):
                if f' {part} ' in cmd or cmd.startswith(part + ' ') or cmd.endswith(' ' + part):
                    print(f"❌ Test {i}: Command contains unwanted '{part}': {cmd}")
                    return False
            
            print(f"✅ Test {i}: Profile={test_case['expected_profile']}, Model={test_case['expected_model']}")
            
        except Exception as e:
            print(f"❌ Test {i} Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True


def test_harness_creation():
    """Test harness creation (without actual agent connections)."""
    print("\n🧪 Testing harness creation...")
    
    from agents.harnesses import get_harness
    
    # Test that we can create harness instances
    # These will fail connectivity tests but should create the objects
    try:
        # Test with use_cli=True to avoid server connectivity
        # These may fail if the commands are not installed, but that's expected
        try:
            harness = get_harness("hermes", "qwen3.5-27B", use_cli=True)
            print(f"✅ Hermes harness created: {harness}")
        except FileNotFoundError:
            print("⚠️  Hermes command not found (expected if not installed)")
        
        try:
            harness = get_harness("opencode", "deepseek-v4-flash-free", use_cli=True)
            print(f"✅ OpenCode harness created: {harness}")
        except FileNotFoundError:
            print("⚠️  OpenCode command not found (expected if not installed)")
        
        try:
            harness = get_harness("vibe-cli", "mistral-medium-3.5", use_cli=True)
            print(f"✅ Vibe CLI harness created: {harness}")
        except FileNotFoundError:
            print("⚠️  Vibe CLI command not found (expected if not installed)")
        
        # Test that we can create harness objects even if commands aren't found
        # by using server mode (which will fail connectivity but create objects)
        try:
            harness = get_harness("hermes", "qwen3.5-27B", use_cli=False, endpoint="http://localhost:8080")
            print(f"✅ Hermes harness object created (server mode): {harness}")
        except FileNotFoundError:
            print("⚠️  Hermes command not found (expected if not installed)")
        
        try:
            harness = get_harness("opencode", "deepseek-v4-flash-free", use_cli=False, endpoint="http://localhost:8081")
            print(f"✅ OpenCode harness object created (server mode): {harness}")
        except FileNotFoundError:
            print("⚠️  OpenCode command not found (expected if not installed)")
        
        try:
            harness = get_harness("vibe-cli", "mistral-medium-3.5", use_cli=False, endpoint="http://localhost:8082")
            print(f"✅ Vibe CLI harness object created (server mode): {harness}")
        except FileNotFoundError:
            print("⚠️  Vibe CLI command not found (expected if not installed)")
        
        return True
        
    except Exception as e:
        print(f"❌ Harness creation failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Starting Agent Harness Integration Tests\n")
    
    tests = [
        test_imports,
        test_parse_agent_harness_spec,
        test_hermes_profile_support,
        test_is_agent_harness_spec,
        test_parse_player,
        test_game_state,
        test_harness_creation,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ {test.__name__} failed")
        except Exception as e:
            print(f"❌ {test.__name__} failed with exception: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())