"""도메인 팩 로더 (FR-AG-025, DR-021, NFR-EXT-001·002).

엔진은 산업별 값(아이템 키·동작 ID·제목·명령 문구·티어)을 코드에 갖지 않는다.
전부 packs/<DOMAIN_PACK>/ 의 metrics.yaml·actions.yaml·prompts/ 에서 읽는다.
팩이 없거나 형식이 틀리면 PackError 로 기동을 멈춘다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TIERS = ("A", "B", "C")
TIER_RANK = {"A": 0, "B": 1, "C": 2}


class PackError(RuntimeError):
    """팩을 찾을 수 없거나 형식이 틀렸을 때. 기동 실패 사유로 쓴다."""


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    tier: str
    command_preview: dict[str, str] = field(default_factory=dict)
    precheck: str | None = None
    rollback: str | None = None
    expected_effect: str | None = None
    risk: str | None = None


@dataclass(frozen=True)
class Pack:
    name: str
    path: Path
    metrics: dict[str, list[str]]  # 별칭 → 아이템 키 목록
    actions: dict[str, Action]
    default_tier: str
    fallback_plans: dict[str, list[str]]  # 지표 별칭 → 동작 ID 목록
    prompts: dict[str, str]  # 파일 이름(확장자 제외) → 내용

    def classify_key(self, item_key: str) -> str | None:
        """트리거 아이템 키를 지표 별칭으로 분류한다. 모르면 None."""
        for alias, keys in self.metrics.items():
            for key in keys:
                if item_key == key or item_key.startswith(key.split("[")[0] + "["):
                    return alias
        return None

    def allowed_actions_text(self) -> str:
        """LLM 프롬프트에 넣는 허용 동작 목록 (FR-AG-004)."""
        return "\n".join(
            f"- {a.id} | {a.title} | tier {a.tier}" for a in self.actions.values()
        )


def find_packs_dir(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "packs"
        if candidate.is_dir():
            return candidate
    raise PackError(f"packs/ 폴더를 찾을 수 없음 (시작: {here})")


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise PackError(f"팩 파일 없음: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PackError(f"YAML 파싱 실패: {path}: {exc}") from exc


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def load_pack(name: str, packs_dir: Path | None = None) -> Pack:
    root = (packs_dir or find_packs_dir()) / name
    if not root.is_dir():
        raise PackError(f"도메인 팩 없음: {root}")

    metrics_raw = _read_yaml(root / "metrics.yaml").get("metrics") or {}
    metrics: dict[str, list[str]] = {}
    for alias, spec in metrics_raw.items():
        keys = _as_list(spec.get("keys") if isinstance(spec, dict) else spec)
        if not keys:
            raise PackError(f"metrics.yaml: '{alias}'에 키가 없음")
        metrics[str(alias)] = keys

    actions_raw = _read_yaml(root / "actions.yaml")
    default_tier = str(actions_raw.get("default_tier", "C"))
    if default_tier not in TIERS:
        raise PackError(f"actions.yaml: default_tier 는 A/B/C 중 하나 ({default_tier})")
    actions: dict[str, Action] = {}
    for item in actions_raw.get("actions") or []:
        aid = str(item.get("id", "")).strip()
        tier = str(item.get("tier", "")).strip()
        if not aid or aid in actions:
            raise PackError(f"actions.yaml: 비었거나 중복된 동작 ID ({aid!r})")
        if tier not in TIERS:
            raise PackError(f"actions.yaml: {aid} 의 tier 가 A/B/C 가 아님 ({tier!r})")
        preview = item.get("command_preview") or {}
        if isinstance(preview, str):
            preview = {"default": preview}
        actions[aid] = Action(
            id=aid,
            title=str(item.get("title") or aid),
            tier=tier,
            command_preview={str(k): str(v) for k, v in preview.items()},
            precheck=item.get("precheck"),
            rollback=item.get("rollback"),
            expected_effect=item.get("expected_effect"),
            risk=item.get("risk"),
        )
    if not actions:
        raise PackError("actions.yaml: actions 가 비어 있음")

    fallback_plans: dict[str, list[str]] = {}
    for alias, ids in (actions_raw.get("fallback_plans") or {}).items():
        ids = _as_list(ids)
        unknown = [i for i in ids if i not in actions]
        if unknown:
            raise PackError(f"fallback_plans.{alias}: actions 에 없는 ID {unknown}")
        fallback_plans[str(alias)] = ids

    prompts_dir = root / "prompts"
    if not prompts_dir.is_dir():
        raise PackError(f"prompts/ 폴더 없음: {prompts_dir}")
    prompts = {p.stem: p.read_text(encoding="utf-8") for p in prompts_dir.glob("*.md")}

    return Pack(
        name=name,
        path=root,
        metrics=metrics,
        actions=actions,
        default_tier=default_tier,
        fallback_plans=fallback_plans,
        prompts=prompts,
    )
