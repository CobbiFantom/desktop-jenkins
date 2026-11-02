from threading import Event

import pytest
from pypdf import PdfReader, PdfWriter

from pdf_uk.documents import Cancelled, DocumentError, NoTextError, extract_pages, translate_pdf, write_pdf
from pdf_uk.translation import GoogleTranslateClient


def test_google_client_to_pdf_pipeline(tmp_path, monkeypatch):
    """Use the real deep-translator HTML parser with a fake Google response."""
    requests = []
    class Response:
        status_code = 200
        text = '<html><div class="t0">Привіт, світе! Україна: ґ, є, і, ї.</div></html>'
        def close(self):
            pass

    def get(url, params, proxies):
        requests.append(dict(params))
        return Response()

    monkeypatch.setattr("deep_translator.google.requests.get", get)
    source, destination = tmp_path / "source.pdf", tmp_path / "translated.pdf"
    write_pdf(["Hello world!", "Another page."], source, Event())
    updates = []
    translate_pdf(source, destination, GoogleTranslateClient(), Event(), lambda value, _: updates.append(value))
    result = PdfReader(destination)
    assert len(result.pages) == 2
    assert "Україна: ґ, є, і, ї." in " ".join(result.pages[0].extract_text().split())
    assert len(requests) == 2
    assert all(item["tl"] == "uk" for item in requests)
    assert updates[-1] == 100
    assert updates == sorted(updates)


def test_cancellation_does_not_replace_existing_result(tmp_path):
    source, destination = tmp_path / "in.pdf", tmp_path / "out.pdf"
    write_pdf(["Hello"], source, Event())
    destination.write_bytes(b"existing result")
    cancel = Event()
    class CancellingTranslator:
        def translate(self, text):
            cancel.set()
            return "Переклад"
    with pytest.raises(Cancelled):
        translate_pdf(source, destination, CancellingTranslator(), cancel, lambda *_: None)
    assert destination.read_bytes() == b"existing result"


def test_source_cannot_be_overwritten(tmp_path):
    source = tmp_path / "in.pdf"
    write_pdf(["Hello"], source, Event())
    before = source.read_bytes()
    with pytest.raises(DocumentError, match="перезаписати"):
        translate_pdf(source, source, None, Event(), lambda *_: None)
    assert source.read_bytes() == before


@pytest.mark.parametrize("encrypted", [False, True])
def test_blank_and_encrypted_pdf_are_rejected(tmp_path, encrypted):
    source = tmp_path / "in.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("secret")
    writer.write(source)
    with pytest.raises(DocumentError, match="паролем" if encrypted else "OCR"):
        extract_pages(source, Event())


def test_failed_save_keeps_existing_result_and_cleans_temporary_file(tmp_path, monkeypatch):
    destination = tmp_path / "out.pdf"
    destination.write_bytes(b"existing result")
    def fail(*args):
        raise PermissionError("Cannot replace")
    monkeypatch.setattr("pdf_uk.documents.os.replace", fail)
    with pytest.raises(DocumentError):
        write_pdf(["Новий переклад"], destination, Event())
    assert destination.read_bytes() == b"existing result"
    assert list(tmp_path.iterdir()) == [destination]


def test_long_text_flows_to_extra_pages(tmp_path):
    destination = tmp_path / "long.pdf"
    sentences = [f"Речення{index:04d}: Це довгий український текст." for index in range(1800)]
    write_pdf([" ".join(sentences)], destination, Event())
    reader = PdfReader(destination)
    assert len(reader.pages) > 1
    text = "".join("".join(page.extract_text().split()) for page in reader.pages)
    # PDF extraction may include clipped boundary lines twice. Every unique
    # sentence must still be present across the generated pages.
    assert all(f"Речення{index:04d}" in text for index in range(1800))


@pytest.mark.parametrize("blank_number", [1, 2, 3])
def test_empty_pages_are_skipped_without_losing_source_page_numbers(tmp_path, blank_number):
    text_source = tmp_path / "text.pdf"
    source, destination = tmp_path / "mixed.pdf", tmp_path / "result.pdf"
    write_pdf(["First readable page", "Second readable page"], text_source, Event())
    reader, writer = PdfReader(text_source), PdfWriter()
    text_index = 0
    for number in range(1, 4):
        if number == blank_number:
            writer.add_blank_page(width=595, height=842)
        else:
            writer.add_page(reader.pages[text_index])
            text_index += 1
    writer.write(source)
    pages = extract_pages(source, Event())
    assert len(pages) == 3
    assert pages[blank_number - 1] == ""

    class RecordingTranslator:
        def __init__(self):
            self.calls = []
        def translate(self, text):
            self.calls.append(text)
            return "Переклад українською"

    client = RecordingTranslator()
    updates = []
    skipped = translate_pdf(source, destination, client, Event(), lambda value, _: updates.append(value))
    assert skipped == [blank_number]
    assert len(client.calls) == 2
    assert all(text.strip() for text in client.calls)
    output = PdfReader(destination)
    assert len(output.pages) == 3
    for number, page in enumerate(output.pages, 1):
        text = " ".join(page.extract_text().split())
        assert f"Сторінка оригіналу {number}" in text
        assert ("текст не знайдено" in text) == (number == blank_number)
    assert updates[-1] == 100
    assert updates == sorted(updates)


def test_all_empty_pages_need_ocr_without_requests_or_replacing_result(tmp_path):
    source, destination = tmp_path / "scan.pdf", tmp_path / "result.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    writer.write(source)
    destination.write_bytes(b"existing result")
    class NoNetworkTranslator:
        def translate(self, text):
            raise AssertionError("A document without text must not call the translator")
    with pytest.raises(NoTextError, match="OCR"):
        translate_pdf(source, destination, NoNetworkTranslator(), Event(), lambda *_: None)
    assert destination.read_bytes() == b"existing result"
