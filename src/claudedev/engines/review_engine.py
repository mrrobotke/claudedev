"""Multi-reviewer orchestration engine for parallel code review."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from claudedev.config import Settings
    from claudedev.integrations.claude_sdk import ClaudeSDKClient

logger = structlog.get_logger(__name__)


class ReviewDomain(StrEnum):
    QUALITY = "quality"
    SECURITY = "security"
    TESTS = "tests"
    PERFORMANCE = "performance"
    TYPE_DESIGN = "type_design"
    ATOMIC_DESIGN = "atomic_design"
    SILENT_FAILURES = "silent_failures"
    SIMPLICITY = "simplicity"


class FindingSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


@dataclass
class ReviewFinding:
    """A single finding from a reviewer."""

    domain: ReviewDomain
    severity: FindingSeverity
    file_path: str
    line_number: int | None
    description: str
    suggested_fix: str = ""


@dataclass
class ReviewReport:
    """Aggregated review report from all reviewers."""

    findings: list[ReviewFinding] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.MEDIUM)

    @property
    def blocks_completion(self) -> bool:
        return self.critical_count > 0 or self.high_count > 0

    def by_domain(self, domain: ReviewDomain) -> list[ReviewFinding]:
        return [f for f in self.findings if f.domain == domain]

    def by_severity(self, severity: FindingSeverity) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity == severity]

    def to_markdown(self) -> str:
        """Format the review report as a markdown summary."""
        if not self.findings:
            return "No findings."

        sections: list[str] = []
        sections.append(
            f"**Summary**: {self.critical_count} CRITICAL, "
            f"{self.high_count} HIGH, {self.medium_count} MEDIUM\n"
        )

        for severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM):
            items = self.by_severity(severity)
            if not items:
                continue
            sections.append(f"### {severity.value}")
            for finding in items:
                loc = f"`{finding.file_path}"
                if finding.line_number:
                    loc += f":{finding.line_number}"
                loc += "`"
                sections.append(f"- [{finding.domain.value}] {loc}: {finding.description}")
                if finding.suggested_fix:
                    sections.append(f"  - Fix: {finding.suggested_fix}")
            sections.append("")

        return "\n".join(sections)


REVIEWER_PROMPTS: dict[ReviewDomain, str] = {
    ReviewDomain.QUALITY: (
        "Review code for bugs, logic errors, convention violations, DRY, naming, dead code. "
        "Only report findings with >90% confidence."
    ),
    ReviewDomain.SECURITY: (
        "Audit for OWASP Top 10, injection attacks, auth/authz flaws, hardcoded secrets, "
        "CSRF, SSRF, path traversal, rate limiting gaps."
    ),
    ReviewDomain.TESTS: (
        "Analyze test coverage for new/changed code. Identify untested critical paths, "
        "missing edge cases, flaky patterns, missing integration tests."
    ),
    ReviewDomain.PERFORMANCE: (
        "Find N+1 queries, missing indexes, unnecessary re-renders, memory leaks, "
        "O(n^2) algorithms, missing caching opportunities."
    ),
    ReviewDomain.TYPE_DESIGN: (
        "Review type safety: 'any' usage, unsafe casts, missing narrowing, "
        "Pydantic model constraints, generic bounds, exhaustive matching."
    ),
    ReviewDomain.ATOMIC_DESIGN: (
        "Verify atomic design hierarchy: correct level placement, import boundaries, "
        "atoms have no data fetching, molecules compose atoms only."
    ),
    ReviewDomain.SILENT_FAILURES: (
        "Find swallowed exceptions, empty catch blocks, fallback values hiding errors, "
        "missing .catch(), console.log instead of proper error handling."
    ),
    ReviewDomain.SIMPLICITY: (
        "Flag over-engineering: single-use abstractions, unnecessary wrappers, "
        "premature optimization, feature flags for direct code."
    ),
}


class ReviewEngine:
    """Orchestrates parallel code review across multiple specialized reviewers."""

    def __init__(self, settings: Settings, claude_client: ClaudeSDKClient) -> None:
        self.settings = settings
        self.claude_client = claude_client

    async def run_review(
        self,
        changed_files: list[str],
        diff: str,
        domains: list[ReviewDomain] | None = None,
    ) -> ReviewReport:
        """Run reviews across specified domains (or all by default) in parallel.

        Each domain reviewer analyzes the changed files and diff independently.
        Results are aggregated into a single ReviewReport.
        """
        import asyncio

        active_domains = domains or list(ReviewDomain)
        log = logger.bind(domains=[d.value for d in active_domains], file_count=len(changed_files))
        log.info("starting_parallel_review")

        tasks = [self._run_domain_review(domain, changed_files, diff) for domain in active_domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        report = ReviewReport()
        for domain, result in zip(active_domains, results, strict=True):
            if isinstance(result, BaseException):
                log.error("domain_review_failed", domain=domain.value, error=str(result))
                continue
            report.findings.extend(result)

        log.info(
            "review_complete",
            critical=report.critical_count,
            high=report.high_count,
            medium=report.medium_count,
        )
        return report

    async def _run_domain_review(
        self,
        domain: ReviewDomain,
        changed_files: list[str],
        diff: str,
    ) -> list[ReviewFinding]:
        """Run a single domain review and parse the findings."""
        base_prompt = REVIEWER_PROMPTS[domain]
        prompt = (
            f"You are a {domain.value} reviewer.\n\n"
            f"{base_prompt}\n\n"
            f"Changed files:\n{chr(10).join(f'- {f}' for f in changed_files)}\n\n"
            f"Diff:\n```\n{diff[:8000]}\n```\n\n"
            "For each finding, format as:\n"
            "SEVERITY | file:line | description | suggested fix\n"
            "Where SEVERITY is CRITICAL, HIGH, or MEDIUM."
        )

        response = ""
        async for chunk in self.claude_client.run_query(prompt):
            response += chunk

        return self._parse_domain_findings(domain, response)

    def _parse_domain_findings(self, domain: ReviewDomain, response: str) -> list[ReviewFinding]:
        """Parse review response into structured findings."""
        findings: list[ReviewFinding] = []

        for line in response.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            parts = stripped.split("|")
            if len(parts) < 3:
                continue

            severity_str = parts[0].strip().upper()
            if severity_str not in ("CRITICAL", "HIGH", "MEDIUM"):
                continue

            location = parts[1].strip()
            description = parts[2].strip()
            suggested_fix = parts[3].strip() if len(parts) > 3 else ""

            file_path = location
            line_number = None
            if ":" in location:
                file_part, line_part = location.rsplit(":", 1)
                file_path = file_part
                with contextlib.suppress(ValueError):
                    line_number = int(line_part)

            findings.append(
                ReviewFinding(
                    domain=domain,
                    severity=FindingSeverity(severity_str),
                    file_path=file_path,
                    line_number=line_number,
                    description=description,
                    suggested_fix=suggested_fix,
                )
            )

        return findings
