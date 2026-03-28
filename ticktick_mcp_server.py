#!/usr/bin/env python3
"""
TickTick MCP Server
Wraps ticktick_api.py as an MCP server so Claude (Desktop/Code) can manage tasks directly.
Uses stdio transport — launched as a subprocess by the MCP host.
"""

import json
import sys
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Add parent dir to path so we can import our existing modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ticktick_auth import get_valid_token
from ticktick_api import TickTickClient

# ── Initialize MCP Server ──────────────────────────────────────

mcp = FastMCP(
    name="ticktick",
    instructions=(
        "TickTick task management server. Use these tools to manage tasks and projects "
        "in the user's TickTick account. Always confirm destructive actions (delete, complete) "
        "with the user before executing."
    ),
)


def _get_client() -> TickTickClient:
    """Get an authenticated TickTick API client."""
    token = get_valid_token()
    return TickTickClient(token)


# ── Tools ───────────────────────────────────────────────────────


@mcp.tool()
def list_projects() -> str:
    """
    List all TickTick projects (lists).
    Returns project names and IDs which are needed for other operations.
    """
    with _get_client() as client:
        projects = client.list_projects()

    if not projects:
        return "No projects found."

    lines = []
    for p in projects:
        kind = p.get("kind", "TASK")
        lines.append(f"- {p.get('name', '?')} (id: {p.get('id', '?')}, kind: {kind})")

    return f"Found {len(projects)} projects:\n" + "\n".join(lines)


@mcp.tool()
def list_tasks(project_name: Optional[str] = None) -> str:
    """
    List tasks. If project_name is provided, lists tasks from that project only.
    Otherwise lists ALL tasks across all projects.

    Args:
        project_name: Optional project/list name to filter by (e.g. "Work", "Inbox")
    """
    with _get_client() as client:
        if project_name:
            proj = client.find_project_by_name(project_name)
            if not proj:
                return f"Project '{project_name}' not found. Use list_projects to see available projects."

            data = client.get_project(proj["id"])
            tasks = data.get("tasks", [])
            header = f"Tasks in '{proj['name']}' ({len(tasks)} total):"
        else:
            tasks = client.list_all_tasks()
            header = f"All tasks ({len(tasks)} total):"

    if not tasks:
        return "No tasks found."

    lines = [header]
    for t in sorted(tasks, key=lambda x: x.get("priority", 0), reverse=True):
        priority_labels = {0: "none", 1: "low", 3: "medium", 5: "high"}
        pri = priority_labels.get(t.get("priority", 0), "none")
        due = t.get("dueDate", "")[:10] if t.get("dueDate") else "no due date"
        tags = ", ".join(t.get("tags", [])) if t.get("tags") else ""
        proj_name = t.get("_projectName", "")

        line = f"- [{pri}] {t.get('title', 'Untitled')}"
        if due != "no due date":
            line += f" (due: {due})"
        if tags:
            line += f" [tags: {tags}]"
        if proj_name:
            line += f" [{proj_name}]"
        line += f"\n  project_id: {t.get('projectId', '?')}, task_id: {t.get('id', '?')}"
        lines.append(line)

    return "\n".join(lines)


@mcp.tool()
def create_task(
    title: str,
    project_name: Optional[str] = None,
    content: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """
    Create a new task in TickTick.

    Args:
        title: Task title (required)
        project_name: Project/list name to add to (default: Inbox). Use list_projects to find names.
        content: Task description or notes
        due_date: Due date — accepts "today", "tomorrow", or ISO date like "2026-04-01"
        priority: Priority level — "none", "low", "medium", or "high"
        tags: Comma-separated tags, e.g. "work,urgent"
    """
    priority_map = {"none": 0, "low": 1, "medium": 3, "high": 5}
    pri_int = priority_map.get((priority or "none").lower(), 0)
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    with _get_client() as client:
        project_id = None
        if project_name:
            proj = client.find_project_by_name(project_name)
            if proj:
                project_id = proj["id"]
            else:
                return f"Project '{project_name}' not found. Use list_projects to see available projects."

        task = client.create_task(
            title=title,
            project_id=project_id,
            content=content,
            due_date=due_date,
            priority=pri_int,
            tags=tag_list,
        )

    result = f"Task created: '{task.get('title')}'"
    result += f"\n  task_id: {task.get('id')}"
    result += f"\n  project_id: {task.get('projectId')}"
    if due_date:
        result += f"\n  due: {due_date}"
    if priority:
        result += f"\n  priority: {priority}"
    return result


@mcp.tool()
def update_task(
    task_id: str,
    project_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """
    Update an existing task. Requires both task_id and project_id (get these from list_tasks).

    Args:
        task_id: The task ID to update (from list_tasks)
        project_id: The project ID the task belongs to (from list_tasks)
        title: New title for the task
        content: New description/notes
        due_date: New due date — "today", "tomorrow", or ISO date
        priority: New priority — "none", "low", "medium", or "high"
        tags: New comma-separated tags (replaces existing)
    """
    priority_map = {"none": 0, "low": 1, "medium": 3, "high": 5}
    updates = {}

    if title:
        updates["title"] = title
    if content:
        updates["content"] = content
    if due_date:
        updates["due_date"] = due_date
    if priority:
        updates["priority"] = priority_map.get(priority.lower(), 0)
    if tags:
        updates["tags"] = [t.strip() for t in tags.split(",")]

    if not updates:
        return "No updates specified. Provide at least one field to update."

    with _get_client() as client:
        result = client.update_task(task_id, project_id, **updates)

    return f"Task updated: '{result.get('title')}' (id: {result.get('id')})"


@mcp.tool()
def complete_task(project_id: str, task_id: str) -> str:
    """
    Mark a task as complete. Requires both project_id and task_id (get these from list_tasks).

    Args:
        project_id: The project ID the task belongs to
        task_id: The task ID to complete
    """
    with _get_client() as client:
        client.complete_task(project_id, task_id)

    return f"Task {task_id} marked as complete."


@mcp.tool()
def delete_task(project_id: str, task_id: str) -> str:
    """
    Delete a task permanently. Requires both project_id and task_id (get these from list_tasks).
    This action cannot be undone.

    Args:
        project_id: The project ID the task belongs to
        task_id: The task ID to delete
    """
    with _get_client() as client:
        client.delete_task(project_id, task_id)

    return f"Task {task_id} deleted."


@mcp.tool()
def get_project_details(project_name: str) -> str:
    """
    Get detailed info about a specific project including all its tasks.

    Args:
        project_name: The project/list name to look up
    """
    with _get_client() as client:
        proj = client.find_project_by_name(project_name)
        if not proj:
            return f"Project '{project_name}' not found."

        data = client.get_project(proj["id"])

    tasks = data.get("tasks", [])
    result = f"Project: {proj.get('name')}\n"
    result += f"  ID: {proj.get('id')}\n"
    result += f"  Tasks: {len(tasks)}\n"

    if tasks:
        result += "\nTasks:\n"
        for t in tasks:
            status = "completed" if t.get("status", 0) == 2 else "active"
            result += f"  - {t.get('title', 'Untitled')} ({status}, id: {t.get('id')})\n"

    return result


# ── Entry Point ─────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()