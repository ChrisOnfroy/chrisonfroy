"""Genera las tarjetas de actividad del perfil con la API de GitHub (sin dependencias)."""
import json
import os
import pathlib
import urllib.request
from html import escape

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def graphql(login, token, cursor):
    body = json.dumps({"query": QUERY, "variables": {"login": login, "cursor": cursor}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql", data=body, headers={"Authorization": f"bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise SystemExit(f"Error de la API: {result['errors']}")
    return result["data"]["user"]


def fetch(login, token):
    cursor, repos = None, []
    while True:
        user = graphql(login, token, cursor)
        page = user["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return user, repos
        cursor = page["pageInfo"]["endCursor"]


def card(title, height, content):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="{height}" viewBox="0 0 420 {height}" '
        f'role="img" aria-label="{title}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif">'
        f'<rect width="420" height="{height}" rx="14" fill="#231A33"/>'
        f'<text x="24" y="36" font-size="18" font-weight="700" fill="#F6B26B">{title}</text>{content}</svg>'
    )


def activity_card(user, repos):
    year = user["contributionsCollection"]
    rows = [
        ("Contributions (last year)", year["contributionCalendar"]["totalContributions"]),
        ("Commits (last year)", year["totalCommitContributions"]),
        ("Pull requests (last year)", year["totalPullRequestContributions"]),
        ("Public repositories", user["repositories"]["totalCount"]),
        ("Stars received", sum(repo["stargazerCount"] for repo in repos)),
    ]
    content = "".join(
        f'<text x="24" y="{72 + i * 27}" font-size="14" fill="#FFE8C7">{label}</text>'
        f'<text x="396" y="{72 + i * 27}" font-size="14" font-weight="700" text-anchor="end" fill="#FFF6EA">{value:,}</text>'
        for i, (label, value) in enumerate(rows)
    )
    return card("GitHub activity", 200, content)


def languages_card(repos):
    sizes, colors = {}, {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#B5556A"
    total = sum(sizes.values()) or 1
    top = sorted(sizes.items(), key=lambda item: item[1], reverse=True)[:6]
    content = ""
    for i, (name, size) in enumerate(top):
        y = 64 + i * 22
        share = size / total
        content += (
            f'<text x="24" y="{y + 9}" font-size="13" fill="#FFE8C7">{escape(name)}</text>'
            f'<rect x="140" y="{y}" width="200" height="9" rx="4" fill="#49294A"/>'
            f'<rect x="140" y="{y}" width="{max(share * 200, 3):.1f}" height="9" rx="4" fill="{colors[name]}"/>'
            f'<text x="396" y="{y + 9}" font-size="12" text-anchor="end" fill="#FFF6EA">{share:.1%}</text>'
        )
    return card("Languages in public repos", 200, content)


def main():
    user, repos = fetch(os.environ["GITHUB_LOGIN"], os.environ["GITHUB_TOKEN"])
    output = pathlib.Path("dist")
    output.mkdir(exist_ok=True)
    (output / "activity.svg").write_text(activity_card(user, repos), encoding="utf-8")
    (output / "languages.svg").write_text(languages_card(repos), encoding="utf-8")


if __name__ == "__main__":
    main()
