from abc import ABC, abstractmethod

from model import Job, TriageResult, Feedback


class JobRepository(ABC):
    """Port defining the contract for job persistence."""

    @abstractmethod
    def save(self, job: Job) -> Job:
        """Insert a new job. Returns the job with its assigned id."""

    @abstractmethod
    def save_batch(self, jobs: list[Job]) -> list[Job]:
        """Insert multiple jobs, skipping duplicates by job_url."""

    @abstractmethod
    def get_by_id(self, job_id: int) -> Job | None: ...

    @abstractmethod
    def get_by_url(self, job_url: str) -> Job | None: ...

    @abstractmethod
    def exists(self, job_url: str) -> bool: ...

    @abstractmethod
    def get_by_status(self, status: str) -> list[Job]: ...

    @abstractmethod
    def update_triage(self, job_id: int, triage: TriageResult) -> None: ...

    @abstractmethod
    def update_feedback(self, job_id: int, feedback: Feedback) -> None: ...

    @abstractmethod
    def update_status(self, job_id: int, status: str) -> None: ...

    @abstractmethod
    def get_seen_urls(self) -> set[str]: ...

    @abstractmethod
    def close(self) -> None: ...
