# CoHub Recruiting Plugin

Recruiting assistant skill and MCP servers for [CoHub/CoPaw](https://github.com/user/cohub).

## Features

- **Recruiting Assistant Skill**: AI-powered recruiting workflow for Chinese job platforms
- **Liepin MCP** (猎聘): Browser automation for liepin.com
- **BOSS MCP** (BOSS直聘): Browser automation for zhipin.com  
- **Zhaopin MCP** (智联招聘): Browser automation for zhaopin.com
- **Multi-site Tool Guard**: Prevents conflicting tool calls across all 3 sites
- **Match Reasoning**: AI-powered candidate match scoring

## Installation

```bash
pip install cohub-recruiting-plugin
```

Or for development:

```bash
cd cohub-recruiting-plugin
pip install -e ".[dev]"
```

## Setup

After installation, the plugin is automatically discovered by CoHub via the `copaw.skills` entry-point.

To configure MCP clients in your workspace:

```python
from cohub_recruiting.installer import install_recruiting_plugin

install_recruiting_plugin(
    workspace_dir="~/.copaw/workspaces/default",
)
```

## Architecture

The plugin registers hooks with CoHub's generic skill hook system:

- **Tool Block Hook**: Prevents browser_use/site tools after stop signals
- **Stop Context Hook**: Detects stop signals from MCP tool results
- **Latest Context Hook**: Finds the latest recruiting tool context
- **Stop Reply Hook**: Builds user-facing stop messages (Chinese)
- **Blocked Text Hook**: Builds blocked-tool response text
- **Summary Hook**: Extracts pre-rendered summary_markdown from tool output

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RECRUITING_ENABLED_SITES` | Comma-separated list of sites | `liepin` |
| `RECRUITING_SITE_FAILURE_MODE` | `partial_success` or `strict_all_sites` | `partial_success` |
| `RECRUITING_DEFAULT_PAGE` | Default page number | `1` |
| `RECRUITING_DEFAULT_RESULT_LIMIT` | Max candidates per search | `20` |
| `RECRUITING_MATCH_MODEL_PROVIDER` | Match reasoning model provider | (empty) |
| `RECRUITING_MATCH_MODEL` | Match reasoning model name | (empty) |
| `RECRUITING_MATCH_API_KEY` | Match reasoning API key | (empty) |
| `RECRUITING_MATCH_BASE_URL` | Match reasoning API base URL | (empty) |
| `BOSS_PROFILE_DIR` | BOSS browser profile directory | `~/.copaw/recruiting/boss-profile` |
| `BOSS_CDP_URL` | BOSS Chrome DevTools URL | (empty) |
| `ZHAOPIN_PROFILE_DIR` | Zhaopin browser profile directory | `~/.copaw/recruiting/zhaopin-profile` |
| `LIEPIN_PROFILE_DIR` | Liepin browser profile directory | `~/.copaw/recruiting/liepin-profile` |

## Bug Fixes (vs Original)

This plugin includes several fixes over the original embedded implementation:

1. **Multi-site tool guard**: Now handles BOSS and Zhaopin stop signals (was Liepin-only)
2. **Race condition protection**: AsyncIO locks on all MCP service public methods
3. **Browser session cleanup**: Proper cleanup on init failure (no more Playwright leaks)
4. **Client pooling**: Match reasoner reuses HTTP client instead of creating one per call
5. **Error logging**: Replaced silent `except Exception: pass` with proper logging
6. **Production safety**: Replaced `assert` statements with proper error checks
7. **BOSS validation**: Added `candidate_summary_is_reliable()` and `candidate_batch_is_reliable()`

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests  
pytest tests/ -v
```

## License

MIT
