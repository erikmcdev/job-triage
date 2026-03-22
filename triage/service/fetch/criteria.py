from dataclasses import dataclass, field


@dataclass(frozen=True)
class HardFilters:
    exclude_title_keywords: list[str] = field(default_factory=list)
    blacklist_companies: list[str] = field(default_factory=list)
    min_salary_yearly: int = 0

    def passes(self, title: str, company: str,
               salary_min: int | None, salary_max: int | None) -> bool:
        title_lower = title.lower()
        for kw in self.exclude_title_keywords:
            if kw.lower() in title_lower:
                return False

        company_lower = company.lower()
        for bl in self.blacklist_companies:
            if bl.lower() in company_lower:
                return False

        if self.min_salary_yearly and salary_max is not None:
            if salary_max < self.min_salary_yearly:
                return False

        return True


@dataclass(frozen=True)
class SearchCriteria:
    queries: list[dict] = field(default_factory=list)
    results_per_query: int = 50
    hours_old: int = 72
    hard_filters: HardFilters = field(default_factory=HardFilters)
