#!/usr/bin/env python3
"""
TickTick CLI — Manage your TickTick tasks from the terminal.

Usage:
    ticktick setup <client_id> <client_secret>     First-time OAuth setup
    ticktick projects                               List all projects
    ticktick tasks [project_name]                   List tasks (all or by project)
    ticktick add "title" [options]                  Create a task
    ticktick complete <project_id> <task_id>        Complete a task
    ticktick delete <project_id> <task_id>          Delete a task
    ticktick update <task_id> --project <pid> [options]  Update a task

Options for add/update:
    --project <name_or_id>    Target project (default: Inbox)
    --due <date>              Due date: "today", "tomorrow", "2026-04-01"
    --priority <level>        none|low|medium|high (or 0/1/3/5)
    --content <text>          Description / notes
    --tags <t1,t2,...>        Comma-separated tags
"""

import sys
import json

from ticktick_auth import setup as auth_setup, get_valid_token
from ticktick_api import TickTickClient


PRIORITY_MAP = {"none": 0, "low": 1, "medium": 3, "high": 5}


def parse_priority(val: str) -> int:
    """Convert priority string to int."""
    if val.isdigit():
        return int(val)
    return PRIORITY_MAP.get(val.lower(), 0)


def format_task(task: dict, show_project: bool = False) -> str:
    """Pretty-print a single task."""
    priority_icons = {0: " ", 1: "🔵", 3: "🟡", 5: "🔴"}
    icon = priority_icons.get(task.get("priority", 0), " ")

    line = f"  {icon} {task.get('title', 'Untitled')}"

    due = task.get("dueDate", "")
    if due:
        line += f"  📅 {due[:10]}"

    tags = task.get("tags", [])
    if tags:
        line += f"  🏷  {', '.join(tags)}"

    if show_project:
        proj = task.get("_projectName", "")
        if proj:
            line += f"  [{proj}]"

    # Show IDs in a dim line below for reference
    pid = task.get("projectId", "?")
    tid = task.get("id", "?")
    id_line = f"    └─ project:{pid}  task:{tid}"

    return f"{line}\n{id_line}"


def cmd_setup(args: list[str]):
    """Handle: ticktick setup <client_id> <client_secret>"""
    if len(args) < 2:
        print("Usage: ticktick setup <client_id> <client_secret>")
        sys.exit(1)
    auth_setup(args[0], args[1])


def cmd_projects():
    """Handle: ticktick projects"""
    token = get_valid_token()
    with TickTickClient(token) as client:
        projects = client.list_projects()

    if not projects:
        print("No projects found.")
        return

    print(f"\n{'Name':<30} {'ID':<30} {'Kind'}")
    print("─" * 80)
    for p in projects:
        kind = p.get("kind", "TASK")
        print(f"  {p.get('name', '?'):<28} {p.get('id', '?'):<28} {kind}")
    print()


def cmd_tasks(args: list[str]):
    """Handle: ticktick tasks [project_name]"""
    token = get_valid_token()
    with TickTickClient(token) as client:
        if args:
            # Find project by name
            project_name = " ".join(args)
            proj = client.find_project_by_name(project_name)
            if not proj:
                print(f"Project '{project_name}' not found.")
                sys.exit(1)

            data = client.get_project(proj["id"])
            tasks = data.get("tasks", [])
            print(f"\n📁 {proj['name']} ({len(tasks)} tasks)\n")
            for t in tasks:
                print(format_task(t))
        else:
            tasks = client.list_all_tasks()
            print(f"\n📋 All tasks ({len(tasks)} total)\n")
            for t in sorted(tasks, key=lambda x: x.get("priority", 0), reverse=True):
                print(format_task(t, show_project=True))
    print()


def cmd_add(args: list[str]):
    """Handle: ticktick add "title" [--project X] [--due Y] [--priority Z] [--content C] [--tags t1,t2]"""
    if not args:
        print('Usage: ticktick add "Task title" [--project name] [--due date] [--priority level]')
        sys.exit(1)

    # Parse positional title and keyword args
    title = args[0]
    opts = _parse_opts(args[1:])

    token = get_valid_token()
    with TickTickClient(token) as client:
        # Resolve project name to ID if given
        project_id = None
        if "project" in opts:
            proj = client.find_project_by_name(opts["project"])
            if proj:
                project_id = proj["id"]
            else:
                # Maybe it's already an ID
                project_id = opts["project"]

        task = client.create_task(
            title=title,
            project_id=project_id,
            content=opts.get("content"),
            due_date=opts.get("due"),
            priority=parse_priority(opts.get("priority", "0")),
            tags=opts.get("tags", "").split(",") if opts.get("tags") else None,
        )

    print(f"\n✅ Created: {task.get('title')}")
    print(f"   ID: {task.get('id')}")
    print(f"   Project: {task.get('projectId')}\n")


def cmd_complete(args: list[str]):
    """Handle: ticktick complete <project_id> <task_id>"""
    if len(args) < 2:
        print("Usage: ticktick complete <project_id> <task_id>")
        sys.exit(1)

    token = get_valid_token()
    with TickTickClient(token) as client:
        client.complete_task(args[0], args[1])
    print(f"\n✅ Task completed!\n")


def cmd_delete(args: list[str]):
    """Handle: ticktick delete <project_id> <task_id>"""
    if len(args) < 2:
        print("Usage: ticktick delete <project_id> <task_id>")
        sys.exit(1)

    token = get_valid_token()
    with TickTickClient(token) as client:
        client.delete_task(args[0], args[1])
    print(f"\n🗑  Task deleted!\n")


def cmd_update(args: list[str]):
    """Handle: ticktick update <task_id> --project <pid> [--title X] [--due Y] ..."""
    if not args:
        print("Usage: ticktick update <task_id> --project <project_id> [--title X] [--due Y]")
        sys.exit(1)

    task_id = args[0]
    opts = _parse_opts(args[1:])

    if "project" not in opts:
        print("Error: --project <project_id> is required for updates.")
        sys.exit(1)

    token = get_valid_token()
    updates = {}
    if "title" in opts:
        updates["title"] = opts["title"]
    if "content" in opts:
        updates["content"] = opts["content"]
    if "due" in opts:
        updates["due_date"] = opts["due"]
    if "priority" in opts:
        updates["priority"] = parse_priority(opts["priority"])
    if "tags" in opts:
        updates["tags"] = opts["tags"].split(",")

    with TickTickClient(token) as client:
        result = client.update_task(task_id, opts["project"], **updates)

    print(f"\n✏️  Updated: {result.get('title')}\n")


def _parse_opts(args: list[str]) -> dict:
    """Parse --key value pairs from args list."""
    opts = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args):
            key = args[i][2:]
            opts[key] = args[i + 1]
            i += 2
        else:
            i += 1
    return opts


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "setup": cmd_setup,
        "projects": lambda: cmd_projects(),
        "tasks": cmd_tasks,
        "add": cmd_add,
        "complete": cmd_complete,
        "delete": cmd_delete,
        "update": cmd_update,
    }

    if command == "help" or command == "--help":
        print(__doc__)
    elif command in commands:
        func = commands[command]
        # Handle commands that don't take args
        if command == "projects":
            func()
        else:
            func(args)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
