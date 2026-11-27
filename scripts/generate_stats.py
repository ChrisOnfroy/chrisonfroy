"""Genera las tarjetas de actividad del perfil con la API de GitHub (sin dependencias)."""
import json
import os
import pathlib
import urllib.request
from html import escape

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalPullRequestReviewContributions
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


def total_commits(login, token):
    request = urllib.request.Request(
        f"https://api.github.com/search/commits?q=author:{login}&per_page=1",
        headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["total_count"]


def calculate_rank(commits, prs, issues, reviews, stars, followers):
    """Fórmula de github-readme-stats (MIT, (c) 2020 Anurag Hazra), con todos los commits.

    Devuelve la letra y el percentil (menor es mejor).
    """

    def exponential(x):
        return 1 - 2**-x

    def log_normal(x):
        return x / (1 + x)

    weighted = (
        2 * exponential(commits / 1000)
        + 3 * exponential(prs / 50)
        + 1 * exponential(issues / 25)
        + 1 * exponential(reviews / 2)
        + 4 * log_normal(stars / 50)
        + 1 * log_normal(followers / 10)
    )
    percentile = (1 - weighted / 12) * 100
    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    level = next(name for limit, name in zip(thresholds, levels) if percentile <= limit)
    return level, percentile


def card(title, height, content):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="{height}" viewBox="0 0 420 {height}" '
        f'role="img" aria-label="{title}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif">'
        f'<rect width="420" height="{height}" rx="14" fill="#231A33"/>'
        f'<text x="24" y="36" font-size="18" font-weight="700" fill="#F6B26B">{title}</text>{content}</svg>'
    )


def activity_card(user, repos, commits):
    year = user["contributionsCollection"]
    stars = sum(repo["stargazerCount"] for repo in repos)
    prs = user["pullRequests"]["totalCount"]
    level, percentile = calculate_rank(
        commits,
        prs,
        user["issues"]["totalCount"],
        year["totalPullRequestReviewContributions"],
        stars,
        user["followers"]["totalCount"],
    )
    rows = [
        ("Contributions (last year)", year["contributionCalendar"]["totalContributions"]),
        ("Commits (all time)", commits),
        ("Pull requests (all time)", prs),
        ("Public repositories", user["repositories"]["totalCount"]),
        ("Stars received", stars),
    ]
    content = "".join(
        f'<text x="24" y="{72 + i * 27}" font-size="14" fill="#FFE8C7">{label}</text>'
        f'<text x="270" y="{72 + i * 27}" font-size="14" font-weight="700" text-anchor="end" fill="#FFF6EA">{value:,}</text>'
        for i, (label, value) in enumerate(rows)
    )
    # Anillo de la calificación: 2 * pi * 44 = 276.46
    filled = 276.46 * (100 - percentile) / 100
    content += (
        '<circle cx="345" cy="112" r="44" fill="none" stroke="#49294A" stroke-width="8"/>'
        '<circle cx="345" cy="112" r="44" fill="none" stroke="#F6B26B" stroke-width="8" stroke-linecap="round" '
        f'stroke-dasharray="{filled:.1f} 276.46" transform="rotate(-90 345 112)"/>'
        f'<text x="345" y="122" font-size="28" font-weight="700" text-anchor="middle" fill="#FFF6EA">{level}</text>'
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
    login, token = os.environ["GITHUB_LOGIN"], os.environ["GITHUB_TOKEN"]
    user, repos = fetch(login, token)
    output = pathlib.Path("dist")
    output.mkdir(exist_ok=True)
    (output / "activity.svg").write_text(activity_card(user, repos, total_commits(login, token)), encoding="utf-8")
    (output / "languages.svg").write_text(languages_card(repos), encoding="utf-8")


if __name__ == "__main__":
    main()
