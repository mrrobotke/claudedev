"""CWD-aware repository auto-discovery for project onboarding.

Scans the current working directory to detect git repositories,
resolve GitHub remotes, detect tech stacks, classify domains,
and determine monorepo vs polyrepo project structure.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import structlog

from claudedev.core.state import ProjectType

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GitHubRemote:
    """Parsed GitHub remote URL."""

    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass
class DiscoveredRepo:
    """A git repository discovered during CWD scanning."""

    path: Path
    remote: GitHubRemote | None
    default_branch: str
    tech_stack: list[str]
    domain: str  # RepoDomain value
    name: str  # short display name (directory name)


@dataclass
class DiscoveryResult:
    """Complete result of CWD auto-discovery."""

    project_type: str  # ProjectType value
    repos: list[DiscoveredRepo]
    cwd: Path
    is_inside_repo: bool  # True if CWD is inside a git repo


class RepoDiscovery:
    """Discovers and classifies git repositories from CWD."""

    # Tech stack marker files -> tech stack names
    TECH_MARKERS: ClassVar[dict[str, list[str]]] = {
        "pyproject.toml": ["python"],
        "setup.py": ["python"],
        "requirements.txt": ["python"],
        "Pipfile": ["python"],
        "package.json": [],  # special handling - inspect content
        "Cargo.toml": ["rust"],
        "go.mod": ["go"],
        "Gemfile": ["ruby"],
        "pom.xml": ["java"],
        "build.gradle": ["java"],
        "build.gradle.kts": ["kotlin"],
        "Podfile": ["ios", "swift"],
        "pubspec.yaml": ["dart", "flutter"],
        "composer.json": ["php"],
        "mix.exs": ["elixir"],
    }

    # package.json dependency -> tech stack
    PACKAGE_JSON_MARKERS: ClassVar[dict[str, str]] = {
        "react-native": "react-native",
        "expo": "expo",
        "next": "nextjs",
        "nuxt": "nuxtjs",
        "react": "react",
        "vue": "vue",
        "angular": "angular",
        "@angular/core": "angular",
        "svelte": "svelte",
        "express": "express",
        "fastify": "fastify",
        "nestjs": "nestjs",
        "@nestjs/core": "nestjs",
        "hono": "hono",
        "electron": "electron",
    }

    # Tech stack -> domain mapping (priority order)
    DOMAIN_SIGNALS: ClassVar[dict[str, str]] = {
        # Mobile first (most specific)
        "react-native": "mobile",
        "expo": "mobile",
        "flutter": "mobile",
        "ios": "mobile",
        "swift": "mobile",
        "kotlin": "mobile",
        # Backend
        "fastapi": "backend",
        "django": "backend",
        "flask": "backend",
        "express": "backend",
        "fastify": "backend",
        "nestjs": "backend",
        "hono": "backend",
        "spring": "backend",
        "rails": "backend",
        # Frontend
        "nextjs": "frontend",
        "nuxtjs": "frontend",
        "react": "frontend",
        "vue": "frontend",
        "angular": "frontend",
        "svelte": "frontend",
    }

    _BACKEND_DIR_HINTS: ClassVar[frozenset[str]] = frozenset(
        {"api", "server", "backend", "service", "services"}
    )
    _FRONTEND_DIR_HINTS: ClassVar[frozenset[str]] = frozenset(
        {"web", "app", "frontend", "client", "ui"}
    )
    _MOBILE_DIR_HINTS: ClassVar[frozenset[str]] = frozenset({"mobile", "ios", "android"})

    MAX_CHILD_SCAN_DEPTH: ClassVar[int] = 2

    _MONOREPO_SUBDIRS: ClassVar[tuple[str, ...]] = ("packages", "apps", "services", "libs")
    _DOMAIN_DIRS: ClassVar[tuple[str, ...]] = ("backend", "frontend", "mobile", "api", "web")

    def __init__(self) -> None:
        self._log = logger.bind(component="discovery")

    async def discover(self, cwd: Path | None = None) -> DiscoveryResult:
        """Main entry point: discover repos from CWD."""
        effective_cwd = cwd if cwd is not None else Path.cwd()
        self._log.debug("starting_discovery", cwd=str(effective_cwd))

        git_root = await self._find_git_root(effective_cwd)
        is_inside_repo = git_root is not None

        repos: list[DiscoveredRepo] = []

        if is_inside_repo and git_root is not None:
            monorepo_packages = await self._detect_monorepo_packages(git_root)
            if monorepo_packages:
                repos = monorepo_packages
            else:
                repo = await self._build_discovered_repo(git_root)
                repos = [repo]

                parent = git_root.parent
                # Don't scan filesystem root or very high-level dirs
                if parent != git_root and parent != parent.parent:
                    sibling_paths = await self._find_child_repos(parent)
                else:
                    sibling_paths = []
                for sibling_path in sibling_paths:
                    if sibling_path.resolve() != git_root.resolve():
                        sibling = await self._build_discovered_repo(sibling_path)
                        repos.append(sibling)
        else:
            child_paths = await self._find_child_repos(effective_cwd)
            for child_path in child_paths:
                repo = await self._build_discovered_repo(child_path)
                repos.append(repo)

        project_type = self._classify_project_type(repos, is_inside_repo)

        self._log.info(
            "discovery_complete",
            project_type=project_type,
            repo_count=len(repos),
        )
        return DiscoveryResult(
            project_type=project_type,
            repos=repos,
            cwd=effective_cwd,
            is_inside_repo=is_inside_repo,
        )

    async def _find_git_root(self, path: Path) -> Path | None:
        """Walk up from path to find the nearest .git directory."""
        result = await self._run_git(["-C", str(path), "rev-parse", "--show-toplevel"])
        if result is None:
            return None
        root = result.strip()
        if not root:
            return None
        return Path(root)

    async def _find_child_repos(
        self, parent: Path, max_depth: int = MAX_CHILD_SCAN_DEPTH
    ) -> list[Path]:
        """Scan immediate children (up to max_depth) for git repos."""
        found: list[Path] = []
        if not parent.is_dir():
            return found
        self._scan_for_repos(parent, found, current_depth=0, max_depth=max_depth)
        return found

    def _scan_for_repos(
        self,
        directory: Path,
        found: list[Path],
        current_depth: int,
        max_depth: int,
    ) -> None:
        """Recursive helper that collects git repo root paths."""
        if current_depth >= max_depth:
            return
        try:
            for child in sorted(directory.iterdir()):
                if not child.is_dir():
                    continue
                if child.name.startswith("."):
                    continue
                if (child / ".git").exists():
                    found.append(child)
                    continue
                self._scan_for_repos(
                    child, found, current_depth=current_depth + 1, max_depth=max_depth
                )
        except PermissionError:
            pass

    async def _get_github_remote(self, repo_path: Path) -> GitHubRemote | None:
        """Parse the GitHub owner/repo from git remote 'origin'."""
        url = await self._run_git(["-C", str(repo_path), "remote", "get-url", "origin"])
        if url is None:
            return None
        url = url.strip()
        if not url:
            return None

        # HTTPS: https://github.com/owner/repo.git or https://github.com/owner/repo
        https_match = re.match(r"https://github\.com/([^/]+)/([^/\s]+?)(?:\.git)?$", url)
        if https_match:
            return GitHubRemote(owner=https_match.group(1), repo=https_match.group(2))

        # SSH: git@github.com:owner/repo.git or git@github.com:owner/repo
        ssh_match = re.match(r"git@github\.com:([^/]+)/([^\s]+?)(?:\.git)?$", url)
        if ssh_match:
            return GitHubRemote(owner=ssh_match.group(1), repo=ssh_match.group(2))

        self._log.warning("non_github_remote", url=url, repo=str(repo_path))
        return None

    async def _get_default_branch(self, repo_path: Path) -> str:
        """Get the default branch name for a repo."""
        result = await self._run_git(
            ["-C", str(repo_path), "symbolic-ref", "refs/remotes/origin/HEAD"]
        )
        if result:
            parts = result.strip().split("/")
            if parts and parts[-1]:
                return parts[-1]
        return "main"

    async def _detect_tech_stack(self, repo_path: Path) -> list[str]:
        """Detect tech stack by checking for marker files."""
        stack: set[str] = set()

        for marker, techs in self.TECH_MARKERS.items():
            marker_path = repo_path / marker
            if not marker_path.exists():
                continue
            if marker == "package.json":
                detected = await self._parse_package_json(marker_path)
                stack.update(detected)
            else:
                stack.update(techs)

        return sorted(stack)

    async def _parse_package_json(self, package_json_path: Path) -> list[str]:
        """Parse package.json to detect JS/TS framework."""
        detected: list[str] = []
        try:
            content = package_json_path.read_text(encoding="utf-8")
            data: object = json.loads(content)
            if not isinstance(data, dict):
                return detected

            all_deps: set[str] = set()
            for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
                dep_section = data.get(dep_key)
                if isinstance(dep_section, dict):
                    all_deps.update(dep_section.keys())

            if "typescript" in all_deps or "@types/node" in all_deps:
                detected.append("typescript")

            for dep_name, tech in self.PACKAGE_JSON_MARKERS.items():
                if dep_name in all_deps and tech not in detected:
                    detected.append(tech)

        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._log.warning(
                "package_json_parse_error",
                path=str(package_json_path),
                error=str(exc),
            )

        return detected

    def _classify_domain(self, tech_stack: list[str], repo_path: Path) -> str:
        """Classify repo domain based on tech stack signals."""
        for tech in tech_stack:
            domain = self.DOMAIN_SIGNALS.get(tech)
            if domain:
                return domain

        dir_name = repo_path.name.lower()
        if dir_name in self._BACKEND_DIR_HINTS:
            return "backend"
        if dir_name in self._FRONTEND_DIR_HINTS:
            return "frontend"
        if dir_name in self._MOBILE_DIR_HINTS:
            return "mobile"

        return "shared"

    def _classify_project_type(self, repos: list[DiscoveredRepo], is_inside_repo: bool) -> str:
        """Determine if this is a monorepo or polyrepo."""
        if is_inside_repo and len(repos) > 1:
            return ProjectType.MONOREPO
        return ProjectType.POLYREPO

    async def _detect_monorepo_packages(self, repo_path: Path) -> list[DiscoveredRepo]:
        """For a monorepo, discover sub-packages/workspaces within it."""
        packages: list[DiscoveredRepo] = []

        # 1. Check common monorepo subdirectory patterns
        for subdir_name in self._MONOREPO_SUBDIRS:
            subdir = repo_path / subdir_name
            if subdir.is_dir():
                for child in sorted(subdir.iterdir()):
                    if child.is_dir() and not child.name.startswith("."):
                        tech_stack = await self._detect_tech_stack(child)
                        domain = self._classify_domain(tech_stack, child)
                        packages.append(
                            DiscoveredRepo(
                                path=child,
                                remote=None,
                                default_branch="main",
                                tech_stack=tech_stack,
                                domain=domain,
                                name=child.name,
                            )
                        )

        # 2. Check domain-named subdirectories at repo root
        if not packages:
            for domain_dir_name in self._DOMAIN_DIRS:
                domain_dir = repo_path / domain_dir_name
                if domain_dir.is_dir() and not (domain_dir / ".git").exists():
                    tech_stack = await self._detect_tech_stack(domain_dir)
                    if tech_stack:  # Only count as a package if it has recognizable tech
                        domain = self._classify_domain(tech_stack, domain_dir)
                        packages.append(
                            DiscoveredRepo(
                                path=domain_dir,
                                remote=None,
                                default_branch="main",
                                tech_stack=tech_stack,
                                domain=domain,
                                name=domain_dir.name,
                            )
                        )

        # 3. Check package.json workspaces field
        if not packages:
            root_pkg = repo_path / "package.json"
            if root_pkg.exists():
                try:
                    data: object = json.loads(root_pkg.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        workspaces = data.get("workspaces")
                        ws_patterns: list[str] = []
                        if isinstance(workspaces, list):
                            ws_patterns = [w for w in workspaces if isinstance(w, str)]
                        elif isinstance(workspaces, dict):
                            pkgs = workspaces.get("packages")
                            if isinstance(pkgs, list):
                                ws_patterns = [w for w in pkgs if isinstance(w, str)]
                        for pattern in ws_patterns:
                            if pattern.endswith("/*"):
                                base = (repo_path / pattern[:-2]).resolve()
                                if not str(base).startswith(str(repo_path.resolve())):
                                    self._log.warning(
                                        "workspace_outside_repo", pattern=pattern
                                    )
                                    continue
                                if base.is_dir():
                                    for child in sorted(base.iterdir()):
                                        if child.is_dir() and not child.name.startswith("."):
                                            tech_stack = await self._detect_tech_stack(child)
                                            domain = self._classify_domain(tech_stack, child)
                                            packages.append(
                                                DiscoveredRepo(
                                                    path=child,
                                                    remote=None,
                                                    default_branch="main",
                                                    tech_stack=tech_stack,
                                                    domain=domain,
                                                    name=child.name,
                                                )
                                            )
                except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    self._log.warning("workspace_parse_error", error=str(exc))

        return packages

    async def _build_discovered_repo(self, repo_path: Path) -> DiscoveredRepo:
        """Build a DiscoveredRepo for a given git repo path."""
        remote, branch, tech_stack = await asyncio.gather(
            self._get_github_remote(repo_path),
            self._get_default_branch(repo_path),
            self._detect_tech_stack(repo_path),
        )
        domain = self._classify_domain(tech_stack, repo_path)
        return DiscoveredRepo(
            path=repo_path,
            remote=remote,
            default_branch=branch,
            tech_stack=tech_stack,
            domain=domain,
            name=repo_path.name,
        )

    async def _run_git(self, args: list[str], cwd: Path | None = None) -> str | None:
        """Run a git command and return stdout, or None on failure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd is not None else None,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                self._log.debug(
                    "git_command_failed",
                    args=args,
                    returncode=proc.returncode,
                    stderr=stderr.decode(errors="replace").strip(),
                )
                return None
            return stdout.decode(errors="replace")
        except (OSError, FileNotFoundError) as exc:
            self._log.warning("git_not_found", error=str(exc))
            return None
