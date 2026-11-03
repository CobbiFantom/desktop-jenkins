# PDF Ukrainian

PDF Ukrainian — настільний застосунок для перекладу текстових PDF українською мовою. Проєкт створено як практичний приклад розробки на Python і PyQt6 та збирання застосунку для macOS, Windows і Linux.

## Як це працює

Застосунок дістає текст зі сторінок PDF, надсилає його обраному сервісу перекладу (MyMemory або Google Translate) і зберігає переклад в окремий PDF. Для роботи потрібне підключення до інтернету. Оригінальний файл не змінюється.

Підтримуються PDF із текстом, який можна виділити. Розпізнавання сканів (OCR) не реалізоване, а початкове оформлення, зображення й таблиці не переносяться у результат.

## Збирання застосунку

Спочатку збірки виконувалися в Jenkins на підключених агентах macOS і Linux. Зараз CI/CD працює через GitHub Actions: push у `main` запускає тести, а push нового тега `v*` — тести й окреме збирання для macOS, Windows і Linux. Після успішної збірки ZIP-файли автоматично додаються до GitHub Release.

## Встановлення

**Готові збірки:** завантажте архів для своєї системи, розпакуйте його та запустіть застосунок. Python встановлювати не потрібно.

- [macOS (Apple Silicon)](https://github.com/CobbiFantom/desktop-jenkins/releases/latest/download/PDFUkrainian-Darwin-arm64.zip)
- [Windows (64-bit)](https://github.com/CobbiFantom/desktop-jenkins/releases/latest/download/PDFUkrainian-Windows-x86_64.zip)
- [Linux (x86_64)](https://github.com/CobbiFantom/desktop-jenkins/releases/latest/download/PDFUkrainian-Linux-x86_64.zip)

**Запуск із коду:** потрібні Python 3.10–3.13 та інтернет для перекладу.

```bash
git clone https://github.com/CobbiFantom/desktop-jenkins.git
cd desktop-jenkins
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

У Windows PowerShell активуйте середовище командою `.venv\Scripts\Activate.ps1`, а потім виконайте команди встановлення залежностей і запуску.
