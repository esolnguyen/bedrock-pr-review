"""Azure DevOps SCM + WorkItem provider via MCP proxy."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote
import requests
from .base import SCMProvider, WorkItemProvider
from ..config import config


class AzureDevOpsMCPClient:
    """Client that sends JSON-RPC calls to the Azure DevOps MCP proxy.
    Uses a persistent session for connection reuse."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None):
        self.endpoint = endpoint or config.azure_devops.mcp_endpoint
        self.api_key = api_key or config.azure_devops.mcp_api_key
        self._session = requests.Session()
        self._session.headers.update({
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        })
        self._req_id = 0

    def call_tool(self, tool_name: str, arguments: dict) -> Any:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self._req_id,
        }
        resp = self._session.post(self.endpoint, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")

        # Standard MCP: {"result": {"content": [{"type":"text","text":"..."}]}}
        content = result.get("result", {}).get("content", []) if isinstance(result, dict) else []
        if content and isinstance(content, list) and isinstance(content[0], dict) and content[0].get("type") == "text":
            text = content[0]["text"]
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text

        # Proxy might return result directly
        if isinstance(result, dict) and "result" in result:
            inner = result["result"]
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except (json.JSONDecodeError, TypeError):
                    return inner
            return inner

        return result


class AzureDevOpsSCMProvider(SCMProvider):
    """Azure DevOps SCM provider using MCP proxy."""

    def __init__(self, project: str | None = None,
                 mcp_client: AzureDevOpsMCPClient | None = None):
        self.mcp = mcp_client or AzureDevOpsMCPClient()
        self.project = project or config.azure_devops.project

    def fetch_pr_details(self, repo_identifier: str, pr_number: int) -> dict[str, Any]:
        if not repo_identifier:
            return {"error": "repo_identifier is required"}

        try:
            pr = self.mcp.call_tool("repo_get_pull_request_by_id", {
                "repositoryId": repo_identifier,
                "pullRequestId": pr_number,
                "project": self.project,
                "includeWorkItemRefs": True,
            })

            if not isinstance(pr, dict):
                return {"error": f"Unexpected PR response type: {type(pr).__name__}, value: {str(pr)[:500]}"}

            # Extract work item IDs from the response
            work_item_ids = []
            for ref in pr.get("workItemRefs", []):
                wi_id = ref.get("id") or ref.get("url", "").rstrip("/").split("/")[-1]
                if wi_id:
                    work_item_ids.append(str(wi_id))

            # Fallback: regex on title/description
            if not work_item_ids:
                work_item_ids = self._extract_work_item_ids(
                    pr.get("title", ""), pr.get("description", "")
                )

            # Get changed files via git diff
            head_branch = pr.get("sourceRefName", "").replace("refs/heads/", "")
            base_branch = pr.get("targetRefName", "").replace("refs/heads/", "")
            last_merge = pr.get("lastMergeSourceCommit", {}).get("commitId", "")
            base_commit = pr.get("lastMergeTargetCommit", {}).get("commitId", "")

            files = []
            total_add = total_del = 0
            if last_merge and base_commit:
                files = self._get_changed_files_from_commits(
                    repo_identifier, base_commit, last_merge,
                    base_branch, head_branch,
                )
                total_add = sum(f["additions"] for f in files)
                total_del = sum(f["deletions"] for f in files)

            return {
                "number": pr.get("pullRequestId", pr_number),
                "title": pr.get("title", ""),
                "description": pr.get("description", ""),
                "state": pr.get("status", ""),
                "author": pr.get("createdBy", {}).get("displayName", ""),
                "created_at": pr.get("creationDate", ""),
                "base_branch": base_branch,
                "head_branch": head_branch,
                "additions": total_add,
                "deletions": total_del,
                "changed_files": len(files),
                "files": files,
                "commits": [],
                "work_item_ids": work_item_ids,
                "_head_branch": head_branch,
                "_base_branch": base_branch,
                "_repo_id": repo_identifier,
            }
        except Exception as e:
            return {"error": f"Azure DevOps error: {str(e)}"}

    def get_full_diff(self, repo_identifier: str, pr_number: int) -> str:
        if not repo_identifier:
            return ""

        try:
            pr = self.mcp.call_tool("repo_get_pull_request_by_id", {
                "repositoryId": repo_identifier,
                "pullRequestId": pr_number,
                "project": self.project,
            })
            if not isinstance(pr, dict):
                return ""

            base_commit = pr.get("lastMergeTargetCommit", {}).get("commitId", "")
            head_commit = pr.get("lastMergeSourceCommit", {}).get("commitId", "")
            if not base_commit or not head_commit:
                return ""

            base_branch = pr.get("targetRefName", "").replace("refs/heads/", "")
            head_branch = pr.get("sourceRefName", "").replace("refs/heads/", "")
            return self._git_diff(repo_identifier, base_commit, head_commit,
                                  base_branch, head_branch)
        except Exception as e:
            return f"Error fetching diff: {e}"

    def post_comment(self, repo_identifier: str, pr_number: int, body: str) -> bool:
        try:
            self.mcp.call_tool("repo_create_pull_request_thread", {
                "repositoryId": repo_identifier,
                "pullRequestId": pr_number,
                "content": body,
                "project": self.project,
            })
            return True
        except Exception as e:
            print(f"Error posting comment: {str(e)}")
            return False

    def post_inline_comment(self, repo_identifier: str, pr_number: int,
                            file_path: str, line: int, body: str) -> bool:
        try:
            self.mcp.call_tool("repo_create_pull_request_thread", {
                "repositoryId": repo_identifier,
                "pullRequestId": pr_number,
                "content": body,
                "project": self.project,
                "filePath": file_path,
                "rightFileStartLine": line,
                "rightFileStartOffset": 1,
                "rightFileEndLine": line,
                "rightFileEndOffset": 1,
            })
            return True
        except Exception as e:
            print(f"Error posting inline comment: {e}")
            return False

    def _git_diff(self, repo_name: str, base: str, head: str,
                  base_branch: str = "", head_branch: str = "") -> str:
        """Clone repo, checkout source branch, diff against target branch."""
        org = config.azure_devops.org
        pat = config.azure_devops.pat
        if not org or not pat:
            return "# git diff unavailable: ADO_ORG and ADO_PAT required"

        print(f"Git diff: {base_branch} → {head_branch} in {repo_name}")

        project = quote(self.project, safe="")
        clone_url = f"https://{pat}@dev.azure.com/{org}/{project}/_git/{repo_name}"

        with tempfile.TemporaryDirectory() as tmp:
            run = lambda *args: subprocess.run(
                args, cwd=tmp, capture_output=True, text=True, timeout=180,
            )

            # Clone target branch
            print(f"Cloning {repo_name} (branch: {base_branch or 'default'})...")
            clone_args = ["git", "clone", "--depth=100"]
            if base_branch:
                clone_args += ["-b", base_branch]
            clone_args += [clone_url, tmp]
            r = subprocess.run(clone_args, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                return f"# git clone failed: {r.stderr[:500]}"

            # Fetch source branch with explicit refspec so tracking ref is created
            print(f"Fetching {head_branch}...")
            refspec = f"{head_branch}:refs/remotes/origin/{head_branch}"
            r = run("git", "fetch", "origin", refspec)
            if r.returncode != 0:
                return f"# git fetch failed: {r.stderr[:500]}"

            # Three-dot diff: changes introduced by source branch since divergence
            r = run("git", "diff", f"origin/{base_branch}...origin/{head_branch}")
            if r.returncode == 0:
                print(f"Git diff: {len(r.stdout)} bytes, {r.stdout.count(chr(10))} lines")
                return r.stdout
            return f"# git diff failed: {r.stderr[:500]}"

    def _get_changed_files_from_diff(self, diff_text: str) -> list[dict]:
        """Parse git diff output to extract changed file list with stats."""
        files = []
        current_file = None
        status = "modified"
        additions = deletions = 0

        def _flush():
            if current_file:
                files.append({"filename": current_file, "status": status,
                              "additions": additions, "deletions": deletions,
                              "changes": additions + deletions, "patch": None})

        for line in diff_text.split("\n"):
            if line.startswith("diff --git"):
                _flush()
                parts = line.split(" b/", 1)
                current_file = parts[1] if len(parts) > 1 else None
                status = "modified"
                additions = deletions = 0
            elif line.startswith("new file"):
                status = "added"
            elif line.startswith("deleted file"):
                status = "removed"
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        _flush()
        return files

    def _get_changed_files_from_commits(
        self, repo_id: str, base_commit: str, head_commit: str,
        base_branch: str = "", head_branch: str = "",
    ) -> list[dict]:
        """Get changed files via git diff."""
        diff = self._git_diff(repo_id, base_commit, head_commit, base_branch, head_branch)
        if diff.startswith("#"):
            return []
        return self._get_changed_files_from_diff(diff)

    def _extract_work_item_ids(self, title: str, description: str) -> list[str]:
        pattern = r'(?:AB)?#(\d+)'
        ids = set()
        ids.update(re.findall(pattern, title))
        if description:
            ids.update(re.findall(pattern, description))
        return sorted(list(ids))


class AzureDevOpsWorkItemProvider(WorkItemProvider):
    """Azure Boards work item provider using MCP proxy."""

    def __init__(self, project: str | None = None,
                 mcp_client: AzureDevOpsMCPClient | None = None):
        self.mcp = mcp_client or AzureDevOpsMCPClient()
        self.project = project or config.azure_devops.project

    def fetch_ticket(self, ticket_id: str) -> dict[str, Any]:
        try:
            wi = self.mcp.call_tool("wit_get_work_item", {
                "id": int(ticket_id),
                "project": self.project,
            })

            if not isinstance(wi, dict):
                return {"error": f"Unexpected work item response: {str(wi)[:300]}"}

            fields = wi.get("fields", {})
            description = fields.get("System.Description", "") or ""
            assigned = fields.get("System.AssignedTo")

            return {
                "key": str(wi.get("id", ticket_id)),
                "summary": fields.get("System.Title", ""),
                "description": self._strip_html(description),
                "status": fields.get("System.State", ""),
                "priority": str(fields.get("Microsoft.VSTS.Common.Priority", "")),
                "issue_type": fields.get("System.WorkItemType", ""),
                "assignee": assigned.get("displayName", "Unassigned") if isinstance(assigned, dict) else str(assigned or "Unassigned"),
                "requirements": self._extract_requirements(description),
                "acceptance_criteria": self._extract_acceptance_criteria(fields),
            }
        except Exception as e:
            return {"error": f"Azure DevOps work item error: {str(e)}"}

    def _strip_html(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '\n', text).strip()

    def _extract_acceptance_criteria(self, fields: dict) -> list[str]:
        ac = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "") or ""
        if not ac:
            return []
        clean = self._strip_html(ac)
        return [line.strip() for line in clean.split('\n') if line.strip()]

    def _extract_requirements(self, description: str) -> list[str]:
        if not description:
            return []
        clean = self._strip_html(description)
        for pattern in [r'Requirements?:?\n(.*?)(?:\n\n|\Z)']:
            matches = re.findall(pattern, clean, re.IGNORECASE | re.DOTALL)
            if matches:
                items = re.split(r'\n[\*\-\d]+[\.\)]\s*', matches[0])
                return [item.strip() for item in items if item.strip()]
        return []
