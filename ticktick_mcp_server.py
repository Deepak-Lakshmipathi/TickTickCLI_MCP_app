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


@mcp.tool()
def get_task(project_id: str, task_id: str) -> str:
    """
    Get full details of a single task including subtasks, reminders, and recurrence.

    Args:
        project_id: The project ID the task belongs to (from list_tasks)
        task_id: The task ID to retrieve (from list_tasks)
    """
    with _get_client() as client:
        task = client.get_task(project_id, task_id)

    priority_labels = {0: "none", 1: "low", 3: "medium", 5: "high"}
    lines = [
        f"Title: {task.get('title', 'Untitled')}",
        f"  ID: {task.get('id')}",
        f"  Project ID: {task.get('projectId')}",
        f"  Status: {'completed' if task.get('status') == 2 else 'active'}",
        f"  Priority: {priority_labels.get(task.get('priority', 0), 'none')}",
    ]
    if task.get("content"):
        lines.append(f"  Content: {task['content']}")
    if task.get("desc"):
        lines.append(f"  Description: {task['desc']}")
    if task.get("startDate"):
        lines.append(f"  Start: {task['startDate'][:10]}")
    if task.get("dueDate"):
        lines.append(f"  Due: {task['dueDate'][:10]}")
    if task.get("tags"):
        lines.append(f"  Tags: {', '.join(task['tags'])}")
    if task.get("reminders"):
        lines.append(f"  Reminders: {', '.join(task['reminders'])}")
    if task.get("repeatFlag"):
        lines.append(f"  Repeat: {task['repeatFlag']}")
    if task.get("completedTime"):
        lines.append(f"  Completed: {task['completedTime'][:10]}")
    items = task.get("items", [])
    if items:
        lines.append(f"  Subtasks ({len(items)}):")
        for item in items:
            status_icon = "[x]" if item.get("status") == 1 else "[ ]"
            lines.append(f"    {status_icon} {item.get('title', 'Untitled')} (id: {item.get('id')})")
    return "\n".join(lines)


@mcp.tool()
def create_task_with_subtasks(
    title: str,
    subtasks: str,
    project_name: Optional[str] = None,
    content: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: Optional[str] = None,
) -> str:
    """
    Create a checklist task with subtask items in one call.

    Args:
        title: Task title (required)
        subtasks: Newline- or comma-separated list of subtask titles
        project_name: Project/list name (default: Inbox)
        content: Task description/notes
        due_date: Due date — "today", "tomorrow", or ISO date
        priority: "none", "low", "medium", or "high"
    """
    priority_map = {"none": 0, "low": 1, "medium": 3, "high": 5}
    pri_int = priority_map.get((priority or "none").lower(), 0)

    # Accept newline or comma separated
    sep = "\n" if "\n" in subtasks else ","
    item_titles = [s.strip() for s in subtasks.split(sep) if s.strip()]
    items = [{"title": t, "status": 0, "sortOrder": i * 1000} for i, t in enumerate(item_titles)]

    from ticktick_api import _normalize_date

    body: dict = {
        "title": title,
        "priority": pri_int,
        "items": items,
        "kind": "CHECKLIST",
    }
    if content:
        body["content"] = content
    if due_date:
        body["dueDate"] = _normalize_date(due_date)

    with _get_client() as client:
        if project_name:
            proj = client.find_project_by_name(project_name)
            if not proj:
                return f"Project '{project_name}' not found. Use list_projects to see available projects."
            body["projectId"] = proj["id"]

        r = client.http.post("/task", json=body)
        r.raise_for_status()
        task = r.json()

    result = f"Checklist task created: '{task.get('title')}' with {len(items)} subtasks"
    result += f"\n  task_id: {task.get('id')}"
    result += f"\n  project_id: {task.get('projectId')}"
    result += "\n  Subtasks: " + ", ".join(item_titles)
    return result


@mcp.tool()
def move_task(task_id: str, from_project_name: str, to_project_name: str) -> str:
    """
    Move a task from one project to another.

    Args:
        task_id: The task ID to move (from list_tasks)
        from_project_name: The source project name
        to_project_name: The destination project name
    """
    with _get_client() as client:
        from_proj = client.find_project_by_name(from_project_name)
        if not from_proj:
            return f"Source project '{from_project_name}' not found."

        to_proj = client.find_project_by_name(to_project_name)
        if not to_proj:
            return f"Destination project '{to_project_name}' not found."

        results = client.move_tasks([{
            "fromProjectId": from_proj["id"],
            "toProjectId": to_proj["id"],
            "taskId": task_id,
        }])

    return (
        f"Task {task_id} moved from '{from_project_name}' to '{to_project_name}'.\n"
        f"  New etag: {results[0].get('etag', '?') if results else '?'}"
    )


@mcp.tool()
def list_completed_tasks(
    project_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    List tasks that have been marked as completed, with optional filters.

    Args:
        project_name: Filter to a specific project (optional)
        start_date: Only show tasks completed on or after this date — "today", "yesterday", or ISO date
        end_date: Only show tasks completed on or before this date — ISO date
    """
    with _get_client() as client:
        project_ids = None
        if project_name:
            proj = client.find_project_by_name(project_name)
            if not proj:
                return f"Project '{project_name}' not found."
            project_ids = [proj["id"]]

        tasks = client.list_completed_tasks(
            project_ids=project_ids,
            start_date=start_date,
            end_date=end_date,
        )

    if not tasks:
        return "No completed tasks found for the given criteria."

    lines = [f"Completed tasks ({len(tasks)} total):"]
    for t in tasks:
        completed = t.get("completedTime", "")[:10] if t.get("completedTime") else "?"
        lines.append(
            f"- {t.get('title', 'Untitled')} (completed: {completed})\n"
            f"  project_id: {t.get('projectId')}, task_id: {t.get('id')}"
        )
    return "\n".join(lines)


@mcp.tool()
def filter_tasks(
    project_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """
    Advanced task search — filter by project, date range, priority, tags, and status.

    Args:
        project_name: Limit search to this project (optional)
        start_date: Tasks with startDate >= this date — ISO date or "today"
        end_date: Tasks with startDate <= this date — ISO date
        priority: Comma-separated priorities to include: "none", "low", "medium", "high"
        tags: Comma-separated tags — returns tasks that have ALL listed tags
        status: "open", "completed", or "open,completed" (default: open)
    """
    priority_map = {"none": 0, "low": 1, "medium": 3, "high": 5}
    status_map = {"open": 0, "completed": 2}

    priority_ints = None
    if priority:
        priority_ints = [priority_map[p.strip().lower()] for p in priority.split(",") if p.strip().lower() in priority_map]

    status_ints = None
    if status:
        status_ints = [status_map[s.strip().lower()] for s in status.split(",") if s.strip().lower() in status_map]
    else:
        status_ints = [0]  # default: open tasks

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    with _get_client() as client:
        project_ids = None
        if project_name:
            proj = client.find_project_by_name(project_name)
            if not proj:
                return f"Project '{project_name}' not found."
            project_ids = [proj["id"]]

        tasks = client.filter_tasks(
            project_ids=project_ids,
            start_date=start_date,
            end_date=end_date,
            priority=priority_ints,
            tag=tag_list,
            status=status_ints,
        )

    if not tasks:
        return "No tasks match the given filters."

    priority_labels = {0: "none", 1: "low", 3: "medium", 5: "high"}
    lines = [f"Matching tasks ({len(tasks)} total):"]
    for t in tasks:
        pri = priority_labels.get(t.get("priority", 0), "none")
        due = t.get("dueDate", "")[:10] if t.get("dueDate") else "no due date"
        tag_str = ", ".join(t.get("tags", []))
        line = f"- [{pri}] {t.get('title', 'Untitled')}"
        if due != "no due date":
            line += f" (due: {due})"
        if tag_str:
            line += f" [tags: {tag_str}]"
        line += f"\n  project_id: {t.get('projectId')}, task_id: {t.get('id')}"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool()
def create_project(
    name: str,
    color: Optional[str] = None,
    view_mode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    """
    Create a new project (list) in TickTick.

    Args:
        name: Project name (required)
        color: Hex color, e.g. "#F18181"
        view_mode: "list", "kanban", or "timeline"
        kind: "TASK" or "NOTE" (default: TASK)
    """
    with _get_client() as client:
        project = client.create_project(name=name, color=color, view_mode=view_mode, kind=kind)

    result = f"Project created: '{project.get('name')}'"
    result += f"\n  id: {project.get('id')}"
    if project.get("color"):
        result += f"\n  color: {project['color']}"
    result += f"\n  view_mode: {project.get('viewMode', 'list')}"
    result += f"\n  kind: {project.get('kind', 'TASK')}"
    return result


@mcp.tool()
def update_project(
    project_name: str,
    new_name: Optional[str] = None,
    color: Optional[str] = None,
    view_mode: Optional[str] = None,
) -> str:
    """
    Update a project's name, color, or view mode.

    Args:
        project_name: Current project name to update
        new_name: New name for the project
        color: New hex color, e.g. "#F18181"
        view_mode: New view mode — "list", "kanban", or "timeline"
    """
    updates = {}
    if new_name:
        updates["name"] = new_name
    if color:
        updates["color"] = color
    if view_mode:
        updates["viewMode"] = view_mode

    if not updates:
        return "No updates specified. Provide at least one of: new_name, color, view_mode."

    with _get_client() as client:
        proj = client.find_project_by_name(project_name)
        if not proj:
            return f"Project '{project_name}' not found."

        result = client.update_project(proj["id"], **updates)

    return f"Project updated: '{result.get('name')}' (id: {result.get('id')})"


@mcp.tool()
def delete_project(project_name: str) -> str:
    """
    Delete a project and all its tasks. This action cannot be undone.

    Args:
        project_name: The project name to delete
    """
    with _get_client() as client:
        proj = client.find_project_by_name(project_name)
        if not proj:
            return f"Project '{project_name}' not found."

        client.delete_project(proj["id"])

    return f"Project '{project_name}' (id: {proj['id']}) has been deleted."


# ── Entry Point ─────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()