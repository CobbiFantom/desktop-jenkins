"""Publish tested archives to existing GitHub releases; Python standard library only."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


REPOSITORY = "CobbiFantom/desktop-jenkins"
API = "https://api.github.com"
ASSETS = ("PDFUkrainian-Darwin-arm64.zip", "PDFUkrainian-Linux-x86_64.zip")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class ReleaseError(RuntimeError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirect destination.
        return None


class GitHub:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ReleaseError("GITHUB_TOKEN is missing; configure github-release-token in Jenkins")
        self.opener = build_opener(NoRedirects())

    def request(self, path, *, upload=None, fields=None):
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
            "User-Agent": "desktop-jenkins-release",
        }
        if upload:
            headers.update({"Content-Type": "application/zip",
                            "Content-Length": str(os.fstat(upload.fileno()).st_size)})
        data = upload
        if fields is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(fields).encode("utf-8")
        method = "PATCH" if fields is not None else "POST" if upload else "GET"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=120) as response:
                return json.load(response)
        except HTTPError as error:
            status = error.code
            error.close()
            # Neither response bodies nor request headers may enter Jenkins logs.
            raise ReleaseError(f"GitHub API HTTP {status}; check token permissions and release state") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ReleaseError("GitHub API request failed; retry the build after checking connectivity") from None

    def release(self, tag):
        release = self.request("/releases/tags/" + quote(validate_tag(tag), safe=""))
        if release.get("draft") or not release.get("published_at"):
            raise ReleaseError("The GitHub release must be published before building")
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
        return self.pages(f"/releases/{release['id']}/assets")

    def pages(self, path):
        page = 1
        while True:
            items = self.request(f"{path}?per_page=100&page={page}")
            yield from items
            if len(items) < 100:
                return
            page += 1


def validate_tag(tag):
    if not tag or len(tag) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in tag):
        raise ReleaseError("Invalid release tag")
    return tag


def asset_label(name, commit):
    # GitHub displays the label instead of the file name in the download list.
    return f"{name} (git:{commit})"


def matches_source(asset, commit):
    return asset.get("label") in ("git:" + commit, asset_label(asset["name"], commit))


def complete(assets, commit):
    ready = {asset["name"] for asset in assets
             if asset.get("state") == "uploaded" and matches_source(asset, commit)}
    return set(ASSETS) <= ready


def pending_tag(api):
    for release in api.pages("/releases"):
        if release.get("draft") or not release.get("published_at"):
            continue
        tag = validate_tag(release["tag_name"])
        commit = api.commit(tag)
        assets = list(api.assets(release))
        if not complete(assets, commit):
            return tag
        # Migrate the original SHA-only labels without rebuilding or replacing binaries.
        for asset in assets:
            if asset['name'] in ASSETS and asset.get('label') == 'git:' + commit:
                label = asset_label(asset['name'], commit)
                updated = api.request(f"/releases/assets/{asset['id']}", fields={"label": label})
                if updated.get('label') != label:
                    raise ReleaseError("GitHub did not confirm the download label update")
    return ""


def upload_url(release):
    url = release["upload_url"].split("{", 1)[0]
    parsed = urlsplit(url)
    expected = f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release['id']}/assets"
    if url != expected or parsed.query or parsed.fragment:
        raise ReleaseError("Unexpected GitHub release upload URL")
    return url


def publish(api, tag, commit, directory):
    if not SHA.fullmatch(commit):
        raise ReleaseError("Expected a full Git commit SHA")
    release = api.release(tag)
    if api.commit(tag) != commit:
        raise ReleaseError("Release tag moved after checkout; refusing to publish different source code")
    url = upload_url(release)
    existing = {asset["name"]: asset for asset in api.assets(release)}
    # Check all conflicts/files before uploading anything. Existing files are never deleted.
    for name in ASSETS:
        asset = existing.get(name)
        if asset and (not matches_source(asset, commit) or asset.get("state") != "uploaded"):
            raise ReleaseError(f"Existing asset {name} has unknown provenance or is incomplete; review it in GitHub")
        file = Path(directory) / name
        if not file.is_file() or not zipfile.is_zipfile(file):
            raise ReleaseError(f"Missing or invalid ZIP archive: {name}")
    for name in ASSETS:
        if name in existing:
            print(f"Already published: {name}")
            continue
        # Recheck before each upload, including after a previous upload took time.
        if api.commit(tag) != commit:
            raise ReleaseError("Release tag moved during publication; refusing further uploads")
        label = asset_label(name, commit)
        with (Path(directory) / name).open("rb") as stream:
            result = api.request(url + "?" + urlencode({"name": name, "label": label}), upload=stream)
        if result.get("state") != "uploaded" or result.get("name") != name or result.get("label") != label:
            raise ReleaseError(f"GitHub did not confirm upload of {name}")
        print(f"Published: {name}")
    if api.commit(tag) != commit or not complete(api.assets(release), commit):
        raise ReleaseError("Final release verification failed")
    print(f"Release ready: https://github.com/{REPOSITORY}/releases/tag/{quote(tag, safe='')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pending", help="Print the next published release missing our packages")
    resolve = commands.add_parser("resolve", help="Print the exact commit for a published release")
    resolve.add_argument("tag")
    upload = commands.add_parser("publish", help="Upload both tested platform archives")
    upload.add_argument("tag")
    upload.add_argument("commit")
    upload.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        api = GitHub()
        if args.command == "pending":
            print(pending_tag(api))
        elif args.command == "resolve":
            api.release(args.tag)
            print(api.commit(args.tag))
        else:
            publish(api, args.tag, args.commit, args.directory)
    except (ReleaseError, KeyError, TypeError) as error:
        message = str(error) if isinstance(error, ReleaseError) else "Unexpected GitHub API response"
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
