#!/usr/bin/env python3
"""GitHub Telemetry and Metrics Extraction Engine with Robust Error Handling."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TelemetryExtractor")

DEFAULT_BOT_ACCOUNTS: Final[frozenset[str]] = frozenset({
    "actions-user",
    "github-actions[bot]",
    "dependabot[bot]",
    "dependabot-preview[bot]",
    "imgbot[bot]",
    "greenkeeper[bot]",
    "renovate[bot]",
    "snyk-bot",
})

REFERRER_CHANNELS: Final[tuple[tuple[str, str, str], ...]] = (
    ("linkedin", "LinkedIn", "share-2"),
    ("telegram", "Telegram", "send"),
    ("t.me", "Telegram", "send"),
    ("google", "Google Search", "search"),
    ("github", "GitHub", "github"),
    ("twitter", "X (Twitter)", "twitter"),
    ("t.co", "X (Twitter)", "twitter"),
    ("x.com", "X (Twitter)", "twitter"),
    ("facebook", "Facebook", "share-2"),
    ("fb.me", "Facebook", "share-2"),
    ("reddit", "Reddit", "message-square"),
    ("youtube", "YouTube", "video"),
)


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────
class TelemetryError(Exception):
    """Base domain exception for telemetry pipeline operations."""


class GitHubCLIError(TelemetryError):
    """Raised when GitHub CLI operations fail critically."""


class ConfigurationError(TelemetryError):
    """Raised when configuration parsing or validation fails."""


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION MODELS
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(slots=True, frozen=True)
class BrandConfig:
    """Branding presentation attributes for the dashboard."""

    prefix: str = "open"
    middle: str = "source"
    suffix: str = ".stats"
    prefix_color: str = "#22c55e"
    suffix_color: str = "#f43f5e"
    tagline: str = "TELEMETRÍA & OBSERVABILIDAD"


@dataclass(slots=True, frozen=True)
class RepoVisualOverride:
    """Custom overrides for repository presentation cards."""

    badge: Optional[str] = None
    featured: bool = False
    accent_color: str = "border-t-zinc-700"
    icon: str = "box"


@dataclass(slots=True, frozen=True)
class ExtractorConfig:
    """Runtime configuration resolved from environment and JSON."""

    target: str = "shellaquiles"
    is_org: bool = True
    title: str = "stats — Telemetría & Métricas Open Source"
    brand: BrandConfig = field(default_factory=BrandConfig)
    links: dict[str, str] = field(default_factory=dict)
    exclude_repos: frozenset[str] = field(default_factory=frozenset)
    repo_overrides: dict[str, RepoVisualOverride] = field(default_factory=dict)
    output_json: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data.json")

    @classmethod
    def from_source(cls, config_path: Optional[Path] = None) -> ExtractorConfig:
        """Construct configuration prioritizing env vars over file settings."""
        file_path = config_path or Path(os.getenv("STATS_CONFIG_FILE", "config.json"))
        file_data: dict[str, Any] = {}

        if file_path.is_file():
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    file_data = json.load(f)
            except json.JSONDecodeError as exc:
                logger.error("JSON syntax error in config '%s': %s", file_path, exc)
                raise ConfigurationError(f"Invalid JSON in config file: {file_path}") from exc
            except OSError as exc:
                logger.warning("Could not open config file '%s': %s", file_path, exc)

        # 1. Target resolution: Env var -> config.json -> GITHUB_REPOSITORY_OWNER -> gh cli / git remote
        target = os.getenv("STATS_TARGET") or file_data.get("target")
        if not target or target == "USER" or target == "TU_USUARIO":
            # GitHub Actions runner provee GITHUB_REPOSITORY_OWNER automáticamente
            target = os.getenv("GITHUB_REPOSITORY_OWNER")
            
        if not target:
            # En entorno local, intentar obtener el usuario autenticado en gh
            try:
                auth_user = cls._run_gh("api", "user")
                if auth_user and auth_user.get("login"):
                    target = auth_user["login"]
            except Exception:
                pass

        if not target:
            # Fallback a origin remote de git
            try:
                git_remote = subprocess.check_output(["git", "config", "--get", "remote.origin.url"], text=True).strip()
                if "github.com" in git_remote:
                    # git@github.com:owner/repo.git or https://github.com/owner/repo.git
                    clean_path = git_remote.split("github.com")[-1].lstrip("/:").removesuffix(".git")
                    target = clean_path.split("/")[0]
            except Exception:
                pass

        target = target or "shellaquiles"
        logger.info("Resolved target profile/org: '%s'", target)
        
        # Auto-detección de is_org desde la API si no viene forzado
        if "STATS_IS_ORG" in os.environ:
            is_org = os.getenv("STATS_IS_ORG", "").lower() in ("true", "1")
        elif "is_org" in file_data:
            is_org = bool(file_data["is_org"])
        else:
            try:
                user_info = cls._run_gh("api", f"users/{target}")
                is_org = bool(user_info and user_info.get("type") == "Organization")
            except Exception:
                is_org = False
        title = os.getenv("STATS_TITLE") or file_data.get(
            "title", f"stats.{target} — Telemetría Open Source"
        )

        brand_data = file_data.get("brand", {})
        brand = BrandConfig(
            prefix=os.getenv("STATS_BRAND_PREFIX") or brand_data.get("prefix", target[:5] if len(target) >= 5 else target),
            middle=os.getenv("STATS_BRAND_MIDDLE") or brand_data.get("middle", target[5:] if len(target) >= 5 else ""),
            suffix=os.getenv("STATS_BRAND_SUFFIX") or brand_data.get("suffix", ".org" if is_org else ".dev"),
            prefix_color=os.getenv("STATS_BRAND_PREFIX_COLOR") or brand_data.get("prefix_color", "#22c55e"),
            suffix_color=os.getenv("STATS_BRAND_SUFFIX_COLOR") or brand_data.get("suffix_color", "#f43f5e"),
            tagline=os.getenv("STATS_TAGLINE") or brand_data.get("tagline", "ECOSISTEMA OPEN SOURCE"),
        )

        links_data = file_data.get("links", {})
        links = {
            "github": os.getenv("STATS_GITHUB_URL") or links_data.get("github", f"https://github.com/{target}"),
            "website": os.getenv("STATS_WEBSITE_URL") or links_data.get("website", f"https://shellaquiles.org"),
        }

        env_exclude = os.getenv("STATS_EXCLUDE_REPOS")
        if env_exclude:
            exclude_repos = frozenset(r.strip() for r in env_exclude.split(",") if r.strip())
        else:
            exclude_repos = frozenset(file_data.get("exclude_repos", []))

        raw_overrides = file_data.get("custom_repo_overrides", {})
        repo_overrides = {
            name: RepoVisualOverride(
                badge=opts.get("badge"),
                featured=opts.get("featured", False),
                accent_color=opts.get("accent_color", "border-t-zinc-700"),
                icon=opts.get("icon", "box"),
            )
            for name, opts in raw_overrides.items()
        }

        output_path = Path(os.getenv("STATS_DATA_OUTPUT", "data.json"))

        return cls(
            target=target,
            is_org=is_org,
            title=title,
            brand=brand,
            links=links,
            exclude_repos=exclude_repos,
            repo_overrides=repo_overrides,
            output_json=output_path,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CORE TELEMETRY EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────
class GitHubTelemetryExtractor:
    """Extracts, normalizes, and aggregates telemetry metrics from GitHub."""

    __slots__ = ("config",)

    def __init__(self, config: ExtractorConfig) -> None:
        self.config = config

    @staticmethod
    def _run_gh(*args: str) -> Any:
        """Execute gh CLI command with structured error diagnostics."""
        try:
            res = subprocess.run(
                ["gh", *args],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            return json.loads(res.stdout)
        except subprocess.TimeoutExpired as exc:
            logger.error("GitHub CLI command timed out: %s", " ".join(args))
            return None
        except subprocess.CalledProcessError as exc:
            logger.debug("gh command failed ('%s'): %s", " ".join(args), exc.stderr.strip())
            return None
        except json.JSONDecodeError as exc:
            logger.warning("Failed parsing JSON output from gh command '%s': %s", " ".join(args), exc)
            return None
        except FileNotFoundError:
            logger.critical("GitHub CLI ('gh') is not installed or not in system PATH.")
            raise GitHubCLIError("GitHub CLI ('gh') binary was not found.") from None

    @classmethod
    def _gh_api(cls, endpoint: str) -> Any:
        """Call GitHub API via GitHub CLI and return parsed JSON."""
        return cls._run_gh("api", endpoint)

    @staticmethod
    def normalize_referrer(raw_name: Optional[str]) -> tuple[str, str]:
        """Map referrer strings to canonical channels and icons."""
        if not raw_name:
            return "Directo", "globe"
        lower_name = raw_name.lower()
        for pattern, canonical, icon in REFERRER_CHANNELS:
            if pattern in lower_name:
                return canonical, icon
        return raw_name, "globe"

    @staticmethod
    def is_bot(login: Optional[str]) -> bool:
        """Identify automated bot and service accounts."""
        return not login or login in DEFAULT_BOT_ACCOUNTS or login.endswith("[bot]")

    def discover_repositories(self) -> list[str]:
        """Query target for all active, non-archived public source repositories."""
        logger.info("Discovering public source repositories for '%s'...", self.config.target)
        payload = self._run_gh(
            "repo",
            "list",
            self.config.target,
            "--source",
            "--json",
            "name,isArchived,isFork,isPrivate",
            "--limit",
            "100",
        )
        if not isinstance(payload, list):
            logger.warning("Repository discovery returned no valid repositories or failed.")
            return []

        discovered = [
            repo["name"]
            for repo in payload
            if not repo.get("isArchived")
            and not repo.get("isPrivate")
            and not repo.get("isFork")
            and repo.get("name") not in self.config.exclude_repos
        ]
        logger.info("Discovered %d active source repositories: %s", len(discovered), ", ".join(discovered))
        return discovered

    def _resolve_visuals(self, repo_name: str, language: str) -> tuple[Optional[str], bool, str, str]:
        """Resolve visual badges, border accents and icons."""
        if repo_name in self.config.repo_overrides:
            ov = self.config.repo_overrides[repo_name]
            return ov.badge, ov.featured, ov.accent_color, ov.icon

        lang = language.lower()
        if "python" in lang:
            return None, False, "border-t-[#1e3a8a]", "code-2"
        if "javascript" in lang or "typescript" in lang:
            return None, False, "border-t-[#b45309]", "layout"
        if "shell" in lang or "bash" in lang:
            return None, False, "border-t-[#046a38]", "terminal"
        if "css" in lang or "html" in lang:
            return None, False, "border-t-zinc-400", "file-code"
        return None, False, "border-t-zinc-600", "folder-git-2"

    def fetch_repository_metrics(self, repo_name: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Collect all metrics for a single repository with individual fallback isolation."""
        full_repo = f"{self.config.target}/{repo_name}"

        info = self._run_gh(
            "repo",
            "view",
            full_repo,
            "--json",
            "name,description,url,homepageUrl,createdAt,updatedAt,pushedAt,stargazerCount,forkCount,diskUsage,licenseInfo,repositoryTopics,primaryLanguage",
        ) or {}

        # Traffic endpoints require repo push permissions, gracefully handle empty responses
        views_data = self._gh_api(f"repos/{full_repo}/traffic/views") or {}
        clones_data = self._gh_api(f"repos/{full_repo}/traffic/clones") or {}
        raw_referrers = self._gh_api(f"repos/{full_repo}/traffic/popular/referrers") or []
        releases = self._gh_api(f"repos/{full_repo}/releases") or []
        prs = self._run_gh("pr", "list", "-R", full_repo, "--state", "all", "--json", "number") or []
        contribs = self._gh_api(f"repos/{full_repo}/contributors") or []

        # GitHub Pages check
        pages_data = self._gh_api(f"repos/{full_repo}/pages") or {}
        has_pages = bool(pages_data.get("html_url"))
        pages_url = pages_data.get("html_url") or info.get("homepageUrl") or ""

        valid_contribs = [c for c in contribs if isinstance(c, dict) and not self.is_bot(c.get("login"))]
        total_commits = sum(c.get("contributions", 0) for c in valid_contribs)

        # Referrer aggregation
        normalized_refs: dict[str, dict[str, Any]] = {}
        for r in raw_referrers:
            if not isinstance(r, dict):
                continue
            canon, icon = self.normalize_referrer(r.get("referrer"))
            entry = normalized_refs.setdefault(canon, {"name": canon, "views": 0, "uniques": 0, "icon": icon})
            entry["views"] += r.get("count", 0)
            entry["uniques"] += r.get("uniques", 0)

        primary_lang = (info.get("primaryLanguage") or {}).get("name", "Other")
        badge, featured, accent_color, icon = self._resolve_visuals(repo_name, primary_lang)
        topics = [t["name"] for t in (info.get("repositoryTopics") or []) if isinstance(t, dict) and "name" in t]
        license_name = (info.get("licenseInfo") or {}).get("name", "None")
        clean_license = (
            license_name.replace(" License", "")
            .replace("General Public v3.0", "GPL-3.0")
            .replace("General Public License", "GPL")
        )

        repo_dict = {
            "name": info.get("name", repo_name),
            "description": info.get("description") or "",
            "url": info.get("url", f"https://github.com/{full_repo}"),
            "homepageUrl": info.get("homepageUrl") or "",
            "has_pages": has_pages,
            "pages_url": pages_url,
            "created_at": (info.get("createdAt") or "2026-01-01")[:10],
            "stars": info.get("stargazerCount", 0),
            "forks": info.get("forkCount", 0),
            "commits": total_commits,
            "contributors": len(valid_contribs) if valid_contribs else 1,
            "language": primary_lang,
            "license": clean_license,
            "clones_14d": clones_data.get("count", 0),
            "clones_uniques_14d": clones_data.get("uniques", 0),
            "views_14d": views_data.get("count", 0),
            "uniques_14d": views_data.get("uniques", 0),
            "releases": len(releases) if isinstance(releases, list) else 0,
            "prs": len(prs) if isinstance(prs, list) else 0,
            "featured": featured,
            "badge": badge,
            "icon": icon,
            "accentColor": accent_color,
            "topics": topics,
            "referrers": list(normalized_refs.values()),
        }

        return repo_dict, list(normalized_refs.values()), valid_contribs

    def run(self) -> None:
        """Execute full extraction pipeline and export data.json with file I/O safety."""
        repositories = self.discover_repositories()
        if not repositories:
            logger.warning("No public repositories discovered. Writing empty dataset structure.")

        repos_data: list[dict[str, Any]] = []
        global_referrers: dict[str, dict[str, Any]] = {}
        global_contributors: dict[str, dict[str, Any]] = {}

        for repo_name in repositories:
            logger.info("Processing repository: %s/%s...", self.config.target, repo_name)
            try:
                repo_item, repo_refs, repo_contribs = self.fetch_repository_metrics(repo_name)
                repos_data.append(repo_item)

                for ref in repo_refs:
                    entry = global_referrers.setdefault(
                        ref["name"], {"name": ref["name"], "views": 0, "uniques": 0, "icon": ref["icon"]}
                    )
                    entry["views"] += ref["views"]
                    entry["uniques"] += ref["uniques"]

                for c in repo_contribs:
                    login = c["login"]
                    entry = global_contributors.setdefault(
                        login,
                        {
                            "login": login,
                            "avatar_url": c.get("avatar_url"),
                            "html_url": c.get("html_url"),
                            "contributions": 0,
                            "repos_count": 0,
                            "repos": [],
                        },
                    )
                    entry["contributions"] += c.get("contributions", 0)
                    entry["repos_count"] += 1
                    entry["repos"].append(repo_name)
            except Exception as exc:
                logger.error("Unexpected error processing '%s': %s", repo_name, exc, exc_info=True)
                continue

        sorted_contributors = sorted(
            global_contributors.values(), key=lambda x: x["contributions"], reverse=True
        )
        sorted_referrers = sorted(
            global_referrers.values(), key=lambda x: x["views"], reverse=True
        )

        # Computar fecha de inicio más antigua automáticamente (Earliest Repo Created At)
        creation_dates = [d["created_at"] for d in repos_data if d.get("created_at")]
        earliest_date = min(creation_dates) if creation_dates else "2026-01-01"
        
        # Mapeo a formato legible en español (ej. AGOSTO 2025)
        month_names = {
            "01": "ENERO", "02": "FEBRERO", "03": "MARZO", "04": "ABRIL",
            "05": "MAYO", "06": "JUNIO", "07": "JULIO", "08": "AGOSTO",
            "09": "SEPTIEMBRE", "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE"
        }
        parts = earliest_date.split("-")
        if len(parts) >= 2 and parts[1] in month_names:
            auto_tagline = f"ACTIVO DESDE {month_names[parts[1]]} {parts[0]}"
        else:
            auto_tagline = f"ACTIVO DESDE {earliest_date[:4]}"

        brand_dict = asdict(self.config.brand)
        if not os.getenv("STATS_TAGLINE"):
            brand_dict["tagline"] = auto_tagline

        version_file = Path("VERSION")
        engine_version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "1.0.0"

        payload = {
            "meta": {
                "version": engine_version,
                "target": self.config.target,
                "is_org": self.config.is_org,
                "title": self.config.title,
                "active_since": earliest_date,
                "brand": brand_dict,
                "links": self.config.links,
            },
            "summary": {
                "total_stars": sum(d["stars"] for d in repos_data),
                "total_forks": sum(d["forks"] for d in repos_data),
                "total_commits": sum(d["commits"] for d in repos_data),
                "total_clones_14d": sum(d["clones_14d"] for d in repos_data),
                "total_clones_uniques_14d": sum(d["clones_uniques_14d"] for d in repos_data),
                "total_views_14d": sum(d["views_14d"] for d in repos_data),
                "total_views_uniques_14d": sum(d["uniques_14d"] for d in repos_data),
                "total_releases": sum(d["releases"] for d in repos_data),
                "total_prs": sum(d["prs"] for d in repos_data),
                "total_repos": len(repos_data),
                "total_contributors": len(sorted_contributors),
            },
            "repos": repos_data,
            "referrers": sorted_referrers,
            "contributors": sorted_contributors,
        }

        try:
            self.config.output_json.parent.mkdir(parents=True, exist_ok=True)
            with self.config.output_json.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info("✅ Telemetry exported successfully to %s", self.config.output_json)
        except OSError as exc:
            logger.critical("Failed writing output file '%s': %s", self.config.output_json, exc)
            raise TelemetryError(f"Could not write destination file: {self.config.output_json}") from exc

        self._sync_index_html_meta(self.config.target)

    def _sync_index_html_meta(self, target: str) -> None:
        """Keep static OpenGraph meta tags in index.html in sync with the detected target user."""
        index_html_path = Path(__file__).resolve().parent.parent / "index.html"
        if not index_html_path.is_file():
            return
        try:
            content = index_html_path.read_text(encoding="utf-8")
            import re
            content = re.sub(
                r'<meta property="og:title" content="[^"]*" id="og-title" />',
                f'<meta property="og:title" content="Estadísticas de @{target} en GitHub 📊 ¡Crea tu dashboard gratis!" id="og-title" />',
                content
            )
            content = re.sub(
                r'<meta name="twitter:title" content="[^"]*" id="twitter-title" />',
                f'<meta name="twitter:title" content="Estadísticas de @{target} en GitHub 📊 ¡Crea tu dashboard gratis!" id="twitter-title" />',
                content
            )
            index_html_path.write_text(content, encoding="utf-8")
            logger.info("✔ Synced OpenGraph meta tags in index.html for target '@%s'", target)
        except OSError as exc:
            logger.warning("Could not sync index.html meta tags: %s", exc)


def main() -> None:
    """CLI entrypoint with graceful exit codes."""
    parser = argparse.ArgumentParser(description="Extract GitHub telemetry into data.json.")
    parser.add_argument("--config", "-c", type=Path, default=None, help="Path to config.json")
    args = parser.parse_args()

    try:
        config = ExtractorConfig.from_source(config_path=args.config)
        extractor = GitHubTelemetryExtractor(config=config)
        extractor.run()
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    except GitHubCLIError as exc:
        logger.error("GitHub CLI runtime error: %s", exc)
        sys.exit(2)
    except TelemetryError as exc:
        logger.error("Telemetry engine error: %s", exc)
        sys.exit(3)
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
