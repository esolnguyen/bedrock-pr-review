"""Review output template."""

REVIEW_TEMPLATE = """## 🤖 AI Code Review

### 📊 Summary
{summary}

### 🔒 Security Analysis
{security_analysis}

### 📈 Code Quality
{code_quality}

### ✅ Requirements Coverage
{requirements_coverage}

### 🔍 Detailed Findings
{detailed_findings}

### 💡 Recommendations
{recommendations}

### 🎯 Verdict
**{verdict}**

{verdict_explanation}

---
*Automated review by AWS Bedrock AgentCore powered by Claude Sonnet 4.5*
*Review ID: {review_id} | Generated: {timestamp}*
"""


def format_security_section(security_results: dict) -> str:
    """Format security analysis section."""
    if not security_results or "error" in security_results:
        return "⚠️ Security analysis could not be completed.\n"

    score = security_results.get("security_score", 0)
    total_issues = security_results.get("total_issues", 0)
    severity_counts = security_results.get("severity_counts", {})
    findings = security_results.get("findings", [])

    lines = [
        f"**Security Score**: {score}/100",
        f"**Issues Found**: {total_issues}",
        "",
    ]

    # Severity breakdown
    if severity_counts:
        lines.append("**By Severity**:")
        if severity_counts.get("CRITICAL", 0) > 0:
            lines.append(f"- 🔴 **CRITICAL**: {severity_counts['CRITICAL']}")
        if severity_counts.get("HIGH", 0) > 0:
            lines.append(f"- 🟠 **HIGH**: {severity_counts['HIGH']}")
        if severity_counts.get("MEDIUM", 0) > 0:
            lines.append(f"- 🟡 **MEDIUM**: {severity_counts['MEDIUM']}")
        if severity_counts.get("LOW", 0) > 0:
            lines.append(f"- 🟢 **LOW**: {severity_counts['LOW']}")
        lines.append("")

    # Top findings
    if findings:
        critical_and_high = [f for f in findings if f["severity"] in ["CRITICAL", "HIGH"]]
        if critical_and_high:
            lines.append("**Critical/High Severity Issues**:")
            for finding in critical_and_high[:5]:  # Top 5
                severity_emoji = "🔴" if finding["severity"] == "CRITICAL" else "🟠"
                lines.append(
                    f"{severity_emoji} **{finding['type']}** in `{finding['file']}:{finding['line']}`"
                )
                lines.append(f"   - {finding['description']}")
                lines.append(f"   - _{finding['recommendation']}_")
                lines.append("")
        elif total_issues == 0:
            lines.append("✅ No security vulnerabilities detected!")
    else:
        lines.append("✅ No security vulnerabilities detected!")

    return "\n".join(lines)


def format_quality_section(quality_results: dict) -> str:
    """Format code quality section."""
    if not quality_results or "error" in quality_results:
        return "⚠️ Quality analysis could not be completed.\n"

    metrics = quality_results.get("metrics", {})
    findings = quality_results.get("findings", [])
    recommendations = quality_results.get("recommendations", [])
    overall_quality = quality_results.get("overall_quality", "Unknown")

    lines = [
        f"**Overall Quality**: {overall_quality}",
        f"**Maintainability Score**: {metrics.get('maintainability_score', 0)}/100",
        f"**Complexity Score**: {metrics.get('complexity_score', 0)}/100",
        "",
        "**Change Statistics**:",
        f"- Files Changed: {metrics.get('files_changed', 0)}",
        f"- Lines Added: {metrics.get('total_lines_added', 0)}",
        f"- Lines Removed: {metrics.get('total_lines_removed', 0)}",
        "",
    ]

    if findings:
        # Group by severity
        high_issues = [f for f in findings if f.get("severity") == "HIGH"]
        medium_issues = [f for f in findings if f.get("severity") == "MEDIUM"]

        if high_issues:
            lines.append("**High Priority Issues**:")
            for finding in high_issues[:3]:
                lines.append(f"- ⚠️ {finding['description']} in `{finding['file']}:{finding['line']}`")
            lines.append("")

        if medium_issues:
            lines.append(f"**Medium Priority Issues**: {len(medium_issues)} found")
            lines.append("")

    if recommendations:
        lines.append("**Recommendations**:")
        for rec in recommendations[:5]:
            lines.append(f"- {rec}")

    return "\n".join(lines)


def format_requirements_section(requirements_results: dict) -> str:
    """Format requirements validation section."""
    if not requirements_results or not requirements_results.get("validation_performed"):
        return "ℹ️ No Jira requirements found for validation.\n"

    coverage = requirements_results.get("coverage_percentage", 0)
    covered = requirements_results.get("requirements_covered", 0)
    partial = requirements_results.get("requirements_partial", 0)
    missing = requirements_results.get("requirements_missing", 0)
    total = requirements_results.get("requirements_checked", 0)

    lines = [
        f"**Coverage**: {coverage}%",
        "",
        f"- ✅ Fully Covered: {covered}/{total}",
        f"- ⚠️ Partially Covered: {partial}/{total}",
        f"- ❌ Not Covered: {missing}/{total}",
        "",
    ]

    # Show details
    validation_results = requirements_results.get("validation_results", [])
    if validation_results:
        lines.append("**Details**:")
        for result in validation_results:
            status = result.get("status", "unknown")
            req_id = result.get("requirement_id", "REQ-???")
            req_text = result.get("requirement_text", "")[:60]

            if status == "covered":
                lines.append(f"✅ {req_id}: {req_text}...")
            elif status == "partial":
                lines.append(f"⚠️ {req_id}: {req_text}... (partial)")
            else:
                lines.append(f"❌ {req_id}: {req_text}... (missing)")

    return "\n".join(lines)


def format_detailed_findings(all_findings: list) -> str:
    """Format detailed findings section."""
    if not all_findings:
        return "No significant issues found.\n"

    lines = []

    # Group by file
    by_file = {}
    for finding in all_findings:
        file_path = finding.get("file", "unknown")
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(finding)

    for file_path, findings in sorted(by_file.items())[:10]:  # Top 10 files
        lines.append(f"#### `{file_path}`")
        lines.append("")

        for finding in findings[:5]:  # Top 5 per file
            severity = finding.get("severity", "INFO")
            line_num = finding.get("line", "?")
            description = finding.get("description", "Issue found")

            emoji = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🟢",
            }.get(severity, "ℹ️")

            lines.append(f"{emoji} **Line {line_num}**: {description}")

            if "recommendation" in finding:
                lines.append(f"   _Recommendation: {finding['recommendation']}_")

            lines.append("")

    return "\n".join(lines)


def format_recommendations(
    security_results: dict,
    quality_results: dict,
    requirements_results: dict
) -> str:
    """Format recommendations section."""
    recommendations = []

    # Security recommendations
    if security_results and security_results.get("has_critical"):
        recommendations.append("🔴 **URGENT**: Fix critical security vulnerabilities before merging")

    sec_recommendation = security_results.get("recommendation", "") if security_results else ""
    if sec_recommendation and "BLOCK" in sec_recommendation:
        recommendations.append(f"🔒 Security: {sec_recommendation}")

    # Quality recommendations
    quality_recs = quality_results.get("recommendations", []) if quality_results else []
    for rec in quality_recs[:3]:
        recommendations.append(f"📈 Quality: {rec}")

    # Requirements recommendations
    req_recommendation = requirements_results.get("recommendation", "") if requirements_results else ""
    if req_recommendation:
        recommendations.append(f"✅ Requirements: {req_recommendation}")

    # Test coverage
    if quality_results and quality_results.get("metrics", {}).get("files_changed", 0) > 0:
        # This would need test coverage data from a test tool
        recommendations.append("🧪 Testing: Ensure adequate test coverage for new code")

    if not recommendations:
        recommendations.append("✅ No major issues found. Good work!")

    return "\n".join(f"{i+1}. {rec}" for i, rec in enumerate(recommendations))


def determine_verdict(
    security_results: dict,
    quality_results: dict,
    requirements_results: dict
) -> tuple[str, str]:
    """
    Determine final verdict and explanation.

    Returns:
        Tuple of (verdict, explanation)
    """
    # Check security
    has_critical_security = security_results and security_results.get("has_critical", False)
    security_score = security_results.get("security_score", 100) if security_results else 100

    # Check quality
    maintainability = quality_results.get("metrics", {}).get("maintainability_score", 100) if quality_results else 100

    # Check requirements
    coverage = requirements_results.get("coverage_percentage", 100) if requirements_results else 100

    # Decision logic
    if has_critical_security:
        verdict = "❌ REQUEST CHANGES"
        explanation = "Critical security vulnerabilities must be addressed before this PR can be merged."

    elif security_score < 60 or maintainability < 50:
        verdict = "❌ REQUEST CHANGES"
        explanation = "Significant security or quality issues need to be resolved."

    elif coverage < 70 and requirements_results and requirements_results.get("validation_performed"):
        verdict = "❌ REQUEST CHANGES"
        explanation = "Important requirements are not fully implemented."

    elif security_score < 80 or maintainability < 70 or coverage < 85:
        verdict = "💬 COMMENT"
        explanation = "Some improvements recommended, but not blocking. Please review the suggestions."

    else:
        verdict = "✅ APPROVE"
        explanation = "Code looks good! Minor suggestions provided for further improvement."

    return verdict, explanation
