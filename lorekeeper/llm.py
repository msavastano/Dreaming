"""One wrapper for every model call, so the rest of the app never touches an SDK.

A provider runs one game-master turn: it sends the prompt, runs any tool calls
the model makes (up to a limit), and returns the final reply text. Every API
request inside that loop is checked against the daily token cap first and
logged to the campaign's usage.jsonl after. Switching providers or models is a
config change, not a code change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol


@dataclass
class Message:
    role: str  # "user" or "assistant"
    text: str


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_tokens += other.cached_tokens


@dataclass
class Reply:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    calls: int = 1
    tool_calls: list[dict] = field(default_factory=list)  # {"name", "args", "result"}


# Runs a tool: (name, args) -> result text.
ToolHandler = Callable[[str, dict], str]


class BudgetExceeded(RuntimeError):
    pass


class Meter(Protocol):
    def before_call(self) -> None: ...
    def after_call(self, model: str, usage: Usage) -> None: ...


class Provider(Protocol):
    name: str

    def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int,
        meter: Meter,
        tools: list[ToolSpec] | None = None,
        tool_handler: ToolHandler | None = None,
        schema: dict | None = None,
        max_tool_rounds: int = 3,
    ) -> Reply: ...


class UsageLog:
    def __init__(self, path: Path):
        self.path = path

    def record(self, provider: str, purpose: str, model: str, usage: Usage) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": provider,
            "model": model,
            "purpose": purpose,
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cached": usage.cached_tokens,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def totals(self, day: str | None = None) -> dict:
        """Token totals, for one UTC day (YYYY-MM-DD) or for all time."""
        totals = {"calls": 0, "input": 0, "output": 0, "cached": 0}
        if not self.path.exists():
            return totals
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if day and not entry["ts"].startswith(day):
                continue
            totals["calls"] += 1
            for key in ("input", "output", "cached"):
                totals[key] += entry.get(key, 0)
        return totals

    def tokens_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        t = self.totals(today)
        return t["input"] + t["output"]


class Budgeted:
    """Wraps a provider: refuses calls over the daily cap and logs every call."""

    def __init__(self, provider: Provider, usage: UsageLog, daily_cap: int):
        self.provider = provider
        self.usage = usage
        self.daily_cap = daily_cap

    def complete(self, system: str, messages: list[Message], max_tokens: int, purpose: str, **kwargs) -> Reply:
        log, cap, name = self.usage, self.daily_cap, self.provider.name

        class _Meter:
            def before_call(self) -> None:
                used = log.tokens_today()
                if used >= cap:
                    raise BudgetExceeded(
                        f"Daily token cap reached ({used:,} of {cap:,}). "
                        "Raise budget.daily_token_cap in config.toml or play again tomorrow."
                    )

            def after_call(self, model: str, usage: Usage) -> None:
                log.record(name, purpose, model, usage)

        return self.provider.complete(system, messages, max_tokens, _Meter(), **kwargs)


def run_tool(handler: ToolHandler | None, name: str, args: dict) -> str:
    if handler is None:
        return "No tools are available."
    try:
        return handler(name, args)
    except Exception as e:  # a broken tool should not end the game
        return f"Tool error: {e}"


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, thinking_level: str = "LOW"):
        from google import genai

        self.client = genai.Client()  # reads GEMINI_API_KEY or GOOGLE_API_KEY
        self.model = model
        self.thinking_level = thinking_level

    def complete(self, system, messages, max_tokens, meter, tools=None, tool_handler=None, schema=None, max_tool_rounds=3) -> Reply:
        from google.genai import types

        contents = [
            types.Content(role="model" if m.role == "assistant" else "user", parts=[types.Part(text=m.text)])
            for m in messages
        ]
        base = dict(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
        )
        if schema:
            base.update(response_mime_type="application/json", response_json_schema=schema)
        if tools:
            base.update(
                tools=[types.Tool(function_declarations=[
                    types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.schema)
                    for t in tools
                ])],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )

        total, calls, tool_log = Usage(), 0, []
        for round_ in range(max_tool_rounds + 1):
            config = dict(base)
            if tools and round_ == max_tool_rounds:  # last round: answer now
                config["tool_config"] = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="NONE")
                )
            meter.before_call()
            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=types.GenerateContentConfig(**config)
            )
            usage = self._usage(response)
            meter.after_call(self.model, usage)
            total.add(usage)
            calls += 1

            function_calls = response.function_calls or []
            if not function_calls:
                break
            # Replay the model's turn as-is so Gemini 3 keeps its thought signatures.
            contents.append(response.candidates[0].content)
            result_parts = []
            for fc in function_calls:
                args = dict(fc.args or {})
                result = run_tool(tool_handler, fc.name, args)
                tool_log.append({"name": fc.name, "args": args, "result": result})
                result_parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
            contents.append(types.Content(role="user", parts=result_parts))

        return Reply(
            text=response.text or "",
            model=self.model,
            input_tokens=total.input_tokens,
            output_tokens=total.output_tokens,
            cached_tokens=total.cached_tokens,
            calls=calls,
            tool_calls=tool_log,
        )

    @staticmethod
    def _usage(response) -> Usage:
        u = response.usage_metadata
        if not u:
            return Usage()
        return Usage(
            input_tokens=u.prompt_token_count or 0,
            # Thinking tokens are billed as output, so count them here.
            output_tokens=(u.candidates_token_count or 0) + (u.thoughts_token_count or 0),
            cached_tokens=u.cached_content_token_count or 0,
        )


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str, effort: str = "low"):
        import anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model
        self.effort = effort

    def complete(self, system, messages, max_tokens, meter, tools=None, tool_handler=None, schema=None, max_tool_rounds=3) -> Reply:
        convo: list[dict] = self._with_history_cache(messages)
        request: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            # The system prompt (rules + canon) is the same every turn, so cache it.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort},
        )
        if schema:
            request["output_config"] = {**request["output_config"], "format": {"type": "json_schema", "schema": schema}}
        if tools:
            request["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.schema, "strict": True}
                for t in tools
            ]

        total, calls, tool_log = Usage(), 0, []
        for round_ in range(max_tool_rounds + 1):
            extra = {}
            if tools and round_ == max_tool_rounds:  # last round: answer now
                extra["tool_choice"] = {"type": "none"}
            meter.before_call()
            response = self.client.messages.create(messages=convo, **request, **extra)
            usage = self._usage(response)
            meter.after_call(self.model, usage)
            total.add(usage)
            calls += 1

            if response.stop_reason != "tool_use":
                break
            convo.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                args = dict(block.input or {})
                result = run_tool(tool_handler, block.name, args)
                tool_log.append({"name": block.name, "args": args, "result": result})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            convo.append({"role": "user", "content": results})

        if response.stop_reason == "refusal":
            text = json.dumps({"narration": "(The game master declined to narrate that. Try a different move.)", "state": None})
        else:
            text = "".join(b.text for b in response.content if b.type == "text")
        return Reply(
            text=text,
            model=self.model,
            input_tokens=total.input_tokens,
            output_tokens=total.output_tokens,
            cached_tokens=total.cached_tokens,
            calls=calls,
            tool_calls=tool_log,
        )

    @staticmethod
    def _usage(response) -> Usage:
        u = response.usage
        cache_read = u.cache_read_input_tokens or 0
        cache_write = u.cache_creation_input_tokens or 0
        return Usage(
            input_tokens=u.input_tokens + cache_read + cache_write,
            output_tokens=u.output_tokens,
            cached_tokens=cache_read,
        )

    @staticmethod
    def _with_history_cache(messages: list[Message]) -> list[dict]:
        """Mark the end of the replayed history as a cache point.

        Everything up to the last narration is the same on the next turn, so
        the next request reads it from cache. Only the final message (notes,
        state and the new move) is new each turn.
        """
        out: list[dict] = [{"role": m.role, "content": m.text} for m in messages]
        if len(out) >= 2:
            last_history = out[-2]
            last_history["content"] = [
                {"type": "text", "text": last_history["content"], "cache_control": {"type": "ephemeral"}}
            ]
        return out


def make_provider(config: dict, override: str | None = None) -> Provider:
    name = override or config["narration"]["provider"]
    if name == "gemini":
        return GeminiProvider(config["gemini"]["model"], config["gemini"]["thinking_level"])
    if name == "claude":
        return ClaudeProvider(config["claude"]["model"], config["claude"]["effort"])
    raise ValueError(f"Unknown provider {name!r}. Use 'gemini' or 'claude'.")
