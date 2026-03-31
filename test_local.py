import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentcore import CodeReviewAgent, config


def test_agent(repo_identifier: str, pr_number: int):
    print(f"🧪 Testing Code Review Agent (provider: {config.provider})")
    print(f"Repository: {repo_identifier}")
    print(f"PR Number: {pr_number}")
    print("=" * 50)

    agent = CodeReviewAgent()
    result = agent.review_pull_request(repo_identifier, pr_number)

    if result.get("success"):
        print("✅ Review completed successfully!\n")
        print("=" * 50)
        print(result["review_comment"])
        print("=" * 50)

        inline = result.get("inline_comments", [])
        if inline:
            print(f"\n📝 Inline comments ({len(inline)}):")
            for c in inline:
                print(f"  {c['file']}:{c['line']} — {c['comment']}")

        post = input("\nPost summary review? (y/n): ").lower()
        if post == 'y':
            success = agent.post_review(repo_identifier, pr_number, result["review_comment"])
            print("✅ Review posted!" if success else "❌ Failed to post review")

        if inline:
            post_inline = input("Post inline comments? (y/n): ").lower()
            if post_inline == 'y':
                agent.post_inline_comments(repo_identifier, pr_number, inline)
    else:
        print(f"❌ Review failed: {result.get('error')}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_local.py <repo_identifier> <pr_number>")
        print()
        print("GitHub:      python test_local.py owner/repo 123")
        print("Azure DevOps: REVIEW_PROVIDER=azure_devops python test_local.py repo-id 456")
        sys.exit(1)

    test_agent(sys.argv[1], int(sys.argv[2]))
