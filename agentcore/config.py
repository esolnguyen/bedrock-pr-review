from __future__ import annotations
import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class AWSConfig(BaseModel):
    access_key_id: str = Field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", ""))
    secret_access_key: str = Field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", ""))
    region: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    bedrock_model_id: str = Field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"))


class GitHubConfig(BaseModel):
    token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    repo: str = Field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))
    webhook_secret: str | None = Field(default_factory=lambda: os.getenv("GITHUB_WEBHOOK_SECRET"))


class JiraConfig(BaseModel):
    url: str = Field(default_factory=lambda: os.getenv("JIRA_URL", ""))
    email: str = Field(default_factory=lambda: os.getenv("JIRA_EMAIL", ""))
    api_token: str = Field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", ""))


class AzureDevOpsConfig(BaseModel):
    mcp_endpoint: str = Field(default_factory=lambda: os.getenv("ADO_MCP_ENDPOINT", ""))
    mcp_api_key: str = Field(default_factory=lambda: os.getenv("ADO_MCP_API_KEY", ""))
    project: str = Field(default_factory=lambda: os.getenv("ADO_PROJECT", ""))
    org: str = Field(default_factory=lambda: os.getenv("ADO_ORG", ""))
    pat: str = Field(default_factory=lambda: os.getenv("ADO_PAT", ""))


class AgentConfig(BaseModel):
    temperature: float = 0.1
    max_tokens: int = 4096
    max_tool_iterations: int = 10


class Config(BaseModel):
    # "github_jira" or "azure_devops"
    provider: str = Field(default_factory=lambda: os.getenv("REVIEW_PROVIDER", "github_jira"))
    aws: AWSConfig = Field(default_factory=AWSConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    jira: JiraConfig = Field(default_factory=JiraConfig)
    azure_devops: AzureDevOpsConfig = Field(default_factory=AzureDevOpsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


config = Config()
