import hashlib
import io
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import zipfile

import pytest

from scripts.github_release import ASSETS, GitHub, REPOSITORY, ReleaseError, asset_label, publish


COMMIT = "a" * 40
TAG = "v0.3.0"


def release(**changes):
    return {"id": 123, "tag_name": TAG, "draft": True, "published_at": None,
            "upload_url": f"https://uploads.github.com/repos/{REPOSITORY}/releases/123/assets{{?name,label}}",
            **changes}


class FakeGitHub:
    def __init__(self, assets=(), target=None):
        self.files = list(assets)
        self.uploads = []
        self.sha = COMMIT
        self.target = target
        self.events = []

    def release(self, tag):
        assert tag == TAG
        return self.target

    def create_release(self, tag, commit):
        assert tag == TAG and commit == COMMIT
        self.target = release()
        self.events.append("draft")
        return self.target

    def publish_release(self, target):
        assert {a['name'] for a in self.files} == set(ASSETS)
        target.update(draft=False, published_at="2026-11-02T12:00:00Z")
        self.events.append("publish")

    def commit(self, tag):
        return self.sha

    def assets(self, target):
        return iter(self.files)

    def request(self, url, *, upload):
        query = parse_qs(urlsplit(url).query)
        data = upload.read()
        assert zipfile.is_zipfile(io.BytesIO(data))
        item = {"name": query["name"][0], "label": query["label"][0], "state": "uploaded",
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data)}
        self.uploads.append(item["name"])
        self.events.append(item["name"])
        self.files.append(item)
        return item


@pytest.fixture
def packages(tmp_path):
    for name in ASSETS:
        with zipfile.ZipFile(tmp_path / name, "w") as archive:
            archive.writestr("app/test.txt", "test")
    return tmp_path


def asset(name, **changes):
    return {"name": name, "label": asset_label(name, COMMIT), "state": "uploaded", **changes}


def test_all_three_zips_verified_before_draft_is_published(packages):
    api = FakeGitHub()
    publish(api, TAG, COMMIT, packages)
    assert api.events == ["draft", *ASSETS, "publish"]
    assert api.target['draft'] is False
    publish(api, TAG, COMMIT, packages)
    assert api.uploads == list(ASSETS)
    assert api.events.count('publish') == 1


def test_partial_draft_retry_uploads_only_missing_files(packages):
    api = FakeGitHub([asset(ASSETS[0])], target=release())
    publish(api, TAG, COMMIT, packages)
    assert api.uploads == list(ASSETS[1:])
    assert api.events[-1] == 'publish'


@pytest.mark.parametrize("changes", [{"label": None}, {"label": "git:" + "b" * 40}, {"state": "starter"}])
def test_conflicts_never_overwrite_existing_assets_or_partially_upload(packages, changes):
    api = FakeGitHub([asset(ASSETS[-1], **changes)], target=release())
    with pytest.raises(ReleaseError, match="Existing asset"):
        publish(api, TAG, COMMIT, packages)
    assert api.events == []


def test_moved_tag_cannot_receive_build_from_another_commit(packages):
    api = FakeGitHub()
    api.sha = "b" * 40
    with pytest.raises(ReleaseError, match="tag moved"):
        publish(api, TAG, COMMIT, packages)
    assert api.events == []


def test_tag_moving_between_uploads_keeps_release_draft(packages):
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
    assert api.target['draft'] is True


def test_corrupt_upload_cannot_publish_release(packages):
    api = FakeGitHub()
    original = api.request

    def corrupt_request(*args, **kwargs):
        result = original(*args, **kwargs)
        result['digest'] = 'sha256:incorrect'
        return result

    api.request = corrupt_request
    with pytest.raises(ReleaseError, match="ZIP integrity"):
        publish(api, TAG, COMMIT, packages)
    assert api.target['draft'] is True
    assert 'publish' not in api.events


def test_missing_windows_zip_cannot_create_release(packages):
    (packages / ASSETS[-1]).unlink()
    api = FakeGitHub()
    with pytest.raises(ReleaseError, match="exactly"):
        publish(api, TAG, COMMIT, packages)
    assert api.events == []


def test_unexpected_upload_host_is_rejected(packages):
    api = FakeGitHub(target=release(upload_url="https://example.com/collect"))
    with pytest.raises(ReleaseError, match="upload URL"):
        publish(api, TAG, COMMIT, packages)
    assert api.events == []


def test_annotated_tags_resolve_to_commit():
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


def test_retry_finds_existing_draft_even_when_tag_endpoint_omits_it():
    api = GitHub("test-secret")

    def request(path):
        if '/tags/' in path:
            raise ReleaseError('not found', 404)
        return [release()]

    api.request = request
    assert api.release(TAG)['draft'] is True


def test_api_error_does_not_expose_token_or_response_body():
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
    with pytest.raises(ReleaseError, match="Unexpected"):
        GitHub("test-secret").request(url)
