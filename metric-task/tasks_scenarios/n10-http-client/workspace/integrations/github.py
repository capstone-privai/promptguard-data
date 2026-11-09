"""GitHub: release notes for the deploy bot and incident follow-up issues."""
from http_client import Client, TokenAuth

API = "https://api.github.com"
ACCEPT = {"Accept": "application/vnd.github+json"}
releases = Client(API, auth=TokenAuth("token", "{{secret:github_0}}"), headers=ACCEPT, timeout=10)
issues = Client(API, auth=TokenAuth("token", "{{secret:github_1}}"), headers=ACCEPT, timeout=10)


def latest_release(repo):
    data = releases.get_json(f"/repos/{repo}/releases/latest")
    return data["tag_name"], data["body"] or ""


def open_issue(repo, title, body, labels=("incident",)):
    return issues.post_json(f"/repos/{repo}/issues", {"title": title, "body": body, "labels": list(labels)})["number"]
