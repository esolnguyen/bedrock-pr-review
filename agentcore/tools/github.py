from __future__ import annotations
import re
from typing import Any
from github import Github, GithubException
from .base import SCMProvider
from ..config import config


class GitHubProvider(SCMProvider):
    """GitHub implementation of SCM provider."""

    def __init__(self, token: str | None = None):
        self.token = token or config.github.token
        self.client = Github(self.token)

    def fetch_pr_details(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        try:
            repo = self.client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            pr_data = {
                "number": pr.number,
                "title": pr.title,
                "description": pr.body or "",
                "state": pr.state,
                "author": pr.user.login,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "base_branch": pr.base.ref,
                "head_branch": pr.head.ref,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
            }

            pr_data["work_item_ids"] = self._extract_jira_tickets(pr.title, pr.body)

            files = []
            for f in pr.get_files():
                files.append({
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "patch": f.patch if hasattr(f, 'patch') else None,
                })
            pr_data["files"] = files

            commits = []
            for c in pr.get_commits():
                commits.append({
                    "sha": c.sha,
                    "message": c.commit.message,
                    "author": c.commit.author.name,
                    "date": c.commit.author.date.isoformat(),
                })
            pr_data["commits"] = commits

            return pr_data

        except GithubException as e:
            return {"error": f"GitHub API error: {str(e)}", "status_code": e.status}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    def get_full_diff(self, repo_name: str, pr_number: int) -> str:
        try:
            repo = self.client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            parts = []
            for f in pr.get_files():
                if hasattr(f, 'patch') and f.patch:
                    parts.append(f"--- a/{f.filename}")
                    parts.append(f"+++ b/{f.filename}")
                    parts.append(f.patch)
                    parts.append("")
            return "\n".join(parts)
        except Exception as e:
            return f"Error fetching diff: {str(e)}"

    def post_comment(self, repo_name: str, pr_number: int, body: str) -> bool:
        try:
            repo = self.client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(body)
            return True
        except Exception as e:
            print(f"Error posting comment: {str(e)}")
            return False

    def _extract_jira_tickets(self, title: str, body: str | None) -> list[str]:
        jira_pattern = r'\b([A-Z]{2,10}-\d+)\b'
        tickets = set()
        tickets.update(re.findall(jira_pattern, title))
        if body:
            tickets.update(re.findall(jira_pattern, body))
        return sorted(list(tickets))
