from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


RULES_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "rules"


@dataclass(frozen=True)
class RuleDocument:
    """A single local business rule document loaded from Markdown."""

    rule_id: str
    title: str
    decision: str
    priority: int
    tags: list[str]
    segments: list[str]
    scope_types: list[str]
    request_types: list[str]
    pending_order_types: list[str]
    body: str
    source_path: str

    def to_dict(self, score: int | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "title": self.title,
            "decision": self.decision,
            "priority": self.priority,
            "tags": list(self.tags),
            "segments": list(self.segments),
            "scope_types": list(self.scope_types),
            "request_types": list(self.request_types),
            "pending_order_types": list(self.pending_order_types),
            "body": self.body,
            "source_path": self.source_path,
        }
        if score is not None:
            data["score"] = score
        return data


def _parse_list(value: str) -> list[str]:
    cleaned = value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    if not cleaned:
        return []
    return [item.strip().strip("'\"") for item in cleaned.split(",") if item.strip()]


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text.strip()

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()

    raw_meta = parts[1]
    body = parts[2].strip()
    metadata: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, body


def _load_rule_file(path: Path) -> RuleDocument:
    metadata, body = _parse_front_matter(path.read_text(encoding="utf-8"))
    return RuleDocument(
        rule_id=metadata.get("rule_id", path.stem),
        title=metadata.get("title", path.stem.replace("_", " ").title()),
        decision=metadata.get("decision", "REVIEW"),
        priority=int(metadata.get("priority", "0")),
        tags=_parse_list(metadata.get("tags", "")),
        segments=_parse_list(metadata.get("segments", "all")),
        scope_types=_parse_list(metadata.get("scope_types", "all")),
        request_types=_parse_list(metadata.get("request_types", "all")),
        pending_order_types=_parse_list(metadata.get("pending_order_types", "all")),
        body=body,
        source_path=str(path.relative_to(RULES_DIR.parent.parent)),
    )


@lru_cache(maxsize=1)
def load_rule_documents() -> tuple[RuleDocument, ...]:
    """Load local Markdown rules once per process."""
    if not RULES_DIR.exists():
        return ()

    rules = [_load_rule_file(path) for path in sorted(RULES_DIR.glob("*.md"))]
    return tuple(sorted(rules, key=lambda rule: (-rule.priority, rule.rule_id)))
