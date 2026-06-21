# OpenCode Chess Agent - SYSTEM.md

## System Configuration & Constraints

### Technical Requirements

#### Minimum Requirements
- **OpenCode Version**: 1.0.0 or higher
- **Python Version**: 3.9 or higher
- **Memory**: 4GB RAM minimum, 8GB+ recommended
- **Storage**: 1GB for logs and game data
- **Network**: Internet access for API calls (if using cloud models)

#### Recommended Configuration
- **OpenCode Version**: Latest stable release
- **Python Version**: 3.11 or higher
- **Memory**: 16GB+ for optimal performance
- **GPU**: CUDA-enabled GPU for local models
- **Network**: High-speed internet for cloud APIs

### Model Configuration

#### Supported Model Types
- **Cloud Models**: OpenRouter, OpenAI, Anthropic, etc.
- **Local Models**: Ollama, vLLM, llama.cpp, etc.
- **OpenCode Zen**: Native OpenCode models
- **Custom Models**: Any model compatible with OpenCode

#### Model Selection Guidelines

| Model Size | Use Case | Temperature | Max Tokens | Reasoning |
|------------|----------|-------------|------------|-----------|
| < 10B | Fast games, bulk testing | 0.1-0.3 | 512-1024 | None |
| 10-30B | Standard games | 0.1-0.3 | 1024-2048 | Low |
| 30-70B | Competitive games | 0.1-0.2 | 2048-4096 | Medium |
| > 70B | High-level analysis | 0.1-0.2 | 4096+ | High |

#### Reasoning Configuration
- **None**: Fastest response, basic analysis
- **Low**: Quick reasoning, good for most games
- **Medium**: Deep analysis, better for complex positions
- **High**: Maximum depth, best for critical moves

### Performance Optimization

#### Token Management
- **Prompt Tokens**: Keep under 2000 for most models
- **Completion Tokens**: 256-512 for move generation
- **Total Budget**: Monitor total token usage per game
- **Caching**: Enable caching for repeated positions

#### Time Management
- **Move Timeout**: 30-120 seconds depending on model speed
- **Retry Timeout**: Exponential backoff for retries
- **Total Game Time**: Monitor and respect time controls

#### Resource Allocation
- **CPU**: Use multiple cores for parallel processing
- **GPU**: Offload to GPU when available
- **Memory**: Cache frequently accessed data

### Security & Safety

#### Data Protection
- **API Keys**: Never expose in logs or responses
- **Game Data**: Store securely with proper access controls
- **Personal Information**: Never collect or store personal data

#### Input Validation
- **FEN Validation**: Verify FEN strings are valid
- **Move Validation**: Check moves against legal move list
- **Format Validation**: Ensure proper data formats

#### Error Handling
- **Graceful Degradation**: Continue with fallback methods
- **Clear Error Messages**: Provide actionable error information
- **Recovery**: Automatic recovery from transient errors

### Integration Points

#### Chess Engine Integration
- **python-chess**: Primary chess library
- **PGN Support**: Standard chess notation
- **FEN Support**: Board state representation
- **UCI Support**: Move notation standard

#### Agent Framework Integration
- **OpenCode Core**: Primary agent framework
- **Tool System**: Chess-specific tools and functions
- **Memory System**: Game history and learning
- **Skill System**: Chess skill development

### Monitoring & Logging

#### Metrics to Track
- **Move Generation Time**: Time to generate each move
- **Token Usage**: Tokens used per move and per game
- **Win Rate**: Percentage of games won
- **Error Rate**: Frequency of errors and timeouts
- **Retry Rate**: Number of retries per game

#### Log Levels
- **DEBUG**: Detailed debugging information
- **INFO**: Standard operational information
- **WARNING**: Potential issues and concerns
- **ERROR**: Errors that need attention
- **CRITICAL**: Critical failures

#### Log Retention
- **Debug Logs**: 7 days
- **Game Logs**: 30 days
- **Error Logs**: 90 days
- **Metrics**: Permanent storage

### Network Configuration

#### API Endpoints
- **Primary**: Main OpenCode API endpoint
- **Fallback**: Backup endpoints for redundancy
- **Timeout**: 30-60 seconds for API calls
- **Retries**: 3-5 retries for failed requests

#### Proxy Support
- **HTTP Proxy**: Configure for corporate networks
- **SOCKS Proxy**: Support for SOCKS proxies
- **Authentication**: Proxy authentication support

### Environment Variables

#### Required Variables
- **OPENAI_API_KEY**: API key for OpenAI models
- **OPENROUTER_API_KEY**: API key for OpenRouter
- **ANTHROPIC_API_KEY**: API key for Anthropic
- **OPENCODE_API_KEY**: API key for OpenCode services

#### Optional Variables
- **OPENCODE_BASE_URL**: Custom OpenCode API URL
- **OPENCODE_TIMEOUT**: Custom timeout in seconds
- **OPENCODE_MAX_RETRIES**: Custom retry count
- **CHESS_DEBUG**: Enable debug logging

### File System

#### Directory Structure
```
chess-llm/
├── agents/
│   ├── profiles/
│   │   └── opencode-agent/
│   │       ├── SOUL.md
│   │       ├── USER.md
│   │       ├── SYSTEM.md
│   │       └── config.yaml
│   └── harnesses/
├── games/
│   └── *.pgn
├── logs/
│   ├── debug/
│   ├── games/
│   └── errors/
└── data/
    ├── memory/
    └── skills/
```

#### File Permissions
- **Profiles**: Read-only for agents
- **Games**: Read/write for game storage
- **Logs**: Read/write for logging
- **Data**: Read/write for memory and skills

---

### Configuration Example

```yaml
# config.yaml for OpenCode Chess Agent
model: "deepseek-v4-flash-free"
temperature: 0.2
max_tokens: 512
reasoning: "medium"
timeout: 60
max_retries: 3
use_tools: true

# OpenCode specific settings
opencode:
  base_url: "https://api.opencode.ai"
  api_key: "${OPENCODE_API_KEY}"
  
# Chess specific settings
chess:
  legal_move_only: true
  uci_format: true
  move_validation: true
  
# Performance settings
performance:
  cache_enabled: true
  parallel_games: 4
  token_budget: 8192
```

---

**Version**: 1.0  
**Last Updated**: 2024  
**Agent Type**: OpenCode Chess Agent