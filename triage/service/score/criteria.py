from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoreCriteria:
    core_stack: list[str] = field(default_factory=list)       # +3 per match
    secondary_stack: list[str] = field(default_factory=list)   # +2 per match
    bonus_stack: list[str] = field(default_factory=list)       # +1 per match
    min_keyword_score: int = 4
