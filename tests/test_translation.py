import pytest
from deep_translator.exceptions import RequestError, TooManyRequests, TranslationNotFound
from requests.exceptions import ConnectionError, Timeout

from pdf_uk.translation import GoogleTranslateClient, TranslationError, split_text


@pytest.mark.parametrize("text", ["", "Hello world. " * 500, "Їжак ґрунт єдність " * 300, "x" * 10001])
def test_chunks_preserve_all_text_and_obey_limit(text):
    chunks = split_text(text, 100)
    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= 100 for chunk in chunks)


def test_unsupported_language_has_clear_error():
    with pytest.raises(TranslationError, match="мова"):
        GoogleTranslateClient("not-a-language")


@pytest.mark.parametrize("source", ["en", "ru", "auto"])
def test_google_request_targets_ukrainian_and_parses_response(monkeypatch, source):
    class Response:
        status_code = 200
        text = '<html><div class="t0">Привіт, світе! Їжак &amp; ґрунт.</div></html>'
        def close(self):
            pass

    def get(url, params, proxies):
        assert url.startswith("https://translate.google.com/")
        assert params["sl"] == source
        assert params["tl"] == "uk"
        assert params["q"] == "Hello world!"
        return Response()

    monkeypatch.setattr("deep_translator.google.requests.get", get)
    assert GoogleTranslateClient(source).translate("Hello world!") == "Привіт, світе! Їжак & ґрунт."


@pytest.mark.parametrize("result", [None, "", "   ", [], {}])
def test_empty_or_invalid_translation_is_rejected(monkeypatch, result):
    monkeypatch.setattr("pdf_uk.translation.GoogleTranslator.translate", lambda *a, **k: result)
    with pytest.raises(TranslationError, match="не повернув переклад"):
        GoogleTranslateClient().translate("Hello")


@pytest.mark.parametrize("error, message", [
    (TooManyRequests(), "обмежив"),
    (ConnectionError("connection refused"), "інтернет"),
    (Timeout(), "вчасно"),
    (RequestError(), "інтернет"),
    (TranslationNotFound("private document text"), "не повернув переклад"),
])
def test_network_and_parser_errors_are_actionable(monkeypatch, error, message):
    def fail(*a, **k):
        raise error
    monkeypatch.setattr("pdf_uk.translation.GoogleTranslator.translate", fail)
    with pytest.raises(TranslationError, match=message) as caught:
        GoogleTranslateClient().translate("private document text")
    assert "private document text" not in str(caught.value)


@pytest.mark.parametrize("status, html, message", [
    (429, "", "обмежив"),
    (500, "", "інтернет"),
    (200, "<html>Unexpected Google page</html>", "не повернув переклад"),
])
def test_real_library_handles_google_error_responses(monkeypatch, status, html, message):
    class Response:
        status_code = status
        text = html
        def close(self):
            pass
    monkeypatch.setattr("deep_translator.google.requests.get", lambda *a, **k: Response())
    with pytest.raises(TranslationError, match=message):
        GoogleTranslateClient().translate("Hello")
