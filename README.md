# TickTick CLI

A lightweight CLI for managing TickTick tasks from the terminal. Designed to later be wrapped as an MCP server for use with Claude.

## Prerequisites

- Python 3.10+
- A TickTick account
- `httpx` library (`pip install httpx`)

## Setup

### 1. Register a TickTick App

1. Go to [developer.ticktick.com](https://developer.ticktick.com) and log in
2. Click **Manage Apps** → **+App Name**
3. Name it (e.g., "My CLI")
4. Set **OAuth Redirect URL** to: `http://localhost:8765/callback`
5. Save your **Client ID** and **Client Secret**

### 2. Install

```bash
cd ticktick-cli
pip install -r requirements.txt
chmod +x ticktick
```

### 3. Authenticate

```bash
python ticktick_cli.py setup YOUR_CLIENT_ID YOUR_CLIENT_SECRET
```

A browser window will open asking you to authorize. After approving, tokens are saved to `~/.config/ticktick-cli/config.json`.

## Usage

```bash
# List all projects
python ticktick_cli.py projects

# List all tasks
python ticktick_cli.py tasks

# List tasks from a specific project
python ticktick_cli.py tasks "Work"

# Create a task in Inbox
python ticktick_cli.py add "Buy groceries"

# Create a task with options
python ticktick_cli.py add "Review PR" --project "Work" --due tomorrow --priority high

# Complete a task
python ticktick_cli.py complete <project_id> <task_id>

# Delete a task
python ticktick_cli.py delete <project_id> <task_id>

# Update a task
python ticktick_cli.py update <task_id> --project <project_id> --title "New title" --due 2026-04-15
```

### Priority Levels

| Value | Meaning |
|-------|---------|
| 0 / none | No priority |
| 1 / low | Low |
| 3 / medium | Medium |
| 5 / high | High |

## Architecture

```
ticktick_auth.py  → OAuth flow, token storage & refresh
ticktick_api.py   → API client (reusable for MCP)
ticktick_cli.py   → CLI interface
```

The `TickTickClient` class in `ticktick_api.py` is intentionally stateless and clean — when you're ready to build the MCP server, you just import it and wire the same methods to MCP tool definitions.

## Token Storage

Tokens are stored in `~/.config/ticktick-cli/config.json` with `600` permissions (owner-only read/write). The CLI automatically refreshes expired tokens.
