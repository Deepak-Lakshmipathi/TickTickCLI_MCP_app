"""
TickTick API Client
Clean wrapper around the TickTick Open API v1.
Designed to be reusable — the MCP server will import this directly.
"""

from datetime import datetime, timezone
from typing import Optional

import httpx

BASE_URL = "https://api.ticktick.com/open/v1"


class TickTickClient:
    """Stateless API client. Takes a token, makes calls."""

    def __init__(self, access_token: str):
        self.token = access_token
        self.http = httpx.Client(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def close(self):
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Projects ────────────────────────────────────────────────

    def list_projects(self) -> list[dict]:
        """Get all projects."""
        r = self.http.get("/project")
        r.raise_for_status()
        return r.json()

    def get_project(self, project_id: str) -> dict:
        """Get a project with all its tasks."""
        r = self.http.get(f"/project/{project_id}/data")
        r.raise_for_status()
        return r.json()

    # ── Tasks ───────────────────────────────────────────────────

    def create_task(
        self,
        title: str,
        project_id: Optional[str] = None,
        content: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: int = 0,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """
        Create a new task.

        Args:
            title:      Task title (required)
            project_id: Project to add to (None = Inbox)
            content:    Task description/notes
            due_date:   ISO date string, e.g. "2026-04-01" or "2026-04-01T10:00:00+0530"
            priority:   0=none, 1=low, 3=medium, 5=high
            tags:       List of tag strings
        """
        body = {"title": title, "priority": priority}

        if project_id:
            body["projectId"] = project_id
        if content:
            body["content"] = content
        if due_date:
            body["dueDate"] = _normalize_date(due_date)
        if tags:
            body["tags"] = tags

        r = self.http.post("/task", json=body)
        r.raise_for_status()
        return r.json()

    def update_task(self, task_id: str, project_id: str, **updates) -> dict:
        """
        Update an existing task.
        Pass any task fields as keyword args (title, content, priority, dueDate, etc.)
        """
        body = {"id": task_id, "projectId": project_id, **updates}

        if "due_date" in updates:
            body["dueDate"] = _normalize_date(updates.pop("due_date"))
            del body["due_date"]  # remove snake_case key

        r = self.http.post(f"/task/{task_id}", json=body)
        r.raise_for_status()
        return r.json()

    def complete_task(self, project_id: str, task_id: str) -> bool:
        """Mark a task as complete."""
        r = self.http.post(f"/project/{project_id}/task/{task_id}/complete")
        r.raise_for_status()
        return True

    def delete_task(self, project_id: str, task_id: str) -> bool:
        """Delete a task."""
        r = self.http.delete(f"/task/{project_id}/{task_id}")
        r.raise_for_status()
        return True

    def get_task(self, project_id: str, task_id: str) -> dict:
        """Get a single task by ID."""
        r = self.http.get(f"/project/{project_id}/task/{task_id}")
        r.raise_for_status()
        return r.json()

    # ── Batch Operations ────────────────────────────────────────

    def batch_tasks(
        self,
        add: Optional[list[dict]] = None,
        update: Optional[list[dict]] = None,
        delete: Optional[list[dict]] = None,
    ) -> dict:
        """
        Batch create/update/delete tasks in a single call.
        delete items should be: [{"taskId": "...", "projectId": "..."}]
        """
        body = {}
        if add:
            body["add"] = add
        if update:
            body["update"] = update
        if delete:
            body["delete"] = delete

        r = self.http.post("/batch/task", json=body)
        r.raise_for_status()
        return r.json()

    # ── Convenience ─────────────────────────────────────────────

    def list_all_tasks(self) -> list[dict]:
        """
        Fetch ALL tasks across all projects.
        (The API doesn't have a single 'all tasks' endpoint,
        so we iterate projects.)
        """
        projects = self.list_projects()
        all_tasks = []
        for proj in projects:
            try:
                data = self.get_project(proj["id"])
                tasks = data.get("tasks", [])
                # Attach project name for convenience
                for t in tasks:
                    t["_projectName"] = proj.get("name", "Unknown")
                all_tasks.extend(tasks)
            except httpx.HTTPStatusError:
                continue
        return all_tasks

    def find_project_by_name(self, name: str) -> Optional[dict]:
        """Find a project by name (case-insensitive)."""
        projects = self.list_projects()
        name_lower = name.lower()
        for p in projects:
            if p.get("name", "").lower() == name_lower:
                return p
        return None


# ── Helpers ─────────────────────────────────────────────────────

def _normalize_date(date_str: str) -> str:
    """
    Accept flexible date formats and normalize to TickTick's expected format.
    Accepts: "2026-04-01", "2026-04-01T10:00:00", "tomorrow", "today"
    """
    date_str = date_str.strip().lower()

    if date_str == "today":
        dt = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")
    elif date_str == "tomorrow":
        from datetime import timedelta
        dt = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")

    # If it's just a date (no time component)
    if len(date_str) == 10:  # "2026-04-01"
        return f"{date_str}T08:00:00+0000"

    # If it already has timezone info, pass through
    if "+" in date_str or date_str.endswith("z"):
        return date_str.upper().replace("Z", "+0000")

    # Otherwise assume UTC
    return f"{date_str}+0000"
