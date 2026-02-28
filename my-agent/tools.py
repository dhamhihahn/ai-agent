from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ALLOWED_COMMAND_PREFIXES = {
    "python",
    "py",
    "git",
    "rg",
    "Get-ChildItem",
    "dir",
    "type",
    "echo",
    "Get-Content",
}


def _resolve_in_workspace(workspace: Path, user_path: str) -> Path:
    candidate = (workspace / user_path).resolve() if not Path(user_path).is_absolute() else Path(user_path).resolve()
    workspace_resolved = workspace.resolve()
    if candidate != workspace_resolved and workspace_resolved not in candidate.parents:
        raise ValueError("Path is outside workspace")
    return candidate


def run_shell(command: str, cwd: str, timeout_seconds: int = 45) -> dict[str, Any]:
    first = command.strip().split(maxsplit=1)[0] if command.strip() else ""
    if first and first not in ALLOWED_COMMAND_PREFIXES:
        return {
            "ok": False,
            "error": f"Command prefix '{first}' is blocked by allowlist.",
            "allowed_prefixes": sorted(ALLOWED_COMMAND_PREFIXES),
        }

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out after {timeout_seconds}s"}


def read_file(workspace: Path, path: str) -> dict[str, Any]:
    try:
        resolved = _resolve_in_workspace(workspace, path)
        if not resolved.exists():
            return {"ok": False, "error": "File does not exist"}
        return {"ok": True, "path": str(resolved), "content": resolved.read_text(encoding="utf-8")[-16000:]}
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def write_file(workspace: Path, path: str, content: str) -> dict[str, Any]:
    try:
        resolved = _resolve_in_workspace(workspace, path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(resolved), "bytes": len(content.encode("utf-8"))}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def list_files(workspace: Path, path: str = ".") -> dict[str, Any]:
    try:
        resolved = _resolve_in_workspace(workspace, path)
        if not resolved.exists():
            return {"ok": False, "error": "Path does not exist"}
        files = []
        for p in resolved.rglob("*"):
            if p.is_file():
                files.append(str(p.relative_to(workspace)))
            if len(files) >= 200:
                break
        return {"ok": True, "files": files}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def web_lookup(query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "Query is empty"}

    encoded = urllib.parse.quote_plus(query)

    def _fetch_json(url: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "my-agent/1.0 (+https://localhost)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # Wikipedia search API -> summary endpoint of best match.
    try:
        search_url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
            f"{encoded}&utf8=&format=json&srlimit=1"
        )
        search_data = _fetch_json(search_url)
        hits = (((search_data.get("query") or {}).get("search")) or [])
        if hits:
            title = (hits[0].get("title") or "").strip()
            if title:
                summary_url = (
                    "https://en.wikipedia.org/api/rest_v1/page/summary/"
                    f"{urllib.parse.quote(title.replace(' ', '_'))}"
                )
                summary_data = _fetch_json(summary_url)
                extract = (summary_data.get("extract") or "").strip()
                if extract:
                    return {
                        "ok": True,
                        "source": "wikipedia",
                        "title": (summary_data.get("title") or title).strip(),
                        "summary": extract[:1200],
                        "url": summary_data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    }
    except Exception:
        pass

    # Fallback: DuckDuckGo instant answer API.
    ddg_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1&no_html=1"
    try:
        data = _fetch_json(ddg_url)
        abstract = (data.get("AbstractText") or "").strip()
        heading = (data.get("Heading") or "").strip()
        if abstract:
            return {
                "ok": True,
                "source": "duckduckgo",
                "title": heading or query,
                "summary": abstract[:1200],
                "url": data.get("AbstractURL", ""),
            }
        related = data.get("RelatedTopics") or []
        snippets: list[str] = []
        for item in related:
            if isinstance(item, dict) and isinstance(item.get("Text"), str):
                snippets.append(item["Text"])
            if len(snippets) >= 3:
                break
        if snippets:
            return {
                "ok": True,
                "source": "duckduckgo",
                "title": heading or query,
                "summary": " | ".join(snippets)[:1200],
                "url": "",
            }
        return {"ok": False, "error": "No web summary found"}
    except Exception as exc:
        return {"ok": False, "error": f"Web lookup failed: {exc}"}


def get_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "run_shell",
            "description": "Run a PowerShell command in the workspace. Limited by a command allowlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "description": "Relative directory in workspace", "default": "."},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a text file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "write_file",
            "description": "Write a text file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "list_files",
            "description": "List up to 200 files inside a workspace path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "web_lookup",
            "description": "Look up a term on the internet and return a short meaning/summary.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    ]


def execute_tool(name: str, arguments: str, workspace: Path) -> str:
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "Invalid JSON args"})

    if name == "run_shell":
        cwd = "."
        if isinstance(args.get("cwd"), str):
            cwd = args["cwd"]
        try:
            resolved_cwd = _resolve_in_workspace(workspace, cwd)
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        result = run_shell(args.get("command", ""), str(resolved_cwd))
    elif name == "read_file":
        result = read_file(workspace, args.get("path", ""))
    elif name == "write_file":
        result = write_file(workspace, args.get("path", ""), args.get("content", ""))
    elif name == "list_files":
        result = list_files(workspace, args.get("path", "."))
    elif name == "web_lookup":
        result = web_lookup(args.get("query", ""))
    else:
        result = {"ok": False, "error": f"Unknown tool: {name}"}

    return json.dumps(result)
