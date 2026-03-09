"""Tests for CWD-aware repository auto-discovery."""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING

from claudedev.core.discovery import (
    DiscoveredRepo,
    GitHubRemote,
    RepoDiscovery,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_GIT_ENV: dict[str, str] = os.environ | {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
}


async def _init_git_repo(path: Path, remote_url: str | None = None) -> None:
    """Create a bare git repo in the given directory."""
    env = _GIT_ENV | {"HOME": str(path)}

    proc = await asyncio.create_subprocess_exec(
        "git",
        "init",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    await proc.communicate()

    # Create an initial commit so symbolic-ref works
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(path),
        "commit",
        "--allow-empty",
        "-m",
        "init",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    await proc.communicate()

    if remote_url:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(path),
            "remote",
            "add",
            "origin",
            remote_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()


# ---------------------------------------------------------------------------
# _find_git_root
# ---------------------------------------------------------------------------


class TestFindGitRoot:
    async def test_find_git_root_from_subdirectory(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "myrepo"
        repo_root.mkdir()
        await _init_git_repo(repo_root)

        subdir = repo_root / "src" / "pkg"
        subdir.mkdir(parents=True)

        discovery = RepoDiscovery()
        found = await discovery._find_git_root(subdir)

        assert found is not None
        assert found.resolve() == repo_root.resolve()

    async def test_find_git_root_not_a_repo(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "notarepo"
        plain_dir.mkdir()

        discovery = RepoDiscovery()
        found = await discovery._find_git_root(plain_dir)

        assert found is None


# ---------------------------------------------------------------------------
# _get_default_branch
# ---------------------------------------------------------------------------


class TestGetDefaultBranch:
    async def test_default_branch_no_remote(self, tmp_path: Path) -> None:
        """A repo with no origin/HEAD should fall back to 'main'."""
        repo = tmp_path / "repo"
        repo.mkdir()
        await _init_git_repo(repo)

        discovery = RepoDiscovery()
        branch = await discovery._get_default_branch(repo)

        # No remote set, symbolic-ref fails -> fallback to "main"
        assert branch == "main"

    async def test_empty_symbolic_ref(self, tmp_path: Path) -> None:
        """When symbolic-ref returns empty string, fallback to 'main'."""
        discovery = RepoDiscovery()

        # Monkeypatch _run_git to return empty string
        original = discovery._run_git

        async def _stub(args: list[str], cwd: Path | None = None) -> str | None:
            if "symbolic-ref" in args:
                return ""
            return await original(args, cwd)

        discovery._run_git = _stub  # type: ignore[method-assign]
        branch = await discovery._get_default_branch(tmp_path)
        assert branch == "main"


# ---------------------------------------------------------------------------
# _find_child_repos
# ---------------------------------------------------------------------------


class TestFindChildRepos:
    async def test_find_child_repos(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "repo-a"
        repo_b = tmp_path / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        await _init_git_repo(repo_a)
        await _init_git_repo(repo_b)

        discovery = RepoDiscovery()
        found = await discovery._find_child_repos(tmp_path)

        found_names = {p.name for p in found}
        assert found_names == {"repo-a", "repo-b"}

    async def test_find_child_repos_skips_hidden(self, tmp_path: Path) -> None:
        visible_repo = tmp_path / "visible"
        hidden_repo = tmp_path / ".hidden"
        visible_repo.mkdir()
        hidden_repo.mkdir()
        await _init_git_repo(visible_repo)
        await _init_git_repo(hidden_repo)

        discovery = RepoDiscovery()
        found = await discovery._find_child_repos(tmp_path)

        found_names = {p.name for p in found}
        assert "visible" in found_names
        assert ".hidden" not in found_names


# ---------------------------------------------------------------------------
# _get_github_remote
# ---------------------------------------------------------------------------


class TestGetGithubRemote:
    async def test_parse_github_remote_https(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        await _init_git_repo(repo, "https://github.com/myowner/myrepo.git")

        discovery = RepoDiscovery()
        remote = await discovery._get_github_remote(repo)

        assert remote is not None
        assert remote.owner == "myowner"
        assert remote.repo == "myrepo"

    async def test_parse_github_remote_ssh(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        await _init_git_repo(repo, "git@github.com:myowner/myrepo.git")

        discovery = RepoDiscovery()
        remote = await discovery._get_github_remote(repo)

        assert remote is not None
        assert remote.owner == "myowner"
        assert remote.repo == "myrepo"

    async def test_parse_github_remote_non_github(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        await _init_git_repo(repo, "https://gitlab.com/myowner/myrepo.git")

        discovery = RepoDiscovery()
        remote = await discovery._get_github_remote(repo)

        assert remote is None

    async def test_parse_github_remote_https_no_git_suffix(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        await _init_git_repo(repo, "https://github.com/myowner/myrepo")

        discovery = RepoDiscovery()
        remote = await discovery._get_github_remote(repo)

        assert remote is not None
        assert remote.owner == "myowner"
        assert remote.repo == "myrepo"

    async def test_no_remote_returns_none(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        await _init_git_repo(repo)  # No remote

        discovery = RepoDiscovery()
        remote = await discovery._get_github_remote(repo)

        assert remote is None


# ---------------------------------------------------------------------------
# _detect_tech_stack
# ---------------------------------------------------------------------------


class TestDetectTechStack:
    async def test_detect_tech_stack_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")

        discovery = RepoDiscovery()
        stack = await discovery._detect_tech_stack(tmp_path)

        assert "python" in stack

    async def test_detect_tech_stack_react(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        discovery = RepoDiscovery()
        stack = await discovery._detect_tech_stack(tmp_path)

        assert "react" in stack

    async def test_detect_tech_stack_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        pkg = {"dependencies": {"express": "^4.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        discovery = RepoDiscovery()
        stack = await discovery._detect_tech_stack(tmp_path)

        assert "python" in stack
        assert "express" in stack

    async def test_detect_tech_stack_react_native(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"react-native": "^0.73.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        discovery = RepoDiscovery()
        stack = await discovery._detect_tech_stack(tmp_path)

        assert "react-native" in stack

    async def test_detect_tech_stack_empty_dir(self, tmp_path: Path) -> None:
        discovery = RepoDiscovery()
        stack = await discovery._detect_tech_stack(tmp_path)

        assert stack == []


# ---------------------------------------------------------------------------
# _classify_domain
# ---------------------------------------------------------------------------


class TestClassifyDomain:
    def test_classify_domain_backend(self, tmp_path: Path) -> None:
        discovery = RepoDiscovery()
        domain = discovery._classify_domain(["python", "fastapi"], tmp_path)
        assert domain == "backend"

    def test_classify_domain_frontend(self, tmp_path: Path) -> None:
        discovery = RepoDiscovery()
        domain = discovery._classify_domain(["react"], tmp_path)
        assert domain == "frontend"

    def test_classify_domain_mobile(self, tmp_path: Path) -> None:
        discovery = RepoDiscovery()
        domain = discovery._classify_domain(["react-native"], tmp_path)
        assert domain == "mobile"

    def test_classify_domain_from_dirname(self, tmp_path: Path) -> None:
        api_dir = tmp_path / "api"
        api_dir.mkdir()

        discovery = RepoDiscovery()
        domain = discovery._classify_domain([], api_dir)
        assert domain == "backend"

    def test_classify_domain_from_dirname_frontend(self, tmp_path: Path) -> None:
        web_dir = tmp_path / "web"
        web_dir.mkdir()

        discovery = RepoDiscovery()
        domain = discovery._classify_domain([], web_dir)
        assert domain == "frontend"

    def test_classify_domain_from_dirname_mobile(self, tmp_path: Path) -> None:
        mobile_dir = tmp_path / "mobile"
        mobile_dir.mkdir()

        discovery = RepoDiscovery()
        domain = discovery._classify_domain([], mobile_dir)
        assert domain == "mobile"

    def test_classify_domain_default_shared(self, tmp_path: Path) -> None:
        discovery = RepoDiscovery()
        domain = discovery._classify_domain([], tmp_path)
        assert domain == "shared"


# ---------------------------------------------------------------------------
# _classify_project_type
# ---------------------------------------------------------------------------


class TestClassifyProjectType:
    def _make_repo(self, path: Path) -> DiscoveredRepo:
        return DiscoveredRepo(
            path=path,
            remote=None,
            default_branch="main",
            tech_stack=[],
            domain="shared",
            name=path.name,
        )

    def test_classify_project_type_polyrepo_multiple(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        repos = [self._make_repo(repo_a), self._make_repo(repo_b)]

        discovery = RepoDiscovery()
        project_type = discovery._classify_project_type(repos, is_inside_repo=False)

        assert project_type == "polyrepo"

    def test_classify_project_type_single_repo(self, tmp_path: Path) -> None:
        repos = [self._make_repo(tmp_path / "myrepo")]

        discovery = RepoDiscovery()
        project_type = discovery._classify_project_type(repos, is_inside_repo=True)

        assert project_type == "polyrepo"

    def test_monorepo_detection(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "backend"
        repo_b = tmp_path / "frontend"
        repos = [self._make_repo(repo_a), self._make_repo(repo_b)]

        discovery = RepoDiscovery()
        project_type = discovery._classify_project_type(repos, is_inside_repo=True)

        assert project_type == "monorepo"


# ---------------------------------------------------------------------------
# discover — integration tests
# ---------------------------------------------------------------------------


class TestDiscover:
    async def test_discover_single_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "myrepo"
        repo.mkdir()
        await _init_git_repo(repo, "https://github.com/owner/myrepo.git")
        (repo / "pyproject.toml").write_text("[tool.poetry]\n")

        discovery = RepoDiscovery()
        result = await discovery.discover(cwd=repo)

        assert result.is_inside_repo is True
        assert len(result.repos) >= 1
        assert result.repos[0].remote is not None
        assert result.repos[0].remote.repo == "myrepo"

    async def test_discover_parent_of_repos(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "backend"
        repo_b = tmp_path / "frontend"
        repo_a.mkdir()
        repo_b.mkdir()
        await _init_git_repo(repo_a, "https://github.com/owner/backend.git")
        await _init_git_repo(repo_b, "https://github.com/owner/frontend.git")

        discovery = RepoDiscovery()
        result = await discovery.discover(cwd=tmp_path)

        assert result.is_inside_repo is False
        repo_names = {r.name for r in result.repos}
        assert "backend" in repo_names
        assert "frontend" in repo_names

    async def test_discover_monorepo_with_packages(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "monorepo"
        repo_root.mkdir()
        await _init_git_repo(repo_root)

        packages_dir = repo_root / "packages"
        packages_dir.mkdir()
        pkg_a = packages_dir / "pkg-a"
        pkg_a.mkdir()
        (pkg_a / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.0.0"}})
        )

        discovery = RepoDiscovery()
        result = await discovery.discover(cwd=repo_root)

        assert result.is_inside_repo is True
        pkg_names = {r.name for r in result.repos}
        assert "pkg-a" in pkg_names

    async def test_discover_no_repos(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        discovery = RepoDiscovery()
        result = await discovery.discover(cwd=empty_dir)

        assert result.is_inside_repo is False
        assert result.repos == []

    async def test_monorepo_with_domain_dirs(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "monorepo"
        repo_root.mkdir()
        await _init_git_repo(repo_root)

        backend_dir = repo_root / "backend"
        backend_dir.mkdir()
        (backend_dir / "pyproject.toml").write_text("[tool.poetry]\n")

        frontend_dir = repo_root / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.0.0"}})
        )

        discovery = RepoDiscovery()
        result = await discovery.discover(cwd=repo_root)

        assert result.is_inside_repo is True
        pkg_names = {r.name for r in result.repos}
        assert "backend" in pkg_names
        assert "frontend" in pkg_names
        assert result.project_type == "monorepo"


# ---------------------------------------------------------------------------
# GitHubRemote property
# ---------------------------------------------------------------------------


class TestGitHubRemote:
    def test_full_name(self) -> None:
        remote = GitHubRemote(owner="acme", repo="widget")
        assert remote.full_name == "acme/widget"
