"""GitHub API integration for owner resolution."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github import Github

logger = logging.getLogger(__name__)


def get_github_token() -> str:
    """Read GITHUB_TOKEN from environment."""
    return os.environ.get("GITHUB_TOKEN", "")


def get_github_client(token: str) -> Github | None:
    """Create a PyGithub client, or None if token is empty."""
    if not token:
        return None
    from github import Github as GithubClient

    return GithubClient(token)


def resolve_handles(
    emails: set[str],
    token: str,
) -> dict[str, str]:
    """Map git commit emails to GitHub @handles."""
    client = get_github_client(token)
    if client is None:
        return {}
    cache: dict[str, str] = {}
    for email in sorted(emails):
        handle = _lookup_handle(client, email)
        if handle is not None:
            cache[email] = handle
    return cache


def _lookup_handle(client: Github, email: str) -> str | None:
    """Look up a single email via GitHub user search API."""
    try:
        users = client.search_users(f"{email} in:email")
        for user in users:
            if user.login:
                return f"@{user.login}"
        return None
    except Exception:
        logger.warning("Failed to resolve GitHub handle for %s", email)
        return None


def map_owners(
    owners: dict[str, tuple[str, ...]],
    token: str,
) -> dict[str, tuple[str, ...]]:
    """Replace emails with @handles where possible. Unresolved stay as-is."""
    all_emails: set[str] = set()
    for owner_tuple in owners.values():
        all_emails.update(owner_tuple)

    email_to_handle = resolve_handles(all_emails, token)
    if not email_to_handle:
        return owners

    return {
        path: tuple(email_to_handle.get(owner, owner) for owner in owner_tuple)
        for path, owner_tuple in owners.items()
    }


def create_team_resolver(
    token: str,
    org: str,
) -> Callable[[tuple[str, ...]], str | None] | None:
    """Create a team resolver with pre-fetched team data.

    Returns None if token/org are empty or API fails.
    """
    if not token or not org:
        return None
    client = get_github_client(token)
    if client is None:
        return None
    team_data = _get_org_teams(client, org)
    if not team_data:
        return None

    def _resolve(owners: tuple[str, ...]) -> str | None:
        owner_logins = {owner.lstrip("@") for owner in owners}
        matching_teams: list[str] = []
        for team_slug, members in team_data.items():
            if owner_logins.issubset(members):
                matching_teams.append(team_slug)
        if not matching_teams:
            return None
        best = max(matching_teams, key=lambda t: t.count("/"))
        return f"@{org}/{best}"

    return _resolve


def _get_org_teams(
    client: Github,
    org: str,
) -> dict[str, set[str]]:
    """Fetch all teams in an org with their member login sets."""
    try:
        gh_org = client.get_organization(org)
        teams: dict[str, set[str]] = {}
        for team in gh_org.get_teams():
            members = {m.login for m in team.get_members()}
            teams[team.slug] = members
        return teams
    except Exception:
        logger.warning("Failed to fetch teams for org %s", org)
        return {}
