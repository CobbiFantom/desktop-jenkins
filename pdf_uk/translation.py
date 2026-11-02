"""Translation providers through deep-translator; independent of the UI."""
import html

from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import BaseError, RequestError, TooManyRequests
from requests.exceptions import RequestException, Timeout


class TranslationError(Exception):
    """An actionable error safe to display in the UI."""


class GoogleTranslateClient:
    def __init__(self, source_language: str = "auto"):
        try:
            self.translator = GoogleTranslator(source=source_language, target="uk")
        except BaseError as exc:
            raise TranslationError("Непідтримувана мова оригіналу.") from exc

    def translate(self, text: str) -> str:
        try:
            translated = self.translator.translate(text)
        except TooManyRequests as exc:
            raise TranslationError(
                "Google обмежив запити (HTTP 429). Оберіть MyMemory у полі «Перекладач» "
                "для короткого документа або спробуйте Google пізніше."
            ) from exc
        except Timeout as exc:
            raise TranslationError("Google не відповів вчасно. Спробуйте ще раз.") from exc
        except (RequestException, RequestError) as exc:
            raise TranslationError("Не вдалося підключитися до Google Translate. Перевірте інтернет.") from exc
        except BaseError as exc:
            raise TranslationError("Google не повернув переклад. Спробуйте пізніше або оновіть deep-translator.") from exc
        if not isinstance(translated, str) or not translated.strip():
            raise TranslationError("Google не повернув переклад тексту.")
        return translated


class MyMemoryTranslateClient:
    max_chunk_bytes = 500
    max_document_chars = 5000

    def __init__(self, source_language: str = "en"):
        languages = {"en": "english", "ru": "russian"}
        if source_language not in languages:
            raise TranslationError("Для MyMemory оберіть англійську або російську мову оригіналу.")
        self.translator = MyMemoryTranslator(source=languages[source_language], target="ukrainian")
        # deep-translator 1.11.4 defaults to plain HTTP. Keep document text on HTTPS.
        self.translator._base_url = "https://api.mymemory.translated.net/get"

    def translate(self, text: str) -> str:
        if not text.strip():
            return text
        if len(text.encode("utf-8")) > self.max_chunk_bytes:
            raise TranslationError("Фрагмент для MyMemory перевищує 500 байтів.")
        try:
            translated = self.translator.translate(text)
        except TooManyRequests as exc:
            raise TranslationError("MyMemory обмежив запити. Спробуйте пізніше.") from exc
        except (RequestException, RequestError) as exc:
            raise TranslationError("Не вдалося підключитися до MyMemory. Перевірте інтернет.") from exc
        except (BaseError, ValueError, AttributeError, TypeError, StopIteration) as exc:
            raise TranslationError("MyMemory не повернув коректний переклад. Спробуйте пізніше.") from exc
        if not isinstance(translated, str) or not translated.strip():
            raise TranslationError("MyMemory не повернув переклад тексту.")
        # The API can return quota/validation errors as translatedText with HTTP 200.
        status = translated.upper()
        if "MYMEMORY WARNING" in status or "YOU USED ALL AVAILABLE FREE TRANSLATIONS" in status:
            raise TranslationError("Вичерпано безкоштовний ліміт MyMemory: 5000 символів на день. Спробуйте завтра.")
        if status.startswith(("INVALID LANGUAGE", "QUERY LENGTH LIMIT EXCEEDED", "PLEASE SELECT TWO DISTINCT")):
            raise TranslationError("MyMemory відхилив текст або мовну пару.")
        return html.unescape(translated)


def split_text(text: str, limit: int = 1800, max_bytes: int | None = None) -> list[str]:
    """Keep every character; prefer paragraph/sentence/word boundaries."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if max_bytes is not None and max_bytes < 4:
        raise ValueError("max_bytes must allow at least one UTF-8 character")
    chunks = []
    while text:
        boundary = min(len(text), limit)
        if max_bytes is not None:
            boundary = len(text[:boundary].encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore"))
        cut = boundary
        if boundary < len(text):
            for delimiter in ("\n\n", ". ", "\n", " "):
                index = text.rfind(delimiter, 0, boundary)
                if index >= boundary // 2:
                    cut = index + len(delimiter)
                    break
        chunks.append(text[:cut])
        text = text[cut:]
    return chunks
