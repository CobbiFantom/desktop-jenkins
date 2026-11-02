"""Qt widgets stay on the main thread; I/O runs in a worker thread."""
import sys
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from pdf_uk.documents import Cancelled, DocumentError, NoTextError, translate_pdf
from pdf_uk.translation import GoogleTranslateClient, MyMemoryTranslateClient, TranslationError


class TranslationWorker(QThread):
    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    warning = pyqtSignal(str)
    no_text = pyqtSignal(str)

    def __init__(self, source: Path, destination: Path, source_language: str = "auto", provider: str = "google"):
        super().__init__()
        self.source, self.destination, self.source_language = source, destination, source_language
        self.cancel = Event()
        self.provider = provider

    def run(self) -> None:
        try:
            if self.provider == "mymemory":
                client = MyMemoryTranslateClient(self.source_language)
            elif self.provider == "google":
                client = GoogleTranslateClient(self.source_language)
            else:
                raise TranslationError("Невідомий перекладач.")
            skipped = translate_pdf(self.source, self.destination, client,
                                    self.cancel, self.progress.emit)
        except Cancelled:
            self.cancelled.emit()
        except NoTextError as exc:
            self.no_text.emit(str(exc))
        except (DocumentError, TranslationError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Не вдалося обробити документ. Спробуйте інший PDF.")
        else:
            if skipped:
                self.warning.emit(
                    "Без тексту, переклад пропущено: сторінки " + ", ".join(map(str, skipped))
                    + ". У PDF вони позначені поясненням; для сканів потрібен OCR."
                )
            self.succeeded.emit(str(self.destination))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.result = None
        self.setWindowTitle("PDF Ukrainian")
        self.resize(740, 640)
        self.setMinimumWidth(640)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        brand = QLabel("PDF / UKRAINIAN")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        heading = QLabel("Ваш PDF — українською")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        subtitle = QLabel("Оберіть документ, перекладіть текст і збережіть новий PDF.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setVerticalSpacing(16)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.source = QLineEdit()
        self.source.setPlaceholderText("Оберіть текстовий PDF")
        self.source.setReadOnly(True)
        self.browse = QPushButton("Обрати PDF…")
        self.browse.clicked.connect(self.choose_source)
        file_row = QHBoxLayout()
        file_row.addWidget(self.source, 1)
        file_row.addWidget(self.browse)
        form.addRow("Документ", file_row)

        self.language = QComboBox()
        for label, code in [("Визначити автоматично", "auto"), ("Англійська", "en"), ("Російська", "ru")]:
            self.language.addItem(label, code)
        form.addRow("Мова оригіналу", self.language)
        form.addRow("Мова перекладу", QLabel("Українська"))
        self.provider = QComboBox()
        self.provider.addItem("MyMemory — короткі документи, без ключа", "mymemory")
        self.provider.addItem("Google Translate", "google")
        self.provider.currentIndexChanged.connect(self.update_provider)
        form.addRow("Перекладач", self.provider)
        layout.addWidget(card)

        self.note = QLabel()
        self.note.setObjectName("note")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.update_provider()
        layout.addStretch()
        self.status = QLabel("Оберіть PDF, щоб почати")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #8a5700; background: #fff4d9; padding: 10px; border-radius: 6px;")
        self.warning.hide()
        layout.addWidget(self.warning)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.open_result = QPushButton("Відкрити результат")
        self.open_result.setEnabled(False)
        self.open_result.clicked.connect(self.show_result)
        actions.addWidget(self.open_result)
        actions.addStretch()
        self.cancel_button = QPushButton("Скасувати")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_translation)
        actions.addWidget(self.cancel_button)
        self.start_button = QPushButton("Перекласти та зберегти")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_translation)
        actions.addWidget(self.start_button)
        layout.addLayout(actions)
        self.setStyleSheet("""
            QWidget { background: #f4f6fa; color: #172033; font-size: 13px; }
            QLabel#brand { color: #2559cc; font-size: 12px; font-weight: 700; }
            QLabel#heading { font-size: 30px; font-weight: 700; }
            QFrame#card { background: white; border: 1px solid #dce2ed; border-radius: 12px; }
            QFrame#card QLabel { background: white; }
            QLineEdit, QComboBox { background: white; border: 1px solid #cbd4e3;
                border-radius: 6px; padding: 9px; min-height: 18px; }
            QPushButton { background: white; border: 1px solid #cbd4e3;
                border-radius: 7px; padding: 10px 13px; }
            QPushButton:hover { background: #eaf0fd; }
            QPushButton#primary { background: #2559cc; color: white; border: none; }
            QPushButton:disabled { background: #e7ebf2; color: #8b96a8; border: none; }
            QLabel#note { color: #607087; font-size: 12px; line-height: 1.5; }
            QProgressBar { border: none; background: #e0e6f0; border-radius: 5px;
                text-align: center; min-height: 16px; }
            QProgressBar::chunk { background: #2c67df; border-radius: 5px; }
        """)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Оберіть PDF", "", "PDF (*.pdf)")
        if path:
            self.source.setText(path)
            self.start_button.setEnabled(True)
            self.status.setText("Документ обрано. Можна починати переклад.")
            self.progress.setValue(0)
            self.result = None
            self.open_result.setEnabled(False)
            self.show_warning("")

    def start_translation(self):
        source = Path(self.source.text())
        filename, _ = QFileDialog.getSaveFileName(
            self, "Зберегти переклад", str(source.with_name(source.stem + "_uk.pdf")), "PDF (*.pdf)"
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_name(destination.name + ".pdf")
            if destination.exists():
                answer = QMessageBox.question(self, "Замінити файл?", f"Файл {destination.name} існує. Замінити?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
        if source.resolve() == destination.resolve():
            self.show_error("Оберіть інше ім'я, щоб зберегти оригінал.")
            return
        self.result = None
        self.show_warning("")
        self.progress.setValue(0)
        self.set_busy(True)
        self.worker = TranslationWorker(source, destination, self.language.currentData(), self.provider.currentData())
        self.worker.progress.connect(self.update_progress)
        self.worker.succeeded.connect(self.translation_succeeded)
        self.worker.failed.connect(self.show_error)
        self.worker.cancelled.connect(self.translation_cancelled)
        self.worker.warning.connect(self.show_warning)
        self.worker.no_text.connect(self.show_no_text)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def set_busy(self, busy):
        for widget in (self.browse, self.language, self.provider):
            widget.setEnabled(not busy)
        self.start_button.setEnabled(not busy and bool(self.source.text()))
        self.cancel_button.setEnabled(busy)
        self.open_result.setEnabled(not busy and self.result is not None)

    def update_progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def update_provider(self):
        previous_language = self.language.currentData()
        self.language.clear()
        if self.provider.currentData() == "google":
            self.language.addItem("Визначити автоматично", "auto")
            description = "Текст надсилається до Google Translate. Google може відхиляти запити (HTTP 429)."
        else:
            description = (
                "Текст надсилається до MyMemory. Безкоштовний ліміт: 5000 символів на день.\n"
                "Підходить для коротких тестових PDF. Мову оригіналу потрібно обрати вручну."
            )
        self.language.addItem("Англійська", "en")
        self.language.addItem("Російська", "ru")
        index = self.language.findData(previous_language)
        self.language.setCurrentIndex(max(index, 0))
        self.note.setText(
            description + "\nПотрібен інтернет. Сторінки без тексту пропускаються. OCR та оригінальна верстка не підтримуються."
        )

    def translation_succeeded(self, destination):
        self.result = Path(destination)
        self.status.setText(f"Готово! Збережено: {destination}")

    def show_error(self, message):
        self.status.setText(message)
        QMessageBox.warning(self, "Не вдалося перекласти", message)

    def show_warning(self, message):
        self.warning.setText(message)
        self.warning.setVisible(bool(message))

    def show_no_text(self, message):
        self.status.setText("У документі немає тексту для перекладу. Для сканів потрібен OCR.")
        self.progress.setValue(0)
        QMessageBox.information(self, "Потрібен текстовий PDF", message)

    def cancel_translation(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Скасування… Очікуємо завершення поточного запиту до перекладача.")

    def translation_cancelled(self):
        self.status.setText("Переклад скасовано. Вихідний файл не змінено.")
        self.progress.setValue(0)

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def show_result(self):
        if self.result and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result))):
            QMessageBox.information(self, "Результат", f"Відкрийте файл вручну:\n{self.result}")

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.cancel_translation()
            event.ignore()
            return
        event.accept()


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("PDF Ukrainian")
    window = MainWindow()
    if "--smoke-test" in sys.argv:
        from tempfile import TemporaryDirectory
        from pdf_uk.documents import extract_pages, write_pdf

        window.show()
        application.processEvents()
        GoogleTranslateClient()
        MyMemoryTranslateClient()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "smoke.pdf"
            write_pdf(["Україна: ґ, є, і, ї."], path, Event())
            text = " ".join(extract_pages(path, Event())[0].split())
            if "Україна: ґ, є, і, ї." not in text:
                return 1
        window.close()
        return 0
    window.show()
    return application.exec()
