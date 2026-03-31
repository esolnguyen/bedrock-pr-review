from __future__ import annotations
import json
import time
import boto3
from datetime import datetime
from typing import Any
from .config import config
from .tools import create_scm_provider, create_workitem_provider
from .tools.base import SCMProvider, WorkItemProvider
from .prompts import SYSTEM_PROMPT


class CodeReviewAgent:
    """AWS Bedrock-powered code review agent with pluggable providers."""

    def __init__(
        self,
        scm_provider: SCMProvider | None = None,
        workitem_provider: WorkItemProvider | None = None,
    ):
        bedrock_kwargs: dict[str, Any] = {"region_name": config.aws.region}
        if config.aws.access_key_id and config.aws.secret_access_key:
            bedrock_kwargs["aws_access_key_id"] = config.aws.access_key_id
            bedrock_kwargs["aws_secret_access_key"] = config.aws.secret_access_key
        self.bedrock = boto3.client('bedrock-runtime', **bedrock_kwargs)
        self.scm = scm_provider or create_scm_provider()
        self.workitem = workitem_provider or create_workitem_provider()
        self.model_id = config.aws.bedrock_model_id

    def review_pull_request(self, repo_identifier: str, pr_number: int) -> dict[str, Any]:
        """Perform comprehensive code review."""
        print(f"Starting review for PR #{pr_number} in {repo_identifier} (provider: {config.provider})")

        try:
            print("Fetching PR details...")
            pr_data = self.scm.fetch_pr_details(repo_identifier, pr_number)
            if "error" in pr_data:
                return {"success": False, "error": pr_data["error"]}

            # Fetch linked work items
            workitem_data = {}
            for wid in pr_data.get("work_item_ids", []):
                print(f"Fetching work item {wid}...")
                ticket = self.workitem.fetch_ticket(wid)
                if "error" not in ticket:
                    workitem_data[wid] = ticket

            # Get the diff
            print("Getting diff...")
            full_diff = self.scm.get_full_diff(repo_identifier, pr_number)

            # Run LLM review
            print("Reviewing with Claude...")
            review = self._llm_review(pr_data, full_diff, workitem_data)

            # Generate inline comments
            print("Generating inline comments...")
            inline_comments = self._generate_inline_comments(full_diff)
            if inline_comments:
                print(f"Generated {len(inline_comments)} inline comments (pending approval)")

            # Format final output
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            review_id = f"CR-{pr_number}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            formatted = (
                f"## 🤖 AI Code Review\n\n{review}\n\n---\n"
                f"*Review ID: {review_id} | Generated: {timestamp}*"
            )

            return {
                "success": True,
                "review_comment": formatted,
                "inline_comments": inline_comments,
                "pr_data": pr_data,
            }
        except Exception as e:
            print(f"Error during review: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def post_review(self, repo_identifier: str, pr_number: int, review_comment: str) -> bool:
        return self.scm.post_comment(repo_identifier, pr_number, review_comment)

    def post_inline_comments(self, repo_identifier: str, pr_number: int,
                             comments: list[dict]) -> int:
        posted = 0
        for c in comments:
            if self.scm.post_inline_comment(
                repo_identifier, pr_number, c["file"], c["line"], c["comment"],
            ):
                posted += 1
        print(f"Posted {posted}/{len(comments)} inline comments")
        return posted

    def _llm_review(self, pr_data: dict, diff: str, workitems: dict) -> str:
        """Single Claude call for the full review."""
        max_diff = 80000
        if len(diff) > max_diff:
            # Truncate at last complete line
            truncated_diff = diff[:max_diff].rsplit("\n", 1)[0]
            truncated_note = f"\n\n(diff truncated — showing {len(truncated_diff)}/{len(diff)} chars)"
        else:
            truncated_diff = diff
            truncated_note = ""

        # Build work items context
        wi_context = ""
        if workitems:
            wi_parts = []
            for wid, wi in workitems.items():
                wi_parts.append(
                    f"- **{wid}** ({wi.get('issue_type', 'Item')}): {wi.get('summary', '')}\n"
                    f"  Description: {wi.get('description', 'N/A')[:500]}\n"
                    f"  Acceptance Criteria: {'; '.join(wi.get('acceptance_criteria', [])) or 'N/A'}"
                )
            wi_context = "\n".join(wi_parts)

        prompt = f"""Review this pull request.

## PR Info
- **Title**: {pr_data.get('title', '')}
- **Author**: {pr_data.get('author', '')}
- **Branch**: {pr_data.get('head_branch', '')} → {pr_data.get('base_branch', '')}
- **Files changed**: {pr_data.get('changed_files', 0)}
- **Lines**: +{pr_data.get('additions', 0)} -{pr_data.get('deletions', 0)}
- **Description**: {(pr_data.get('description', '') or 'None')[:1000]}

## Linked Work Items
{wi_context or 'None'}

## Diff
```
{truncated_diff}{truncated_note}
```

Provide your review in this exact markdown format:

### 📊 Summary
2-3 sentence summary of what the changes do.

### 🔒 Security
List any security concerns, or "✅ No security issues found."

### 📈 Code Quality
Key quality observations — complexity, naming, error handling, duplication. Be specific with file:line.

### ✅ Requirements Coverage
How well the changes match the linked work items. If no work items, say "No work items linked."

### 🎯 Verdict
One of: ✅ APPROVE, 💬 COMMENT, or ❌ REQUEST CHANGES — with a one-line explanation."""

        return self._call_claude(prompt, max_tokens=3000)

    def _generate_inline_comments(self, diff: str) -> list[dict]:
        """Use Claude to identify specific lines worth commenting on."""
        if not diff or diff.startswith("#"):
            return []

        truncated = diff[:30000].rsplit("\n", 1)[0] if len(diff) > 30000 else diff
        prompt = f"""Analyze this git diff and identify specific lines that have issues.
Focus on: typos, bugs, security issues, missing error handling, bad naming.
Do NOT comment on style preferences or minor formatting.
Only flag things that are clearly wrong or risky.

Respond with a JSON array (no markdown fences). Each item:
{{"file": "path/to/file", "line": <line_number_in_new_file>, "comment": "brief explanation"}}

If nothing worth flagging, respond with: []

Diff:
```
{truncated}
```"""

        text = self._call_claude(prompt, max_tokens=2000,
                                 system="You are a code reviewer. Output only valid JSON arrays.")
        try:
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, KeyError, IndexError):
            return []

    def _call_claude(self, prompt: str, max_tokens: int = 2000,
                     system: str | None = None) -> str:
        """Call Bedrock Converse with retry."""
        sys_prompt = system or SYSTEM_PROMPT
        for attempt in range(3):
            try:
                response = self.bedrock.converse(
                    modelId=self.model_id,
                    system=[{"text": sys_prompt}],
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={"temperature": 0, "maxTokens": max_tokens},
                )
                return response["output"]["message"]["content"][0]["text"]
            except Exception as e:
                if "ServiceUnavailable" in type(e).__name__ or "Too many" in str(e):
                    wait = 2 ** (attempt + 1)
                    print(f"Bedrock throttled, retrying in {wait}s... ({attempt + 1}/3)")
                    time.sleep(wait)
                    continue
                print(f"Error calling Claude: {e}")
                return "LLM review unavailable."
        return "LLM review unavailable (service busy)."
