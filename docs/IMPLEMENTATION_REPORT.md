# Итог разработки — 8 октября 2026

Создана локальная предварительная версия AutoCAD Engineering MCP 0.2.0, только
для 2D-чертежей. Пользователь сам публикует проект в GitHub. ZIP не создавался,
проект и DWG никуда не загружались, конфигурация личного Codex не изменялась.

## Расположение и файлы

Рабочие исходники находятся в корне этого Git-репозитория.
Текущие изменения для работы с трубопроводами внесены непосредственно в проект.
Подробности расширения: [PIPELINES_REPORT.md](PIPELINES_REPORT.md).

[Полное дерево файлов](PROJECT_TREE.md), [README RU](../README.md),
[README EN](../README_EN.md), [каталог инструментов](TOOLS.md).

```text
pyproject.toml, README.md, README_EN.md, LICENSE, CHANGELOG.md, CONTRIBUTING.md
.gitignore, .env.example, .github/workflows/ci.yml
src/autocad_engineering_mcp/
  server.py, config.py, __init__.py, __main__.py
  core/        models, geometry, safety, service, exceptions
  adapters/    base, mock, autocad_com, com_geometry, com_pipelines, mock_pipelines
  tools/       registration, cad, engineering, pipelines
  engineering/ models, service
  pipelines/   models, colors, geometry, common, service, analysis
  resources/   profile.example.json
scripts/       install.ps1, uninstall.ps1, check_environment.py, generate_tool_catalog.py
examples/      HVAC, plumbing, shared runner, codex_prompts.md
tests/         mock/schema/safety/STA-contract tests; opt-in COM integration
docs/          sources, tools, Windows checklist, tree, implementation report
```

## Реализованные инструменты

99 инструментов зарегистрированы в сервере; их названия и описания собраны из
фактической регистрации в [TOOLS.md](TOOLS.md). Есть подключение и документы,
вся запрошенная базовая 2D-геометрия, слои, блоки/атрибуты, трансформации, размеры,
пагинация и фильтры, пакетное создание, сценарии ОВ/ВК и спецификации.
Добавлены 14 инструментов для красных/синих кандидатов в трубы в существующих DWG.
Схемы исходных 85 инструментов сохранены; новые расстояния — в единицах чертежа.

Сохранение DWG реализовано через COM SaveAs. Mock DWG не создаёт.
Библиотека встроенных блоков использует простые оригинальные символы, не нормативные УГО.
Оси воздуховодов и труб — схематичные полилинии. Объёмных объектов нет.

## Реально выполненные проверки

Среда: macOS, Python 3.11.15, MCP SDK 2.3.0, Pydantic 2.13.5.

| Проверка | Фактический результат |
| --- | --- |
| pytest | **103 passed, 1 skipped**; пропущен реальный COM-тест |
| Ruff lint | All checks passed |
| Ruff format | Проверка форматирования проходит |
| Editable install | Пакет установлен локально через uv |
| Wheel + sdist | Оба пакета успешно собраны через python -m build |
| Wheel install | Wheel установлен с зависимостями в отдельное временное окружение |
| Console entry point | Установленная консольная команда отвечает SDK-клиенту по stdio |
| JSON Schema | 99 инструментов; схемы исходных 85 инструментов не изменены |
| Protocol calls | Connect/create document/draw line/create pipeline/move/query выполнены через stdio в mock |
| Examples | Оба сквозных примера ОВ/ВК выполнены в mock, спецификации получены |
| Environment check | Python/MCP/Pydantic определены; pywin32 отсутствует на Mac ожидаемо |

Проверены недопустимые координаты/ненулевой Z/единицы, параметры труб и воздуховодов,
изоляция документов, mock-геометрия всех примитивов, public tool wrappers,
copy/move/rotate/scale/mirror/delete, слои/атрибуты, hatch boundaries,
batch preflight/dry-run/rollback/partial reporting, ограничения объёма, подтверждения,
пути/symlink/backup, параметры профиля, схема сети и восстановление из metadata,
спецификации и плоская проекция ВК. STA-тест проверяет владение потоком на fake COM.
Дополнительные тесты трубопроводов проверяют геометрию, цвета, отбор, защиты,
вызовы всех новых wrappers и ошибки восстановления на Python-двойниках ActiveX.

## Команды для друга на Windows

В корне полученного репозитория:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipCodexRegistration
$McpPython = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$DwgRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AutoCAD Engineering MCP'
codex mcp add autocad-engineering --env 'ACAD_MCP_BACKEND=com' --env "ACAD_MCP_SAVE_ROOT=$DwgRoot" -- $McpPython -m autocad_engineering_mcp
codex mcp list
```

Альтернативная конфигурация `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.autocad-engineering]
command = 'C:\CAD\autocad-engineering-mcp\.venv\Scripts\python.exe'
args = ["-m", "autocad_engineering_mcp"]
startup_timeout_sec = 20
tool_timeout_sec = 120

[mcp_servers.autocad-engineering.env]
ACAD_MCP_BACKEND = "com"
ACAD_MCP_SAVE_ROOT = 'C:\CAD\Drawings'
```

Пути замените на свои. Запуск: `.\.venv\Scripts\python.exe -m autocad_engineering_mcp`
либо `.\.venv\Scripts\autocad-engineering-mcp.exe`.

Первые запросы: «Подключись и покажи версию, ничего не изменяй», «Создай новый
2D-документ в мм», «Нарисуй линию [0,0]–[5000,0]», «Создай схему П1 с четырьмя
решётками», «Сформируй спецификацию», «Сохрани новый test.dwg внутри разрешённой папки».
Подробно: [12 сценариев](../examples/codex_prompts.md).

## Непроверенные части и ограничения

На Windows ещё нужно проверить installer/uninstaller, pywin32, точный ProgID,
обнаружение сервера личным Codex, права/ROT/модальные окна, пути с пробелами и backslash.
На AutoCAD 2027 — все реальные ActiveX-вызовы, marshaling массивов, атрибуты,
штриховку/сплайн/размеры, пользовательские 2D-блоки, XData после SaveAs/перезапуска,
Undo Mark/компенсацию, оба инженерных примера, сохранение/открытие DWG и backup.
[Checklist Windows](WINDOWS_VERIFICATION.md) содержит безопасный порядок.

COM-откат best_effort, а не полная транзакция. Нет расчётов, BIM, PaperSpace,
нормативной проверки, автоматических фасонных частей или распознавания любой DWG-геометрии.
Ручное редактирование может рассинхронизировать XData; сеть связывается на явных вершинах.
Крупные запросы ограничены и требуют пагинации. Mock-offset не симулируется.

Это подготовленный к дальнейшей проверке исходный проект; production release и
успешная работа на AutoCAD 2027 пока не заявлены. GitHub Actions подготовлен, но
проверка на GitHub ещё не выполнялась. Коммит/push остаются за владельцем.
