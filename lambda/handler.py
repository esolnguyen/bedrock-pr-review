import json
import os
import sys
import hmac
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentcore import CodeReviewAgent, config
from agentcore.tools.providers.github import GitHubProvider
from agentcore.tools.providers.jira import JiraProvider
from agentcore.tools.providers.azuredevops import AzureDevOpsSCMProvider, AzureDevOpsWorkItemProvider


def verify_github_signature(payload_body: str, signature_header: str) -> bool:
    if not signature_header:
        return False
    webhook_secret = config.github.webhook_secret
    if not webhook_secret:
        print("WARNING: No webhook secret configured, skipping signature verification")
        return True
    hash_algorithm, github_signature = signature_header.split('=')
    if hash_algorithm != 'sha256':
        return False
    mac = hmac.new(webhook_secret.encode('utf-8'), msg=payload_body.encode('utf-8'), digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), github_signature)


def parse_github_event(headers: dict, payload: dict) -> tuple[bool, str, str, int]:
    """Returns (should_review, reason, repo_name, pr_number)."""
    event_type = headers.get("X-GitHub-Event", headers.get("x-github-event", ""))

    if event_type == "pull_request" and payload.get("action") in ("opened", "reopened", "synchronize"):
        return (True, f"PR {payload['action']}", payload["repository"]["full_name"], payload["pull_request"]["number"])

    if event_type == "issue_comment" and payload.get("action") == "created":
        body = payload.get("comment", {}).get("body", "").lower()
        if ("agent review" in body or "@agent review" in body) and payload.get("issue", {}).get("pull_request"):
            pr_url = payload["issue"]["pull_request"]["url"]
            return True, "Manual trigger", payload["repository"]["full_name"], int(pr_url.split('/')[-1])

    return False, "Event not configured", "", 0


def parse_azuredevops_event(payload: dict) -> tuple[bool, str, str, int]:
    """Returns (should_review, reason, repo_identifier, pr_number)."""
    event_type = payload.get("eventType", "")
    resource = payload.get("resource", {})

    if event_type in ("git.pullrequest.created", "git.pullrequest.updated"):
        repo_id = resource.get("repository", {}).get("id", "")
        pr_id = resource.get("pullRequestId", 0)
        if repo_id and pr_id:
            return True, f"ADO {event_type}", repo_id, pr_id

    if event_type == "ms.vss-code.git-pullrequest-comment-event":
        comment = resource.get("comment", {}).get("content", "").lower()
        if "agent review" in comment:
            pr = resource.get("pullRequest", {})
            repo_id = pr.get("repository", {}).get("id", "")
            pr_id = pr.get("pullRequestId", 0)
            if repo_id and pr_id:
                return True, "Manual trigger via ADO comment", repo_id, pr_id

    return False, "Event not configured", "", 0


def detect_provider(headers: dict, payload: dict) -> str:
    if headers.get("X-GitHub-Event") or headers.get("x-github-event"):
        return "github_jira"
    if payload.get("eventType", "").startswith(("git.", "ms.vss-")):
        return "azure_devops"
    return config.provider


def build_agent(provider: str) -> CodeReviewAgent:
    """Create agent with the right providers — no global state mutation."""
    if provider == "azure_devops":
        return CodeReviewAgent(
            scm_provider=AzureDevOpsSCMProvider(),
            workitem_provider=AzureDevOpsWorkItemProvider(),
        )
    return CodeReviewAgent(
        scm_provider=GitHubProvider(),
        workitem_provider=JiraProvider(),
    )


def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")

    try:
        headers = event.get("headers", {})
        body = event.get("body", "")
        if not body:
            return {"statusCode": 400, "body": json.dumps({"error": "Empty request body"})}

        payload = json.loads(body)
        provider = detect_provider(headers, payload)

        if provider == "github_jira":
            sig = headers.get("X-Hub-Signature-256", headers.get("x-hub-signature-256"))
            if not verify_github_signature(body, sig):
                return {"statusCode": 401, "body": json.dumps({"error": "Invalid signature"})}
            should_review, reason, repo_id, pr_number = parse_github_event(headers, payload)
        else:
            should_review, reason, repo_id, pr_number = parse_azuredevops_event(payload)

        if not should_review:
            return {"statusCode": 200, "body": json.dumps({"message": f"Skipped: {reason}"})}

        print(f"Triggering review ({provider}): {reason} — {repo_id} PR #{pr_number}")

        agent = build_agent(provider)
        result = agent.review_pull_request(repo_id, pr_number)

        if not result.get("success"):
            return {"statusCode": 500, "body": json.dumps({"error": result.get("error")})}

        success = agent.post_review(repo_id, pr_number, result["review_comment"])

        if success:
            return {"statusCode": 200, "body": json.dumps({"message": "Review posted", "pr_number": pr_number})}
        else:
            return {"statusCode": 500, "body": json.dumps({"error": "Review completed but failed to post"})}

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
