from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class SCMProvider(ABC):
    """Abstract source control provider (GitHub, Azure DevOps, etc.)."""

    @abstractmethod
    def fetch_pr_details(self, repo_identifier: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR details. Returns dict with keys: number, title, description, author,
        files (list of {filename, status, additions, deletions, patch}),
        commits, additions, deletions, work_item_ids (list of str)."""
        ...

    @abstractmethod
    def get_full_diff(self, repo_identifier: str, pr_number: int) -> str:
        """Get the complete unified diff for a PR."""
        ...

    @abstractmethod
    def post_comment(self, repo_identifier: str, pr_number: int, body: str) -> bool:
        """Post a comment on the PR. Returns True if successful."""
        ...

    def post_inline_comment(self, repo_identifier: str, pr_number: int,
                            file_path: str, line: int, body: str) -> bool:
        """Post an inline comment on a specific line. Default: not supported."""
        return False


class WorkItemProvider(ABC):
    """Abstract work item provider (Jira, Azure Boards, etc.)."""

    @abstractmethod
    def fetch_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Fetch work item/ticket. Returns dict with keys: key, summary, description,
        status, requirements (list of str), acceptance_criteria (list of str).
        Returns {'error': ...} on failure."""
        ...
