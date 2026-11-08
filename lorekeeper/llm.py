"""One wrapper for every model call, so the rest of the app never touches an SDK.

Every call is logged to the campaign's usage.jsonl with its token counts, and
checked against the daily token cap before it is sent. Switching providers or
models is a config change, not a code change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass
class Message:
    role: str  # "user" or "assistant"
    text: str


@dataclass
class Reply:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


class BudgetExceeded(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Reply: ...


class UsageLog:
    def __init__(self, path: Path):
        self.path = path

    def record(self, provider: str, purpose: str, reply: Reply) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": provider,
            "model": reply.model,
            "purpose": purpose,
            "input": reply.input_tokens,
            "output": reply.output_tokens,
            "cached": reply.cached_tokens,
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

    def complete(self, system: str, messages: list[Message], max_tokens: int, purpose: str) -> Reply:
        used = self.usage.tokens_today()
        if used >= self.daily_cap:
            raise BudgetExceeded(
                f"Daily token cap reached ({used:,} of {self.daily_cap:,}). "
                "Raise budget.daily_token_cap in config.toml or play again tomorrow."
            )
        reply = self.provider.complete(system, messages, max_tokens)
        self.usage.record(self.provider.name, purpose, reply)
        return reply


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, thinking_level: str = "LOW"):
        from google import genai

        self.client = genai.Client()  # reads GEMINI_API_KEY or GOOGLE_API_KEY
        self.model = model
        self.thinking_level = thinking_level

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Reply:
        from google.genai import types

        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.text)],
            )
            for m in messages
        ]
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
            ),
        )
        usage = response.usage_metadata
        return Reply(
            text=response.text or "",
            model=self.model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            # Thinking tokens are billed as output, so count them here.
            output_tokens=((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0,
            cached_tokens=(usage.cached_content_token_count or 0) if usage else 0,
        )


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str, effort: str = "low"):
        import anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model
        self.effort = effort

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Reply:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            # The system prompt (rules + canon) is the same every turn, so cache it.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=self._with_history_cache(messages),
            output_config={"effort": self.effort},
        )
        if response.stop_reason == "refusal":
            text = "(The game master declined to narrate that. Try a different move.)"
        else:
            text = "".join(b.text for b in response.content if b.type == "text")
        u = response.usage
        cache_read = u.cache_read_input_tokens or 0
        cache_write = u.cache_creation_input_tokens or 0
        return Reply(
            text=text,
            model=self.model,
            input_tokens=u.input_tokens + cache_read + cache_write,
            output_tokens=u.output_tokens,
            cached_tokens=cache_read,
        )


    @staticmethod
    def _with_history_cache(messages: list[Message]) -> list[dict]:
        """Mark the end of the replayed history as a cache point.

        Everything up to the last narration is the same on the next turn, so
        the next request reads it from cache. Only the final message (state and
        the new move) is new each turn.
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
