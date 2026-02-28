from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from memory import MemoryStore
from tools import execute_tool, get_tool_specs, web_lookup


SYSTEM_PROMPT = """You are a pragmatic coding agent running on Windows.
Use tools when needed. Prefer precise, minimal edits.
Never claim to run commands you did not run.
Understand both Dutch and English user input, including casual greetings/slang.
If a user term is unclear, use web_lookup to infer meaning before answering.
"""

GREETING_WORDS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "hola",
    "hoi",
    "hallo",
    "heyo",
    "goedemorgen",
    "goedemiddag",
    "goedenavond",
}


def maybe_handle_smalltalk(user_input: str) -> str | None:
    cleaned = re.sub(r"[^a-zA-Z0-9\\s]", " ", user_input.lower()).strip()
    if not cleaned:
        return None

    words = [w for w in cleaned.split() if w]
    if not words:
        return None

    # Fast path for short greetings so the assistant feels responsive.
    if len(words) <= 3 and all(w in GREETING_WORDS for w in words):
        if any(w in {"hoi", "hallo", "goedemorgen", "goedemiddag", "goedenavond"} for w in words):
            return "Hoi! Ik ben er. Zeg maar wat je wilt doen, dan help ik je direct."
        return "Hey! I'm here. Tell me what you want to build or fix."

    return None


def _extract_lookup_query(user_input: str) -> str | None:
    text = user_input.strip()
    if not text:
        return None

    lowered = text.lower()
    patterns = [
        r"^wat betekent\s+(.+?)\??$",
        r"^what does\s+(.+?)\s+mean\??$",
        r"^what is\s+(.+?)\??$",
        r"^meaning of\s+(.+?)\??$",
    ]
    for pattern in patterns:
        m = re.match(pattern, lowered)
        if m:
            return m.group(1).strip(" .,!?:;\"'")

    cleaned = re.sub(r"[^a-zA-Z0-9\s\-_/]", " ", text).strip()
    words = [w for w in cleaned.split() if w]
    if not words:
        return None

    # For short/medium messages, prefetch web context immediately.
    if 1 <= len(words) <= 12 and not all(w.lower() in GREETING_WORDS for w in words):
        return " ".join(words)
    return None


def _maybe_prefetch_web_context(user_input: str) -> str | None:
    query = _extract_lookup_query(user_input)
    if not query:
        return None

    result = web_lookup(query)
    if not result.get("ok"):
        error = str(result.get("error") or "unknown error")
        return f"Web lookup attempted for unclear term '{query}', but failed: {error}"

    title = str(result.get("title") or query)
    summary = str(result.get("summary") or "").strip()
    source = str(result.get("source") or "web")
    url = str(result.get("url") or "")
    if not summary:
        return None

    return f"Web context for possibly unclear term:\n- query: {query}\n- title: {title}\n- source: {source}\n- url: {url}\n- summary: {summary}"


def _chat_tools_from_specs() -> list[dict[str, Any]]:
    tools = []
    for spec in get_tool_specs():
        if spec.get("type") != "function":
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec.get("description", ""),
                    "parameters": spec["parameters"],
                },
            }
        )
    return tools


def _choose_api_mode(mode: str, base_url: str | None) -> str:
    if mode in {"responses", "chat"}:
        return mode
    if not base_url:
        return "responses"
    lower = base_url.lower()
    if "localhost" in lower or "127.0.0.1" in lower:
        return "chat"
    return "responses"


def run_turn_responses(client: OpenAI, model: str, user_input: str, workspace: Path, memory: MemoryStore) -> str:
    smalltalk = maybe_handle_smalltalk(user_input)
    if smalltalk is not None:
        return smalltalk

    recent = memory.recent(8)
    history_lines = [f"{item['role']}: {item['content']}" for item in recent]
    history_block = "\n".join(history_lines)
    web_context = _maybe_prefetch_web_context(user_input)
    system_input: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Workspace: {workspace}"},
        {"role": "system", "content": f"Recent memory:\n{history_block}"},
    ]
    if web_context:
        system_input.append({"role": "system", "content": web_context})
    system_input.append({"role": "user", "content": user_input})

    response = client.responses.create(
        model=model,
        input=system_input,
        tools=get_tool_specs(),
    )

    while True:
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            return response.output_text.strip()

        tool_outputs = []
        for call in function_calls:
            output = execute_tool(call.name, call.arguments, workspace)
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": output,
                }
            )

        response = client.responses.create(
            model=model,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=get_tool_specs(),
        )


def run_turn_chat(client: OpenAI, model: str, user_input: str, workspace: Path, memory: MemoryStore) -> str:
    smalltalk = maybe_handle_smalltalk(user_input)
    if smalltalk is not None:
        return smalltalk

    recent = memory.recent(8)
    history_lines = [f"{item['role']}: {item['content']}" for item in recent]
    history_block = "\n".join(history_lines)
    web_context = _maybe_prefetch_web_context(user_input)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Workspace: {workspace}"},
        {"role": "system", "content": f"Recent memory:\n{history_block}"},
    ]
    if web_context:
        messages.append({"role": "system", "content": web_context})
    messages.append({"role": "user", "content": user_input})
    tools = _chat_tools_from_specs()

    for _ in range(12):
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        message = completion.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            return (message.content or "").strip()

        messages.append({"role": "assistant", "content": message.content or "", "tool_calls": tool_calls})

        for call in tool_calls:
            output = execute_tool(call.function.name, call.function.arguments, workspace)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": output,
                }
            )

    return "Stopped after too many tool iterations."


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Codex-like coding agent")
    parser.add_argument("--workspace", default=".", help="Workspace folder for file operations")
    parser.add_argument("--model", default="google/gemma-3-4b", help="Model name")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"), help="OpenAI-compatible base URL")
    parser.add_argument(
        "--api-mode",
        choices=["auto", "responses", "chat"],
        default="auto",
        help="responses=Responses API, chat=chat/completions (LM Studio), auto picks by base-url",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if args.base_url and ("localhost" in args.base_url.lower() or "127.0.0.1" in args.base_url.lower()):
            api_key = "lm-studio"
        else:
            raise SystemExit("OPENAI_API_KEY not set. Set it first and retry.")

    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    memory = MemoryStore(workspace / ".agent" / "memory.json")
    client = OpenAI(api_key=api_key, base_url=args.base_url)
    api_mode = _choose_api_mode(args.api_mode, args.base_url)

    print(f"Agent ready. Workspace: {workspace}")
    print(f"API mode: {api_mode}")
    if args.base_url:
        print(f"Base URL: {args.base_url}")
    print("Type 'exit' to quit.")

    while True:
        try:
            user_input = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopping.")
            return

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Stopping.")
            return

        memory.append("user", user_input)
        if api_mode == "chat":
            answer = run_turn_chat(client, args.model, user_input, workspace, memory)
        else:
            answer = run_turn_responses(client, args.model, user_input, workspace, memory)
        print(f"\nAgent> {answer}")
        memory.append("assistant", answer)


if __name__ == "__main__":
    main()
