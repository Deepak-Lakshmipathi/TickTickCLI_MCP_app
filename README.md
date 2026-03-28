# TickTick CLI & MCP Server

A lightweight Python CLI + MCP server for managing TickTick tasks. Use it from the terminal, or let Claude manage your tasks directly via MCP.

## Prerequisites

- Python 3.10+
- A TickTick account
- `httpx` and `mcp` libraries

## Setup

### 1. Register a TickTick App

1. Go to [developer.ticktick.com](https://developer.ticktick.com) and log in
2. Click **Manage Apps** → **+App Name**
3. Name it (e.g., "My CLI")
4. Set **OAuth Redirect URL** to: `http://localhost:8765/callback`
5. Save your **Client ID** and **Client Secret**

### 2. Install

```bash
cd TickTickCLI_MCP_app
pip install -r requirements.txt
```

### 3. Authenticate

```bash
python ticktick_cli.py setup YOUR_CLIENT_ID YOUR_CLIENT_SECRET
```

A browser window will open asking you to authorize. After approving, tokens are saved to `~/.config/ticktick-cli/config.json`. This only happens once — tokens auto-refresh.

---

## CLI Usage

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

---

## MCP Server (Claude Integration)

The MCP server wraps the same `ticktick_api.py` client and exposes it as tools that Claude can call directly.

### Claude Desktop

Add this to your `claude_desktop_config.json`:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`  
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "python3",
      "args": ["/full/path/to/TickTickCLI_MCP_app/ticktick_mcp_server.py"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add ticktick python3 /full/path/to/TickTickCLI_MCP_app/ticktick_mcp_server.py
```

### Available MCP Tools

#### Tasks

| Tool | Description |
|------|-------------|
| `list_tasks` | List tasks — all projects or filtered by project name |
| `get_task` | Get full details of a single task (subtasks, reminders, recurrence) |
| `create_task` | Create a task with title, project, due date, priority, and tags |
| `create_task_with_subtasks` | Create a checklist task with subtask items in one call |
| `update_task` | Update an existing task's fields |
| `complete_task` | Mark a task as complete |
| `delete_task` | Permanently delete a task |
| `move_task` | Move a task from one project to another |
| `list_completed_tasks` | List completed tasks with optional project and date range filter |
| `filter_tasks` | Advanced search — filter by project, priority, tags, status, and date range |

#### Projects

| Tool | Description |
|------|-------------|
| `list_projects` | List all TickTick projects with IDs |
| `get_project_details` | Get full project info with all its tasks |
| `create_project` | Create a new project with optional color and view mode |
| `update_project` | Rename, recolor, or change the view mode of a project |
| `delete_project` | Permanently delete a project and all its tasks |

### Example Prompts for Claude

Once connected, you can say things like:
- "Show me all my TickTick projects"
- "Create a task called 'Review PR #42' in my Work project, due tomorrow, high priority"
- "Create a checklist called 'Morning Routine' with subtasks: Make coffee, Check email, Review calendar"
- "What tasks do I have due this week?"
- "Show me everything I completed last week"
- "Find all high-priority tasks tagged 'urgent'"
- "Mark the grocery task as complete"
- "Move 'Design review' from Work to Personal"
- "Create a new project called 'Q2 Goals' with kanban view"
- "Rename my 'Misc' project to 'Someday'"

---

## Architecture

```
ticktick_auth.py       → OAuth flow, token storage & auto-refresh
ticktick_api.py        → Stateless API client (shared by CLI + MCP)
ticktick_cli.py        → CLI interface
ticktick_mcp_server.py → MCP server (wraps ticktick_api.py)
```

The `TickTickClient` class in `ticktick_api.py` is the shared core — both the CLI and MCP server import and use the same client. This keeps logic DRY and means any API improvements benefit both interfaces.

## Token Storage

Tokens are stored in `~/.config/ticktick-cli/config.json` with `600` permissions (owner-only read/write). The CLI/MCP server automatically refreshes expired tokens.