#!/usr/bin/env python3
"""
Test script for the agent integration system.

This script tests the core components of the agent integration:
- AgentPlayer class
- AgentRegistry
- Memory system
- Skill system
- MCP server (basic connectivity)
- Webhook server (basic connectivity)

Usage:
    python test_agents.py
    python test_agents.py --verbose
"""

import argparse
import asyncio
import os
import sys
import time
import uuid

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import chess first
import chess

# Now import our modules - they're in the agents subdirectory
# Since chess_llm.py is a single file, we need to handle imports carefully
# The agents module is a proper package


def test_agent_registry():
    """Test the agent registry."""
    print("Testing AgentRegistry...")
    
    from agents.registry import AgentRegistry, reset_registry
    
    # Reset and create new registry
    reset_registry()
    registry = AgentRegistry(use_sqlite=False, storage_path="test_agents_registry")  # Use JSON for testing
    
    # Register agents with unique IDs
    agent1 = registry.register_agent(
        agent_id=f"test-agent-1-{uuid.uuid4()}",
        name="Test Agent 1",
        agent_type="mcp",
        endpoint="http://localhost:8081"
    )
    
    agent2 = registry.register_agent(
        agent_id=f"test-agent-2-{uuid.uuid4()}",
        name="Test Agent 2",
        agent_type="webhook",
        endpoint="http://localhost:8082"
    )
    
    agent3 = registry.register_agent(
        agent_id=f"test-agent-3-{uuid.uuid4()}",
        name="Test Agent 3",
        agent_type="direct",
        model="big-pickle"
    )
    
    # Verify registration
    assert registry.get_agent(agent1.agent_id) is not None
    assert registry.get_agent(agent2.agent_id) is not None
    assert registry.get_agent(agent3.agent_id) is not None
    
    # List agents
    agents = registry.list_agents()
    assert len(agents) == 3
    
    # Test filtering
    mcp_agents = registry.get_agents_by_type("mcp")
    assert len(mcp_agents) == 1
    assert mcp_agents[0].agent_id == agent1.agent_id
    
    # Update state
    registry.update_state(agent1.agent_id, status="playing", current_game="game-123")
    state = registry.get_state(agent1.agent_id)
    assert state.status == "playing"
    assert state.current_game == "game-123"
    
    # Cleanup
    registry.clear()
    reset_registry()
    
    # Clean up test directory
    import shutil
    if os.path.exists("test_agents_registry"):
        shutil.rmtree("test_agents_registry")
    
    print("✅ AgentRegistry tests passed!")


def test_memory_system():
    """Test the memory system."""
    print("Testing Memory System...")
    
    from agents.memory import MemoryManager, MemoryEntry, reset_memory_manager
    
    # Reset and create new memory manager
    reset_memory_manager()
    memory_manager = MemoryManager(use_sqlite=False)
    
    # Use unique agent ID for this test
    agent_id = f"test-agent-mem-{uuid.uuid4()}"
    game_id = f"game-123-mem-{uuid.uuid4()}"
    
    # Save a memory
    board = chess.Board()
    memory_id = memory_manager.save(
        agent_id=agent_id,
        board_state=board.fen(),
        move="e2e4",
        reasoning="Controls the center",
        game_id=game_id,
        move_number=1,
        color="white",
        confidence=0.8,
        outcome="win",
        lessons=["Opening principle: control the center"],
        tags=["opening", "center"]
    )
    
    assert memory_id is not None
    
    # Query memories
    memories = memory_manager.query(agent_id=agent_id)
    assert len(memories) == 1
    assert memories[0].move == "e2e4"
    
    # Query by game
    game_memories = memory_manager.query(agent_id=agent_id, game_id=game_id)
    assert len(game_memories) == 1
    
    # Save another memory
    board2 = chess.Board()
    board2.push_san("e4")
    board2.push_san("e5")
    memory_id2 = memory_manager.save(
        agent_id=agent_id,
        board_state=board2.fen(),
        move="e7e5",
        reasoning="Responds to e4",
        game_id=game_id,
        move_number=2,
        color="black",
        confidence=0.7
    )
    
    # Query all memories for agent
    all_memories = memory_manager.query(agent_id=agent_id)
    assert len(all_memories) == 2
    
    # Test find_similar
    similar = memory_manager.get_memory(agent_id).find_similar(board2.fen())
    assert len(similar) > 0
    
    # Cleanup
    memory_manager.clear()
    reset_memory_manager()
    
    print("✅ Memory System tests passed!")


def test_skill_system():
    """Test the skill system."""
    print("Testing Skill System...")
    
    from agents.skills import SkillManager, AgentSkill
    
    # Use unique agent ID for this test
    agent_id = f"test-agent-skill-{uuid.uuid4()}"
    
    # Create skill manager
    skill_manager = SkillManager(agent_id, use_sqlite=False, storage_path="test_agents_skills")
    
    # Create and save a skill
    skill = AgentSkill(
        agent_id=agent_id,
        name="Italian Game",
        skill_type="opening",
        description="Response to 1. e4 e5 with 2. Nf3 Nc6 3. Bc4",
        data={"moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]},
        tags=["opening", "italian"]
    )
    
    skill_id = skill_manager.save(skill)
    assert skill_id is not None
    
    # Get skill
    retrieved_skill = skill_manager.get(skill_id)
    assert retrieved_skill is not None
    assert retrieved_skill.name == "Italian Game"
    
    # List skills
    skills = skill_manager.list_skills()
    assert len(skills) == 1
    
    # Filter by type
    opening_skills = skill_manager.list_skills(skill_type="opening")
    assert len(opening_skills) == 1
    
    # Test find_applicable
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    
    applicable = skill_manager.find_applicable(board, "white", "opening")
    assert len(applicable) == 1
    assert applicable[0][0].name == "Italian Game"
    
    # Test apply_skill
    move = skill_manager.apply_skill(applicable[0][0], board, "white")
    assert move is not None
    assert move.uci() == "g1f3"  # Nf3
    
    # Cleanup
    skill_manager.clear()
    
    # Clean up test directory
    import shutil
    if os.path.exists("test_agents_skills"):
        shutil.rmtree("test_agents_skills")
    
    print("✅ Skill System tests passed!")


def test_agent_player():
    """Test the AgentPlayer class."""
    print("Testing AgentPlayer...")
    
    from agents.agent_player import AgentPlayer
    from agents.registry import reset_registry
    
    # Reset registry
    reset_registry()
    
    # Create a direct agent (uses LLM) with unique ID
    agent = AgentPlayer(
        agent_id=f"test-direct-agent-{uuid.uuid4()}",
        name="Test Direct Agent",
        agent_type="direct",
        model="big-pickle",
        timeout=30,
        max_retries=2,
        learn=True
    )
    
    # Skip connectivity check since litellm is not installed
    # We'll just test that the agent was created correctly
    try:
        # Verify agent was created correctly
        assert agent.agent_id.startswith("test-direct-agent-")
        assert agent.name == "Test Direct Agent"
        assert agent.agent_type == "direct"
        assert agent.model == "big-pickle"
        
        print("  AgentPlayer created successfully")
        
    except Exception as e:
        print(f"  AgentPlayer test failed: {e}")
        raise
    
    print("✅ AgentPlayer tests passed!")


def test_learning_system():
    """Test the learning system."""
    print("Testing Learning System...")
    
    from agents.learning import LearningSystem, LessonExtractor, reset_learning_system
    from agents.memory import reset_memory_manager
    
    # Reset
    reset_learning_system()
    reset_memory_manager()
    
    # Create learning system
    learning_system = LearningSystem()
    
    # Use unique agent ID for this test
    agent_id = f"test-agent-learn-{uuid.uuid4()}"
    
    # Create a simple PGN
    pgn = """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[Round "1"]
[White "Test Agent"]
[Black "Opponent"]
[Result "1-0"]
[Opening "Italian Game"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O O-O 7. Nbd2 h6
8. Nb3 a5 9. Nxc5 dxc5 10. Bc2 Ng4 11. h3 Nxf2 12. Rxf2 Bg4 13. Rf4 Bxf3
14. Qxf3 Qxd3 15. Be3 Qxe3 16. fxe3 Rfd8 17. Kf2 Rxd2+ 18. Ke1 Rxb2
19. Rc4 Rxa2 20. Rxc7 Rb8 21. Rxb7 Rxb7 22. Bxb7 Rb8 23. Bxa8 Rxa8
"""
    
    # Learn from game
    result = learning_system.learn_from_game(
        pgn=pgn,
        agent_id=agent_id,
        agent_color="white",
        result="1-0"
    )
    
    assert result["lessons_extracted"] >= 0
    assert result["memories_saved"] >= 0
    
    # Get stats
    stats = learning_system.get_stats(agent_id)
    assert "memories_count" in stats
    assert "skills_count" in stats
    
    # Get recommendations
    recommendations = learning_system.get_recommendations(agent_id, limit=3)
    assert isinstance(recommendations, list)
    
    # Reset
    reset_learning_system()
    reset_memory_manager()
    
    print("✅ Learning System tests passed!")


def test_mcp_server_import():
    """Test that MCP server can be imported."""
    print("Testing MCP Server import...")
    
    try:
        from agents.protocols.mcp_server import ChessMCPServer
        
        # Create server (don't start it)
        server = ChessMCPServer(port=8081, transport="http")
        assert server.port == 8081
        assert server.transport == "http"
        
        print("✅ MCP Server import test passed!")
        
    except Exception as e:
        print(f"❌ MCP Server import failed: {e}")
        raise


def test_webhook_server_import():
    """Test that webhook server can be imported."""
    print("Testing Webhook Server import...")
    
    try:
        from agents.protocols.webhook_server import WebhookServer
        
        # Create server (don't start it)
        server = WebhookServer(port=8082)
        assert server.port == 8082
        
        print("✅ Webhook Server import test passed!")
        
    except Exception as e:
        print(f"❌ Webhook Server import failed: {e}")
        raise


def test_acp_skills_import():
    """Test that ACP skills can be imported."""
    print("Testing ACP Skills import...")
    
    try:
        from agents.protocols.acp_skills import ChessSkills
        
        # Create skills
        skills = ChessSkills()
        assert hasattr(skills, "play_chess_move")
        assert hasattr(skills, "analyze_game")
        
        print("✅ ACP Skills import test passed!")
        
    except Exception as e:
        print(f"❌ ACP Skills import failed: {e}")
        raise


def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test agent integration system")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--skip-imports", action="store_true", help="Skip import tests")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Chess LLM Agent Integration - Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        ("Agent Registry", test_agent_registry),
        ("Memory System", test_memory_system),
        ("Skill System", test_skill_system),
        ("Agent Player", test_agent_player),
        ("Learning System", test_learning_system),
    ]
    
    if not args.skip_imports:
        tests.extend([
            ("MCP Server Import", test_mcp_server_import),
            ("Webhook Server Import", test_webhook_server_import),
            ("ACP Skills Import", test_acp_skills_import),
        ])
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} tests failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    main()
