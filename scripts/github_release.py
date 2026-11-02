"""Create a GitHub release from a tested tag and publish all three platform ZIPs."""
import argparse
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "CobbiFantom/desktop-jenkins")
API = "https://api.github.com"
ASSETS = ("PDFUkrainian-Darwin-arm64.zip", "PDFUkrainian-Linux-x86_64.zip",
          "PDFUkrainian-Windows-x86_64.zip")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class ReleaseError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ReleaseError("GITHUB_TOKEN is missing")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", REPOSITORY):
            raise ReleaseError("Invalid GITHUB_REPOSITORY")
        self.opener = build_opener(NoRedirects())

    def request(self, path, *, method="GET", fields=None, upload=None):
        url = API + "/repos/" + REPOSITORY + path if path.startswith("/") else path
        parsed = urlsplit(url)
        host = "uploads.github.com" if upload else "api.github.com"
        if (parsed.scheme != "https" or parsed.netloc != host or parsed.fragment
                or not parsed.path.startswith("/repos/" + REPOSITORY + "/")):
            raise ReleaseError("Unexpected GitHub API URL")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "pdf-ukrainian-release",
        }
        data = None
        if fields is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(fields).encode("utf-8")
        if upload:
            headers.update({"Content-Type": "application/zip",
                            "Content-Length": str(os.fstat(upload.fileno()).st_size)})
            data = upload
            method = "POST"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=120) as response:
                return json.load(response)
        except HTTPError as error:
            status = error.code
            error.close()
            # Never log response bodies, request headers or the token.
            raise ReleaseError(f"GitHub API HTTP {status}; check permissions and release state", status) from None
        except (URLError, TimeoutError, OSError, ValueError, HTTPException):
            raise ReleaseError("GitHub API request failed; check connectivity and rerun the workflow") from None

    def release(self, tag):
        try:
            release = self.request("/releases/tags/" + quote(validate_tag(tag), safe=""))
        except ReleaseError as error:
            if error.status == 404:
                # The tag endpoint may omit drafts; find a partially uploaded draft on retries.
                page = 1
                while True:
                    items = self.request(f"/releases?per_page=100&page={page}")
                    for item in items:
                        if item.get("tag_name") == tag:
                            return item
                    if len(items) < 100:
                        return None
                    page += 1
            raise
        if release.get("tag_name") != tag:
            raise ReleaseError("GitHub returned a different release tag")
        return release

    def commit(self, tag):
        obj = self.request("/git/ref/tags/" + quote(validate_tag(tag), safe=""))["object"]
        seen = set()
        for _ in range(10):
            sha = obj.get("sha", "")
            if not SHA.fullmatch(sha) or sha in seen:
                break
            seen.add(sha)
            if obj.get("type") == "commit":
                return sha
            if obj.get("type") != "tag":
                break
            obj = self.request("/git/tags/" + sha)["object"]
        raise ReleaseError("Release tag does not resolve to a Git commit")

    def assets(self, release):
        page = 1
        while True:
            items = self.request(f"/releases/{release['id']}/assets?per_page=100&page={page}")
            yield from items
            if len(items) < 100:
                return
            page += 1

    def create_release(self, tag, commit):
        # Upload into a draft first, including when immutable releases are enabled.
        return self.request("/releases", method="POST", fields={
            "tag_name": tag, "target_commitish": commit, "name": tag,
            "draft": True, "generate_release_notes": True,
        })

    def publish_release(self, release):
        updated = self.request(f"/releases/{release['id']}", method="PATCH", fields={"draft": False})
        if updated.get("draft") or not updated.get("published_at"):
            raise ReleaseError("GitHub did not confirm release publication")


def validate_tag(tag):
    if not tag or len(tag) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in tag):
        raise ReleaseError("Invalid release tag")
    return tag


def asset_label(name, commit):
    return f"{name} (git:{commit})"


def matches_source(asset, commit):
    return (asset.get("state") == "uploaded"
            and asset.get("label") in ("git:" + commit, asset_label(asset["name"], commit)))


def upload_url(release):
    url = release["upload_url"].split("{", 1)[0]
    expected = f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release['id']}/assets"
    if url != expected:
        raise ReleaseError("Unexpected GitHub release upload URL")
    return url


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def publish(api, tag, commit, directory):
    validate_tag(tag)
    if not SHA.fullmatch(commit):
        raise ReleaseError("Expected a full Git commit SHA")
    directory = Path(directory)
    if {path.name for path in directory.glob("*.zip")} != set(ASSETS):
        raise ReleaseError("Expected exactly the macOS ARM64, Linux x86_64 and Windows x86_64 ZIPs")
    for name in ASSETS:
        if not zipfile.is_zipfile(directory / name):
            raise ReleaseError(f"Invalid ZIP archive: {name}")
    if api.commit(tag) != commit:
        raise ReleaseError("Release tag moved after checkout; refusing to publish different source code")
    release = api.release(tag) or api.create_release(tag, commit)
    url = upload_url(release)
    existing = {asset["name"]: asset for asset in api.assets(release)}
    # Refuse all conflicts before the first upload. Never delete or overwrite assets.
    for name in ASSETS:
        if name in existing and not matches_source(existing[name], commit):
            raise ReleaseError(f"Existing asset {name} has unknown provenance or is incomplete; review it in GitHub")
    for name in ASSETS:
        if name in existing:
            print(f"Already published: {name}")
            continue
        if api.commit(tag) != commit:
            raise ReleaseError("Release tag moved during publication; refusing further uploads")
        label = asset_label(name, commit)
        path = directory / name
        expected_digest = digest(path)
        with path.open("rb") as stream:
            result = api.request(url + "?" + urlencode({"name": name, "label": label}), upload=stream)
        if (result.get("name") != name or not matches_source(result, commit)
                or result.get("size") != path.stat().st_size or result.get("digest") != expected_digest):
            raise ReleaseError(f"GitHub did not confirm ZIP integrity: {name}")
        print(f"Uploaded and verified: {name}")
    ready = {asset["name"] for asset in api.assets(release) if matches_source(asset, commit)}
    if api.commit(tag) != commit or not set(ASSETS) <= ready:
        raise ReleaseError("Final release verification failed")
    if release.get("draft"):
        api.publish_release(release)
    print(f"Release ready: https://github.com/{REPOSITORY}/releases/tag/{quote(tag, safe='')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["publish"])
    parser.add_argument("tag")
    parser.add_argument("commit")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        publish(GitHub(), args.tag, args.commit, args.directory)
    except (ReleaseError, KeyError, TypeError, OSError) as error:
        message = str(error) if isinstance(error, ReleaseError) else "Unexpected release data or filesystem error"
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
