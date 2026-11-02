"""PDF text extraction and a new, readable PDF (original layout is not copied)."""
import html
import os
import tempfile
from pathlib import Path
from threading import Event
from typing import Callable, Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from PyQt6.QtCore import QMarginsF
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument

from pdf_uk.translation import split_text


class DocumentError(Exception):
    pass


class NoTextError(DocumentError):
    """The document needs OCR rather than text translation."""


class Cancelled(Exception):
    pass


class Translator(Protocol):
    def translate(self, text: str) -> str: ...


def check_cancelled(cancel: Event) -> None:
    if cancel.is_set():
        raise Cancelled()


def extract_pages(path: Path, cancel: Event) -> list[str]:
    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            if reader.is_encrypted:
                raise DocumentError("PDF захищений паролем. Спочатку збережіть незахищену копію.")
            pages = []
            for page in reader.pages:
                check_cancelled(cancel)
                text = (page.extract_text() or "").strip()
                pages.append(text)
            if not pages:
                raise DocumentError("PDF не містить сторінок.")
            if not any(pages):
                raise NoTextError(
                    "У цьому PDF немає тексту, який можна витягти. Можливо, це скан або порожній документ. "
                    "Для скана спочатку потрібне розпізнавання тексту (OCR). Файл результату не змінено."
                )
            return pages
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentError("Не вдалося прочитати PDF. Перевірте файл і права доступу.") from exc


def write_pdf(pages: list[str], destination: Path, cancel: Event) -> None:
    """Write alongside destination, then replace atomically only after success."""
    check_cancelled(cancel)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", dir=destination.parent, delete=False) as file:
            temporary = Path(file.name)
        writer = QPdfWriter(str(temporary))
        writer.setTitle("Переклад українською")
        writer.setCreator("PDF Ukrainian")
        writer.setResolution(96)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(20, 18, 20, 18), QPageLayout.Unit.Millimeter)
        document = QTextDocument()
        document.setDefaultFont(QFont("Arial", 11))
        sections = []
        for index, text in enumerate(pages, 1):
            check_cancelled(cancel)
            style = "page-break-before: always;" if index > 1 else ""
            paragraphs = "".join(
                "<p>" + html.escape(paragraph).replace("\n", "<br>") + "</p>"
                for paragraph in text.split("\n\n")
            )
            sections.append(
                f'<div style="{style}"><p style="color:#526177;font-size:9pt">'
                f"ПЕРЕКЛАД УКРАЇНСЬКОЮ · Сторінка оригіналу {index}</p>{paragraphs}</div>"
            )
        document.setHtml('<html><body style="color:#172033;">' + "".join(sections) + "</body></html>")
        document.print(writer)
        # QPdfWriter finalizes its file on destruction, including on Windows.
        del writer
        check_cancelled(cancel)
        if temporary.stat().st_size == 0:
            raise DocumentError("Не вдалося створити вихідний PDF.")
        os.replace(temporary, destination)
    except OSError as exc:
        raise DocumentError("Не вдалося зберегти PDF. Перевірте папку та права доступу.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def translate_pdf(source: Path, destination: Path, translator: Translator,
                  cancel: Event, progress: Callable[[int, str], None]) -> list[int]:
    if source.resolve() == destination.resolve():
        raise DocumentError("Оберіть інший шлях: вихідний PDF не можна перезаписати.")
    progress(0, "Читання PDF…")
    pages = extract_pages(source, cancel)
    document_limit = getattr(translator, "max_document_chars", None)
    if document_limit is not None and sum(map(len, pages)) > document_limit:
        raise DocumentError(
            f"Документ перевищує {document_limit} символів. MyMemory без ключа має денний ліміт "
            f"{document_limit} символів. Оберіть коротший PDF або Google Translate."
        )
    chunks_by_page = [split_text(page, max_bytes=getattr(translator, "max_chunk_bytes", None)) for page in pages]
    total = sum(map(len, chunks_by_page))
    completed = 0
    translated = []
    skipped_pages = []
    for number, chunks in enumerate(chunks_by_page, 1):
        check_cancelled(cancel)
        if not chunks:
            skipped_pages.append(number)
            translated.append(
                "Переклад цієї сторінки пропущено: текст не знайдено.\n\n"
                "Можливо, це порожня сторінка або скан. Для сканів потрібне розпізнавання тексту (OCR)."
            )
            continue
        parts = []
        for chunk in chunks:
            check_cancelled(cancel)
            parts.append(translator.translate(chunk))
            check_cancelled(cancel)
            completed += 1
            progress(int(completed / total * 95), f"Переклад сторінки {number} з {len(pages)}")
        translated.append("\n\n".join(parts))
    progress(97, "Збереження PDF…")
    write_pdf(translated, destination, cancel)
    progress(100, "Готово! Переклад збережено.")
    return skipped_pages
