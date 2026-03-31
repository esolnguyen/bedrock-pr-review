from __future__ import annotations
import re
from typing import Any
from jira import JIRA, JIRAError
from .base import WorkItemProvider
from ..config import config


class JiraProvider(WorkItemProvider):
    """Jira implementation of WorkItem provider."""

    def __init__(
        self,
        url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        self.url = url or config.jira.url
        self.email = email or config.jira.email
        self.api_token = api_token or config.jira.api_token

        if self.url and self.email and self.api_token:
            self.client = JIRA(server=self.url, basic_auth=(self.email, self.api_token))
        else:
            self.client = None

    def fetch_ticket(self, ticket_id: str) -> dict[str, Any]:
        if not self.client:
            return {
                "error": "Jira client not configured. Check JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
            }

        try:
            issue = self.client.issue(ticket_id)
            description = issue.fields.description or ""

            return {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": description,
                "status": issue.fields.status.name,
                "priority": (
                    issue.fields.priority.name if issue.fields.priority else "None"
                ),
                "issue_type": issue.fields.issuetype.name,
                "reporter": (
                    issue.fields.reporter.displayName
                    if issue.fields.reporter
                    else "Unknown"
                ),
                "assignee": (
                    issue.fields.assignee.displayName
                    if issue.fields.assignee
                    else "Unassigned"
                ),
                "requirements": self._extract_requirements(description),
                "acceptance_criteria": self._extract_acceptance_criteria(description),
                "labels": (
                    issue.fields.labels if hasattr(issue.fields, "labels") else []
                ),
            }
        except JIRAError as e:
            return {"error": f"Jira API error: {e.text}", "status_code": e.status_code}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    def _extract_acceptance_criteria(self, description: str) -> list[str]:
        for pattern in [
            r"Acceptance Criteria:?\n(.*?)(?:\n\n|\Z)",
            r"AC:?\n(.*?)(?:\n\n|\Z)",
        ]:
            matches = re.findall(pattern, description, re.IGNORECASE | re.DOTALL)
            if matches:
                items = re.split(r"\n[\*\-\d]+[\.\)]\s*", matches[0])
                return [item.strip() for item in items if item.strip()]
        return []

    def _extract_requirements(self, description: str) -> list[str]:
        for pattern in [
            r"Requirements?:?\n(.*?)(?:\n\n|\Z)",
            r"Technical Requirements?:?\n(.*?)(?:\n\n|\Z)",
        ]:
            matches = re.findall(pattern, description, re.IGNORECASE | re.DOTALL)
            if matches:
                items = re.split(r"\n[\*\-\d]+[\.\)]\s*", matches[0])
                return [item.strip() for item in items if item.strip()]
        return []
