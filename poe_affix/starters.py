"""League-start build recommender (curated catalog + multi-facet filters)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import resolve_named_data

STARTERS_FILE = "league_starters.json"
ALL = "全部"

BUDGET_RANK = {
    "league_start": 0,
    "low": 1,
    "mid": 2,
    "high": 3,
}

DIFFICULTY_LABEL = {
    "easy": "簡單",
    "medium": "中等",
    "hard": "進階",
}

BUDGET_LABEL = {
    "league_start": "開荒零成本",
    "low": "低預算",
    "mid": "中預算",
    "high": "高投資後期",
}

MODE_LABEL = {
    "trade": "交易聯盟",
    "ssf": "SSF",
    "hc": "Hardcore",
}


@dataclass
class StarterBuild:
    id: str
    name: str
    name_zh: str
    ascendancy: str
    ascendancy_zh: str
    skill: str
    skill_zh: str
    styles: list[str]
    damage: list[str]
    playstyles: list[str]
    budget: str
    difficulty: str
    goals: list[str]
    modes: list[str]
    tier: str
    score_bias: int = 0
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    summary: str = ""
    leveling: str = ""
    guide_url: str = ""
    pob_url: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def budget_label(self) -> str:
        return BUDGET_LABEL.get(self.budget, self.budget)

    @property
    def difficulty_label(self) -> str:
        return DIFFICULTY_LABEL.get(self.difficulty, self.difficulty)

    @property
    def budget_rank(self) -> int:
        return BUDGET_RANK.get(self.budget, 99)

    @property
    def search_blob(self) -> str:
        parts = [
            self.id,
            self.name,
            self.name_zh,
            self.ascendancy,
            self.ascendancy_zh,
            self.skill,
            self.skill_zh,
            self.summary,
            self.leveling,
            *self.styles,
            *self.damage,
            *self.playstyles,
            *self.goals,
            *self.pros,
            *self.cons,
            *self.tags,
            self.tier,
            self.budget_label,
            self.difficulty_label,
        ]
        return " ".join(part.lower() for part in parts if part)


@dataclass
class StarterCatalog:
    league: str
    league_zh: str
    updated: str
    notes: str
    styles: list[str]
    damage_types: list[str]
    playstyles: list[str]
    goals: list[str]
    builds: list[StarterBuild]
    budget_options: list[tuple[str, str]] = field(default_factory=list)
    difficulty_options: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class RecommendQuery:
    styles: list[str] = field(default_factory=list)
    damage: list[str] = field(default_factory=list)
    playstyles: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    max_budget: str = ""
    difficulty: str = ""
    mode: str = ""
    search: str = ""
    prefer_league_start: bool = True
    diversify: bool = True
    limit: int = 8


@dataclass
class ScoredBuild:
    build: StarterBuild
    score: float
    reasons: list[str] = field(default_factory=list)


def starters_path() -> Path | None:
    return resolve_named_data(STARTERS_FILE)


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def _parse_build(raw: dict) -> StarterBuild:
    return StarterBuild(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        name_zh=str(raw.get("name_zh") or raw.get("name") or ""),
        ascendancy=str(raw.get("ascendancy") or ""),
        ascendancy_zh=str(raw.get("ascendancy_zh") or raw.get("ascendancy") or ""),
        skill=str(raw.get("skill") or ""),
        skill_zh=str(raw.get("skill_zh") or raw.get("skill") or ""),
        styles=_as_list(raw.get("styles")),
        damage=_as_list(raw.get("damage")),
        playstyles=_as_list(raw.get("playstyles")),
        budget=str(raw.get("budget") or "league_start"),
        difficulty=str(raw.get("difficulty") or "medium"),
        goals=_as_list(raw.get("goals")),
        modes=_as_list(raw.get("modes")) or ["trade"],
        tier=str(raw.get("tier") or "B"),
        score_bias=int(raw.get("score_bias") or 0),
        pros=_as_list(raw.get("pros")),
        cons=_as_list(raw.get("cons")),
        summary=str(raw.get("summary") or ""),
        leveling=str(raw.get("leveling") or ""),
        guide_url=str(raw.get("guide_url") or ""),
        pob_url=str(raw.get("pob_url") or ""),
        tags=_as_list(raw.get("tags")),
    )


def load_catalog(path: Path | None = None) -> StarterCatalog:
    target = path or starters_path()
    if not target or not target.exists():
        raise RuntimeError(f"找不到開荒推薦資料：{STARTERS_FILE}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    builds = [_parse_build(item) for item in payload.get("builds") or [] if isinstance(item, dict)]
    builds = [build for build in builds if build.id and build.name_zh]
    budgets = []
    for item in payload.get("budgets") or []:
        if isinstance(item, dict) and item.get("id"):
            budgets.append((str(item["id"]), str(item.get("label") or item["id"])))
    if not budgets:
        budgets = [(key, label) for key, label in BUDGET_LABEL.items()]
    difficulties = []
    for item in payload.get("difficulties") or []:
        if isinstance(item, dict) and item.get("id"):
            difficulties.append((str(item["id"]), str(item.get("label") or item["id"])))
    if not difficulties:
        difficulties = [(key, label) for key, label in DIFFICULTY_LABEL.items()]
    return StarterCatalog(
        league=str(payload.get("league") or ""),
        league_zh=str(payload.get("league_zh") or payload.get("league") or ""),
        updated=str(payload.get("updated") or ""),
        notes=str(payload.get("notes") or ""),
        styles=_as_list(payload.get("styles")),
        damage_types=_as_list(payload.get("damage_types")),
        playstyles=_as_list(payload.get("playstyles")),
        goals=_as_list(payload.get("goals")),
        builds=builds,
        budget_options=budgets,
        difficulty_options=difficulties,
    )


def matches_search(build: StarterBuild, query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return True
    return all(token in build.search_blob for token in text.split())


def _overlap(selected: list[str], values: list[str]) -> list[str]:
    if not selected:
        return []
    selected_set = set(selected)
    return [item for item in values if item in selected_set]


def _score_build(build: StarterBuild, query: RecommendQuery) -> ScoredBuild | None:
    if query.search and not matches_search(build, query.search):
        return None

    if query.max_budget:
        max_rank = BUDGET_RANK.get(query.max_budget, 99)
        if build.budget_rank > max_rank:
            return None

    if query.difficulty and build.difficulty != query.difficulty:
        return None

    if query.mode and query.mode not in build.modes:
        return None

    style_hits = _overlap(query.styles, build.styles)
    if query.styles and not style_hits:
        return None

    damage_hits = _overlap(query.damage, build.damage)
    if query.damage and not damage_hits:
        return None

    play_hits = _overlap(query.playstyles, build.playstyles)
    goal_hits = _overlap(query.goals, build.goals)

    # Soft preferences: playstyle / goal need not all match, but empty + no hits scores lower.
    if query.playstyles and not play_hits and len(query.playstyles) >= 2:
        # If user picked many playstyles, require at least one.
        return None
    if query.playstyles and not play_hits:
        return None

    score = float(build.score_bias)
    reasons: list[str] = []

    tier_bonus = {"S": 12, "A": 8, "B": 4, "C": 1}.get(build.tier.upper(), 0)
    score += tier_bonus
    if build.tier:
        reasons.append(f"梯隊 {build.tier}")

    if style_hits:
        score += 18 * len(style_hits)
        reasons.append("類型：" + "、".join(style_hits))
    if damage_hits:
        score += 10 * len(damage_hits)
        reasons.append("傷害：" + "、".join(damage_hits))
    if play_hits:
        score += 8 * len(play_hits)
        reasons.append("手感：" + "、".join(play_hits))
    if goal_hits:
        score += 8 * len(goal_hits)
        reasons.append("目標：" + "、".join(goal_hits))

    if query.prefer_league_start and build.budget == "league_start":
        score += 6
        reasons.append("適合開荒")
    elif query.max_budget and build.budget == query.max_budget:
        score += 3
        reasons.append("符合預算")

    if query.difficulty and build.difficulty == query.difficulty:
        score += 4

    if "新手友善" in build.playstyles and (not query.playstyles or "新手友善" in query.playstyles):
        if "新手友善" in play_hits or not query.playstyles:
            score += 1

    return ScoredBuild(build=build, score=score, reasons=reasons)


def recommend(catalog: StarterCatalog, query: RecommendQuery | None = None) -> list[ScoredBuild]:
    query = query or RecommendQuery()
    scored: list[ScoredBuild] = []
    for build in catalog.builds:
        item = _score_build(build, query)
        if item is not None:
            scored.append(item)
    scored.sort(key=lambda item: (-item.score, item.build.name_zh))

    if not query.diversify:
        return scored[: max(query.limit, 1)]

    # Prefer variety by skill within each primary style, then fill by score.
    picked: list[ScoredBuild] = []
    seen_keys: set[str] = set()
    seen_ids: set[str] = set()
    limit = max(query.limit, 1)

    def variety_key(item: ScoredBuild) -> str:
        style = item.build.styles[0] if item.build.styles else "其他"
        skill = item.build.skill or item.build.id
        return f"{style}|{skill}"

    for item in scored:
        key = variety_key(item)
        if key in seen_keys:
            continue
        picked.append(item)
        seen_keys.add(key)
        seen_ids.add(item.build.id)
        if len(picked) >= limit:
            break

    if len(picked) < limit:
        for item in scored:
            if item.build.id in seen_ids:
                continue
            picked.append(item)
            seen_ids.add(item.build.id)
            if len(picked) >= limit:
                break
    return picked


def format_mode_list(modes: list[str]) -> str:
    return "、".join(MODE_LABEL.get(mode, mode) for mode in modes) or "—"


def catalog_summary(catalog: StarterCatalog) -> str:
    return f"{catalog.league_zh or catalog.league} · {len(catalog.builds)} 套 · 更新 {catalog.updated or '—'}"
