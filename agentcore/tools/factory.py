from .base import SCMProvider, WorkItemProvider
from ..config import config


def create_scm_provider() -> SCMProvider:
    if config.provider == "azure_devops":
        from .azuredevops import AzureDevOpsSCMProvider
        return AzureDevOpsSCMProvider()
    else:
        from .github import GitHubProvider
        return GitHubProvider()


def create_workitem_provider() -> WorkItemProvider:
    if config.provider == "azure_devops":
        from .azuredevops import AzureDevOpsWorkItemProvider
        return AzureDevOpsWorkItemProvider()
    else:
        from .jira import JiraProvider
        return JiraProvider()
