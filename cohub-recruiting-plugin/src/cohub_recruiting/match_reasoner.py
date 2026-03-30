# -*- coding: utf-8 -*-
"""Small-model based match-reason generation for recruiting results."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .config import MatchModelConfig
from .models import CandidateSummary, NormalizedSearchQuery

logger = logging.getLogger(__name__)


class MatchReasonResult(BaseModel):
    """Schema-constrained match reasoning output."""

    reasons: list[str] = Field(default_factory=list)
    note: str = ""


class MatchReasoner:
    """Generate short recruiting match reasons with a separate small model."""

    def __init__(
        self,
        config: MatchModelConfig,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or AsyncOpenAI
        self._client: Any | None = None

    def _get_client(self) -> Any:
        """Return a cached client, creating one on first access."""
        if self._client is None:
            self._client = self._client_factory(**self._client_kwargs())
        return self._client

    async def generate(
        self,
        *,
        query: NormalizedSearchQuery,
        candidate: CandidateSummary,
    ) -> MatchReasonResult:
        """Generate short match reasons or return an empty payload."""
        if not self._config.enabled:
            return MatchReasonResult()

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._config.model,
                messages=self._build_messages(query, candidate),
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = self._extract_content(response)
            return self._parse_result(content)
        except asyncio.TimeoutError:
            logger.warning(
                "Match reason timeout for %s", candidate.display_name
            )
            return MatchReasonResult()
        except Exception:
            logger.error("Match reason failed", exc_info=True)
            return MatchReasonResult()

    def _client_kwargs(self) -> dict[str, Any]:
        """Build client kwargs from config."""
        kwargs: dict[str, Any] = {
            "api_key": self._config.api_key,
            "timeout": self._config.timeout_ms / 1000,
        }
        if self._config.base_url:
            kwargs["base_url"] = self._config.base_url
        return kwargs

    @staticmethod
    def _build_messages(
        query: NormalizedSearchQuery,
        candidate: CandidateSummary,
    ) -> list[dict[str, str]]:
        """Build a schema-constrained prompt for short match reasoning."""
        return [
            {
                "role": "system",
                "content": (
                    "You summarize recruiting list evidence into JSON only. "
                    "Return {\"reasons\": [...], \"note\": \"\"}. "
                    "Use 2 to 4 short reasons. "
                    "Only use evidence present in the input."
                ),
            },
            {
                "role": "user",
                "content": (
                    "normalized_query="
                    + json.dumps(
                        query.model_dump(mode="json"),
                        ensure_ascii=False,
                    )
                    + "\n"
                    + "candidate="
                    + json.dumps(
                        candidate.model_dump(mode="json"),
                        ensure_ascii=False,
                    )
                ),
            },
        ]

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Extract model text content from a chat completion response."""
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            return "\n".join(parts)
        return str(content or "")

    @classmethod
    def _parse_result(cls, raw_content: str) -> MatchReasonResult:
        """Parse JSON content into a normalized match-reason payload."""
        payload = cls._load_json_payload(raw_content)
        if not isinstance(payload, dict):
            return MatchReasonResult()

        reasons = payload.get("reasons") or payload.get("highlights") or []
        if not isinstance(reasons, list):
            reasons = []

        normalized_reasons = [
            str(item).strip() for item in reasons if str(item).strip()
        ][:4]
        note = str(payload.get("note", "") or "").strip()
        return MatchReasonResult(
            reasons=normalized_reasons,
            note=note,
        )

    @staticmethod
    def _load_json_payload(raw_content: str) -> Any:
        """Load a JSON object from plain text or fenced markdown."""
        text = (raw_content or "").strip()
        if not text:
            return None

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
