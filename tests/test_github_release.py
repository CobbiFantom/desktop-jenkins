import io
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import zipfile

import pytest

from scripts.github_release import ASSETS, GitHub, REPOSITORY, ReleaseError, pending_tag, publish


COMMIT = "a" * 40
TAG = "v.0.1.0"


def release(**changes):
    return {"id": 123, "tag_name": TAG, "draft": False,
            "published_at": "2026-11-02T12:00:00Z",
            "upload_url": f"https://uploads.github.com/repos/{REPOSITORY}/releases/123/assets{{?name,label}}",
            **changes}


class FakeGitHub:
    def __init__(self, assets=()):
        self.files = list(assets)
        self.uploads = []
        self.sha = COMMIT
        self.releases = [release()]

    def release(self, tag):
        assert tag == TAG
        return self.releases[0]

    def commit(self, tag):
        return self.sha

    def assets(self, target):
        return iter(self.files)

    def pages(self, path):
        assert path == "/releases"
        return iter(self.releases)

    def request(self, url, *, upload):
        query = parse_qs(urlsplit(url).query)
        assert zipfile.is_zipfile(upload)
        item = {"name": query["name"][0], "label": query["label"][0], "state": "uploaded"}
        self.uploads.append(item["name"])
        self.files.append(item)
        return item


@pytest.fixture
def packages(tmp_path):
    for name in ASSETS:
        with zipfile.ZipFile(tmp_path / name, "w") as archive:
            archive.writestr("app/test.txt", "test")
    return tmp_path


def asset(name, **changes):
    return {"name": name, "label": "git:" + COMMIT, "state": "uploaded", **changes}


def test_publish_both_platforms_and_retry_is_idempotent(packages):
    api = FakeGitHub()
    publish(api, TAG, COMMIT, packages)
    publish(api, TAG, COMMIT, packages)
    assert api.uploads == list(ASSETS)
    assert all(item['name'] in item['label'] for item in api.files)
    assert pending_tag(api) == ""


def test_partial_upload_retry_publishes_only_missing_platform(packages):
    api = FakeGitHub([asset(ASSETS[0])])
    assert pending_tag(api) == TAG
    publish(api, TAG, COMMIT, packages)
    assert api.uploads == [ASSETS[1]]


@pytest.mark.parametrize("changes", [{"label": None}, {"label": "git:" + "b" * 40}, {"state": "starter"}])
def test_conflicting_existing_asset_is_never_overwritten(packages, changes):
    api = FakeGitHub([asset(ASSETS[1], **changes)])
    with pytest.raises(ReleaseError, match="Existing asset"):
        publish(api, TAG, COMMIT, packages)
    assert api.uploads == []


def test_moved_tag_cannot_receive_build_from_another_commit(packages):
    api = FakeGitHub()
    api.sha = "b" * 40
    with pytest.raises(ReleaseError, match="tag moved"):
        publish(api, TAG, COMMIT, packages)
    assert api.uploads == []


def test_tag_moving_between_uploads_stops_publication(packages):
    api = FakeGitHub()
    original = api.request

    def moving_request(*args, **kwargs):
        result = original(*args, **kwargs)
        api.sha = "b" * 40
        return result

    api.request = moving_request
    with pytest.raises(ReleaseError, match="tag moved"):
        publish(api, TAG, COMMIT, packages)
    assert api.uploads == [ASSETS[0]]


def test_missing_second_zip_does_not_partially_publish(packages):
    (packages / ASSETS[1]).unlink()
    api = FakeGitHub()
    with pytest.raises(ReleaseError, match="Missing or invalid"):
        publish(api, TAG, COMMIT, packages)
    assert api.uploads == []


def test_drafts_are_not_selected():
    api = FakeGitHub()
    api.releases = [release(draft=True), release(published_at=None)]
    assert pending_tag(api) == ""


def test_upload_url_from_another_host_is_rejected(packages):
    api = FakeGitHub()
    api.releases = [release(upload_url="https://example.com/collect")]
    with pytest.raises(ReleaseError, match="upload URL"):
        publish(api, TAG, COMMIT, packages)
    assert not api.uploads


def test_annotated_tags_are_resolved_to_commit():
    api = GitHub("test-secret")
    paths = []

    def request(path):
        paths.append(path)
        if path.startswith("/git/ref/"):
            return {"object": {"type": "tag", "sha": "b" * 40}}
        return {"object": {"type": "commit", "sha": COMMIT}}

    api.request = request
    assert api.commit("release/test") == COMMIT
    assert paths == ["/git/ref/tags/release%2Ftest", "/git/tags/" + "b" * 40]


def test_api_error_does_not_expose_credentials_or_response_body():
    secret = "test-secret-do-not-log"
    api = GitHub(secret)

    def failing_open(*args, **kwargs):
        raise HTTPError("https://api.github.com", 403, secret, {}, io.BytesIO(secret.encode()))

    api.opener.open = failing_open
    with pytest.raises(ReleaseError) as caught:
        api.request("/releases")
    assert "HTTP 403" in str(caught.value)
    assert secret not in str(caught.value)


@pytest.mark.parametrize("url", ["https://evil.example/repos/" + REPOSITORY + "/releases",
                                    "https://api.github.com@evil.example/repos/" + REPOSITORY + "/releases",
                                    "http://api.github.com/repos/" + REPOSITORY + "/releases"])
def test_api_never_sends_token_to_unexpected_origin(url):
    api = GitHub("test-secret")
    with pytest.raises(ReleaseError, match="Unexpected"):
        api.request(url)


def test_published_release_is_required_for_resolve():
    api = GitHub("test-secret")
    api.request = lambda path: release(draft=True)
    with pytest.raises(ReleaseError, match="must be published"):
        api.release(TAG)
