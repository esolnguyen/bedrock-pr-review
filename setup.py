from setuptools import setup, find_packages

setup(
    name="code-review-agent",
    version="1.0.0",
    description="AWS Bedrock AgentCore-powered Code Review Agent",
    author="AWS Architect & Python Specialist",
    packages=find_packages(),
    install_requires=[
        "boto3>=1.34.0",
        "strands-sdk>=0.1.0",
        "PyGithub>=2.1.1",
        "jira>=3.5.0",
        "requests>=2.31.0",
        "bandit>=1.7.5",
        "python-dotenv>=1.0.0",
        "pydantic>=2.5.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.12.0",
            "moto>=4.2.0",
            "black>=23.12.0",
            "mypy>=1.7.0",
            "flake8>=6.1.0",
        ]
    },
    python_requires=">=3.12",
)
