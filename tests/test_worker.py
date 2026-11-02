from threading import Event
from time import monotonic

from pypdf import PdfReader, PdfWriter

from pdf_uk.app import MainWindow, TranslationWorker
from pdf_uk.documents import write_pdf


def test_provider_selection_has_no_silent_fallback(application):
    window = MainWindow()
    assert window.provider.currentData() == "mymemory"
    assert window.language.findData("auto") == -1
    assert "5000" in window.note.text()
    window.provider.setCurrentIndex(window.provider.findData("google"))
    assert window.language.findData("auto") >= 0
    assert "Google" in window.note.text()
    window.close()


def test_worker_reports_skipped_pages_as_warning_and_still_succeeds(tmp_path, monkeypatch):
    class FakeClient:
        def __init__(self, source_language):
            pass
        def translate(self, text):
            return "Переклад"
    monkeypatch.setattr("pdf_uk.app.GoogleTranslateClient", FakeClient)
    source, destination, text_pdf = tmp_path / "mixed.pdf", tmp_path / "out.pdf", tmp_path / "text.pdf"
    write_pdf(["Hello"], text_pdf, Event())
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_page(PdfReader(text_pdf).pages[0])
    writer.write(source)
    worker = TranslationWorker(source, destination)
    warnings, successes, errors = [], [], []
    worker.warning.connect(warnings.append)
    worker.succeeded.connect(successes.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert successes == [str(destination)]
    assert not errors
    assert len(warnings) == 1
    assert "сторінки 1" in warnings[0]


def test_worker_reports_all_empty_pdf_as_information(tmp_path):
    source, destination = tmp_path / "scan.pdf", tmp_path / "out.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(source)
    worker = TranslationWorker(source, destination)
    messages, successes, errors = [], [], []
    worker.no_text.connect(messages.append)
    worker.succeeded.connect(successes.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert len(messages) == 1
    assert "OCR" in messages[0]
    assert not successes and not errors
    assert not destination.exists()


def test_worker_emits_result_and_returns_without_blocking_ui(tmp_path, application, monkeypatch):
    class FakeClient:
        def __init__(self, source_language):
            pass
        def translate(self, text):
            return "Переклад українською"
    monkeypatch.setattr("pdf_uk.app.GoogleTranslateClient", FakeClient)
    source, destination = tmp_path / "source.pdf", tmp_path / "result.pdf"
    write_pdf(["Hello world"], source, Event())
    window = MainWindow()
    window.show()
    worker = TranslationWorker(source, destination)
    results, errors = [], []
    worker.succeeded.connect(results.append)
    worker.failed.connect(errors.append)
    worker.start()
    deadline = monotonic() + 10
    while worker.isRunning() and monotonic() < deadline:
        application.processEvents()
        worker.wait(10)
    assert worker.wait(1000)
    application.processEvents()
    assert not errors
    assert results == [str(destination)]
    assert destination.is_file()
    window.close()
