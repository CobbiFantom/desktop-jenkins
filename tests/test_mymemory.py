from threading import Event

import pytest

from pdf_uk.documents import DocumentError, translate_pdf, write_pdf
from pdf_uk.translation import MyMemoryTranslateClient, TranslationError, split_text


@pytest.mark.parametrize("text", ["Їжак ґрунт єдність " * 300, "Text " * 400, "🙂" * 401])
def test_chunks_respect_utf8_byte_limit_without_losing_text(text):
    chunks = split_text(text, max_bytes=500)
    assert "".join(chunks) == text
    assert all(0 < len(chunk.encode("utf-8")) <= 500 for chunk in chunks)


def test_mymemory_uses_https_and_ukrainian(monkeypatch):
    class Response:
        status_code = 200
        def json(self):
            return {"responseData": {"translatedText": "Привіт, світе!"}, "matches": []}
        def close(self):
            pass
    def get(url, params, proxies):
        assert url == "https://api.mymemory.translated.net/get"
        assert params["langpair"] == "en-GB|uk-UA"
        assert params["q"] == "Hello world!"
        return Response()
    monkeypatch.setattr("deep_translator.mymemory.requests.get", get)
    assert MyMemoryTranslateClient().translate("Hello world!") == "Привіт, світе!"


def test_mymemory_requires_explicit_source_language():
    with pytest.raises(TranslationError, match="оберіть"):
        MyMemoryTranslateClient("auto")


def test_quota_warning_is_not_saved_as_translation(monkeypatch):
    monkeypatch.setattr(
        "pdf_uk.translation.MyMemoryTranslator.translate",
        lambda *args: "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY",
    )
    with pytest.raises(TranslationError, match="ліміт"):
        MyMemoryTranslateClient().translate("Hello")


def test_document_limit_is_checked_before_network_and_existing_result_is_kept(tmp_path, monkeypatch):
    def unexpected_network(*args):
        raise AssertionError("No request should be made for an oversized document")
    monkeypatch.setattr("pdf_uk.translation.MyMemoryTranslator.translate", unexpected_network)
    source, destination = tmp_path / "long.pdf", tmp_path / "out.pdf"
    write_pdf(["Long text. " * 600], source, Event())
    destination.write_bytes(b"existing result")
    with pytest.raises(DocumentError, match="5000"):
        translate_pdf(source, destination, MyMemoryTranslateClient(), Event(), lambda *_: None)
    assert destination.read_bytes() == b"existing result"
