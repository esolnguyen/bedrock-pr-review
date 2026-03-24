# Bedrock AgentCore PR Review Agent

AI-powered code review agent built on AWS Bedrock (Claude). Automatically reviews pull requests for security vulnerabilities, code quality, and requirements coverage, then posts structured feedback as PR comments.

Supports two provider modes:
- **GitHub + Jira** — GitHub PRs with Jira ticket linking
- **Azure DevOps** — Azure Repos PRs with Azure Boards work items (via MCP proxy)

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Webhook Event  │────▶│  Lambda Handler  │────▶│ CodeReviewAgent │
│ (GitHub / ADO)  │     │  (auto-detect)   │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                   ┌────────────┐ ┌─────────────┐ ┌────────────┐
                                   │ SCMProvider │ │  WorkItem   │ │  Bedrock   │
                                   │ (GitHub or  │ │  Provider   │ │  (Claude)  │
                                   │  ADO)       │ │ (Jira/ADO)  │ │            │
                                   └────────────┘ └─────────────┘ └────────────┘
```

```
agentcore/
├── agent.py              # Core review orchestration
├── config.py             # Pydantic config from env vars
├── prompts/
│   ├── system_prompt.py  # LLM system prompt (security, quality, requirements)
│   └── review_template.py
└── tools/
    ├── base.py           # Abstract SCMProvider / WorkItemProvider
    ├── factory.py        # Provider factory based on REVIEW_PROVIDER
    ├── github.py         # GitHub SCM provider (PyGithub)
    ├── jira.py           # Jira work item provider
    └── azuredevops.py    # Azure DevOps SCM + WorkItem via MCP proxy
lambda/
    └── handler.py        # Lambda entry point (webhook handler)
```

## What It Reviews

- **Security** — OWASP Top 10: SQL injection, hardcoded secrets, command injection, XSS, path traversal, weak crypto, SSRF, etc.
- **Code Quality** — complexity, error handling, naming, unused imports, duplication, performance (N+1 queries)
- **Requirements Coverage** — maps PR changes to linked work items/tickets, reports coverage percentage
- **Inline Comments** — generates file-specific comments on lines with bugs, security issues, or missing error handling

## Setup

### Prerequisites

- Python 3.12+
- AWS account with Bedrock access (Claude model enabled)

### Install

```bash
pip install -e .

# or with dev dependencies
pip install -e ".[dev]"
```

### Configure

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description |
|---|---|
| `REVIEW_PROVIDER` | `github_jira` or `azure_devops` |
| `AWS_REGION` | AWS region for Bedrock |
| `BEDROCK_MODEL_ID` | Bedrock model ID (defaults to Claude Sonnet) |
| `GITHUB_TOKEN` | GitHub PAT (for GitHub provider) |
| `JIRA_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` | Jira credentials (for Jira provider) |
| `ADO_MCP_ENDPOINT` / `ADO_MCP_API_KEY` | MCP proxy endpoint (for ADO provider) |
| `ADO_ORG` / `ADO_PROJECT` / `ADO_PAT` | Azure DevOps org details (for ADO provider) |

## Usage

### Local Testing

```bash
# GitHub + Jira
python test_local.py owner/repo 123

# Azure DevOps
REVIEW_PROVIDER=azure_devops python test_local.py <repo-id> 456
```

The test script fetches the PR, runs the review, and prompts before posting comments.

### Lambda Deployment

The `lambda/handler.py` auto-detects the provider from the incoming webhook payload:
- GitHub webhooks (via `X-GitHub-Event` header) → GitHub + Jira provider
- Azure DevOps service hooks (via `eventType` field) → Azure DevOps provider

Supported triggers:
- PR opened / reopened / synchronized (auto-review)
- Comment containing `agent review` or `@agent review` (manual trigger)

### Review Output

The agent posts a structured markdown comment on the PR:

```
## 🤖 AI Code Review

### 📊 Summary
### 🔒 Security
### 📈 Code Quality
### ✅ Requirements Coverage
### 🎯 Verdict (APPROVE / COMMENT / REQUEST CHANGES)
```

Plus optional inline comments on specific files/lines.

## Development

```bash
# Run tests
pytest

# Lint
flake8 agentcore/
mypy agentcore/

# Format
black agentcore/
```
# bedrock_pr_review_agent
