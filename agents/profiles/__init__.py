"""
Agent Profiles for LLM Chess

This directory contains configuration files for different agent harnesses:
- opencode-agent/ - OpenCode Agent profiles
- hermes-agent/ - Hermes Agent profiles  
- vibe-cli/ - Vibe CLI profiles

Each profile includes:
- SOUL.md - Agent's purpose, goals, and identity
- USER.md - User instructions and preferences
- SYSTEM.md - System configuration and constraints
- config.yaml - Technical configuration
"""

import os
from pathlib import Path

# Profile directories
PROFILE_DIR = Path(__file__).parent
OPENCODE_PROFILE_DIR = PROFILE_DIR / "opencode-agent"
HERMES_PROFILE_DIR = PROFILE_DIR / "hermes-agent"
VIBE_PROFILE_DIR = PROFILE_DIR / "vibe-cli"

# Ensure profile directories exist
def ensure_profile_dirs():
    """Ensure all profile directories exist."""
    for profile_dir in [OPENCODE_PROFILE_DIR, HERMES_PROFILE_DIR, VIBE_PROFILE_DIR]:
        profile_dir.mkdir(parents=True, exist_ok=True)

# Profile file names
PROFILE_FILES = ["SOUL.md", "USER.md", "SYSTEM.md", "config.yaml"]

def get_profile_path(harness_name: str, file_name: str = None) -> Path:
    """
    Get the path to a profile file for a specific harness.
    
    Args:
        harness_name: Name of the harness ('opencode-agent', 'hermes-agent', 'vibe-cli')
        file_name: Name of the profile file (SOUL.md, USER.md, etc.)
        
    Returns:
        Path to the profile file
    """
    harness_map = {
        'opencode': OPENCODE_PROFILE_DIR,
        'opencode-agent': OPENCODE_PROFILE_DIR,
        'hermes': HERMES_PROFILE_DIR,
        'hermes-agent': HERMES_PROFILE_DIR,
        'vibe': VIBE_PROFILE_DIR,
        'vibe-cli': VIBE_PROFILE_DIR,
    }
    
    profile_dir = harness_map.get(harness_name.lower())
    if profile_dir is None:
        raise ValueError(f"Unknown harness: {harness_name}")
    
    if file_name:
        return profile_dir / file_name
    
    return profile_dir

def read_profile_file(harness_name: str, file_name: str) -> str:
    """
    Read a profile file for a specific harness.
    
    Args:
        harness_name: Name of the harness
        file_name: Name of the profile file
        
    Returns:
        Content of the profile file
    """
    profile_path = get_profile_path(harness_name, file_name)
    
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile file not found: {profile_path}")
    
    with open(profile_path, 'r', encoding='utf-8') as f:
        return f.read()

def load_profile_config(harness_name: str) -> dict:
    """
    Load the configuration for a specific harness.
    
    Args:
        harness_name: Name of the harness
        
    Returns:
        Configuration dictionary
    """
    import yaml
    
    config_path = get_profile_path(harness_name, "config.yaml")
    
    if not config_path.exists():
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

# Initialize profile directories
ensure_profile_dirs()