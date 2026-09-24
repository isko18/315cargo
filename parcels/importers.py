"""Разбор файла накладной: .xlsx / .xls / .csv → строки с треком, весом, кодом.

Здесь только чтение файла и распознавание раскладки. Ни БД, ни HTTP: эта часть
ломается на файлах поставщиков чаще всего, и чинить её надо отдельно от Django.

Почему разбор переехал на сервер: раньше накладную парсило мобильное
приложение, и каждый новый формат (объединённые ячейки, cp1251, числа текстом)
требовал релиза в сторах. Плюс веб-панель разбирала тот же формат своим кодом —
два парсера на один формат неизбежно расходятся.
"""

from __future__ import annotations

import codecs
import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import IO

# Шапку ищем не только в первой строке: сверху бывает название документа.
HEADER_SEARCH_DEPTH = 5

_TRACK_PREFIXES = ("трек", "track", "штрих", "barcode", "штрих-код")
_TRACK_CONTAINS = ("номер трека", "tracking")
_WEIGHT_PREFIXES = ("вес", "weight", "салмак", "салмагы", "салмагі")
_CODE_EXACT = ("код клиента", "client code", "клиент код", "код клієнта")
_CODE_CONTAINS = ("код", "client code")

_COLUMN_RE = re.compile(r"^[A-Z]{1,3}$")


class ImportFormatError(Exception):
    """Файл или ячейку не удалось разобрать.

    Текст уходит оператору склада как есть, поэтому он должен быть человеческим:
    никаких трассировок и KeyError.
    """


@dataclass
class Layout:
    """Что мы распознали в файле. Уходит клиенту полем ``detected``."""

    start_row: int
    track_column: str | None = None
    weight_column: str | None = None
    client_code_column: str | None = None


@dataclass
class ImportRow:
    row: int  # номер строки в файле, счёт с 1, вместе с шапкой
    track_number: str
    weight: str
    client_code: str


# --- кодировки и разделители ---


def decode_bytes(raw: bytes) -> str:
    """UTF-8 с BOM, UTF-8 и cp1251 — три кодировки, которые реально приходят.

    BOM обязательно срезать: иначе он приклеивается к первой ячейке, и
    трек-номер из неё не совпадает ни с чем в базе.
    """
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Выгрузки из 1С и старого Excel.
        return raw.decode("cp1251", errors="replace")


def _sniff_delimiter(text: str) -> str:
    """Разделитель — тот, при котором строки бьются на одинаковое число колонок.

    По частоте символов считать нельзя: в шапке «Трек;Вес, кг» запятых столько
    же, сколько точек с запятой, и файл развалился бы по запятой внутри
    названия колонки. csv.Sniffer на кириллице с кавычками тоже ошибается,
    поэтому пробуем все три варианта и смотрим на результат.
    """
    sample = [ln for ln in text.splitlines() if ln.strip()][:5]
    if not sample:
        return ","

    best, best_score = ",", (0.0, 0)
    for sep in (",", ";", "\t"):
        rows = list(csv.reader(sample, delimiter=sep))
        widths = [len(r) for r in rows if r]
        if not widths:
            continue
        common = max(set(widths), key=widths.count)
        consistency = widths.count(common) / len(widths)
        score = (consistency, common)
        if common >= 2 and score > best_score:
            best, best_score = sep, score
    return best


# --- буквы колонок ---


def column_letter_to_index(letter: str) -> int:
    """A → 0, G → 6, AA → 26. Буквы, потому что их оператор видит в Excel."""
    value = (letter or "").strip().upper()
    if not _COLUMN_RE.match(value):
        raise ImportFormatError(
            f"«{letter}» не похоже на обозначение колонки. Ожидается A, B, … AA."
        )
    index = 0
    for char in value:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def index_to_column_letter(index: int) -> str:
    number = index + 1
    out = ""
    while number > 0:
        number, rest = divmod(number - 1, 26)
        out = chr(65 + rest) + out
    return out


# --- чтение файла ---


def _cell_to_text(value) -> str:
    """Ячейка → строка без сюрпризов.

    Трек 836809 Excel отдаёт числом, и наивный str() превратил бы его в
    «836809.0» — такого трека в базе нет.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value).strip()


def _trim_trailing_blank(rows: list[list[str]]) -> list[list[str]]:
    """Хвост из пустых строк — артефакт Excel (форматирование без данных)."""
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()
    return rows


def _read_csv(raw: bytes) -> list[list[str]]:
    text = decode_bytes(raw)
    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    return [[_cell_to_text(cell) for cell in row] for row in reader]


def _read_xlsx(raw: bytes) -> list[list[str]]:
    try:
        import openpyxl

        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = book.worksheets[0]  # несколько листов — берём первый
        rows = [
            [_cell_to_text(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        book.close()
        return rows
    except ImportFormatError:
        raise
    except Exception:
        raise ImportFormatError(
            "Не удалось прочитать файл .xlsx. Откройте его в Excel и пересохраните."
        )


def _read_xls(raw: bytes) -> list[list[str]]:
    try:
        import xlrd

        book = xlrd.open_workbook(file_contents=raw)
        sheet = book.sheet_by_index(0)
        return [
            [_cell_to_text(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
    except Exception:
        raise ImportFormatError(
            "Не удалось прочитать файл .xls. Пересохраните его как .xlsx."
        )


def read_rows(file_obj: IO, filename: str) -> list[list[str]]:
    """Файл → таблица строк. Тип определяем по расширению имени."""
    raw = file_obj.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw.strip():
        raise ImportFormatError("Файл пустой.")

    name = (filename or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        rows = _read_csv(raw)
    elif name.endswith(".xlsx") or name.endswith(".xlsm"):
        rows = _read_xlsx(raw)
    elif name.endswith(".xls"):
        rows = _read_xls(raw)
    else:
        raise ImportFormatError(
            "Поддерживаются только файлы .xlsx, .xls и .csv."
        )

    rows = _trim_trailing_blank(rows)
    if not rows:
        raise ImportFormatError("В файле нет ни одной строки с данными.")
    return rows


# --- распознавание шапки ---


def _norm(cell: str) -> str:
    return re.sub(r"\s+", " ", (cell or "").strip().lower())


def _is_track_header(cell: str) -> bool:
    text = _norm(cell)
    if not text:
        return False
    return text.startswith(_TRACK_PREFIXES) or any(s in text for s in _TRACK_CONTAINS)


def _is_weight_header(cell: str) -> bool:
    text = _norm(cell)
    return bool(text) and text.startswith(_WEIGHT_PREFIXES)


def detect_layout(rows: list[list[str]]) -> Layout:
    """Найти шапку и колонки.

    Строка считается шапкой, только если в ней нашлась колонка трека: файл без
    трека импортировать всё равно нечем. Если шапки нет — данные идут с первой
    строки, а колонки обязан прислать клиент.
    """
    for row_index, row in enumerate(rows[:HEADER_SEARCH_DEPTH]):
        track_idx = next((i for i, cell in enumerate(row) if _is_track_header(cell)), None)
        if track_idx is None:
            continue

        weight_idx = next((i for i, cell in enumerate(row) if _is_weight_header(cell)), None)

        # «Клиент» — это ФИО, а не код: подставить её в код клиента значит
        # привязать посылки к несуществующим кодам. Сначала точное совпадение.
        code_idx = next(
            (i for i, cell in enumerate(row) if _norm(cell) in _CODE_EXACT), None
        )
        if code_idx is None:
            code_idx = next(
                (
                    i
                    for i, cell in enumerate(row)
                    # «Штрих-код» тоже содержит «код» — это колонка трека.
                    if i != track_idx and any(s in _norm(cell) for s in _CODE_CONTAINS)
                ),
                None,
            )

        return Layout(
            start_row=row_index + 2,
            track_column=index_to_column_letter(track_idx),
            weight_column=None if weight_idx is None else index_to_column_letter(weight_idx),
            client_code_column=None if code_idx is None else index_to_column_letter(code_idx),
        )

    return Layout(start_row=1)


# --- выборка строк ---


def _cell(row: list[str], letter: str | None) -> str:
    if not letter:
        return ""
    index = column_letter_to_index(letter)
    return row[index].strip() if index < len(row) else ""


def extract_rows(rows: list[list[str]], layout: Layout) -> list[ImportRow]:
    """Строки данных с номерами, как их видит оператор в Excel."""
    out: list[ImportRow] = []
    start = max(layout.start_row, 1)
    for offset, row in enumerate(rows[start - 1 :]):
        out.append(
            ImportRow(
                row=start + offset,
                track_number=_cell(row, layout.track_column),
                weight=_cell(row, layout.weight_column),
                client_code=_cell(row, layout.client_code_column),
            )
        )
    return out


# --- вес ---


def parse_weight(value) -> Decimal | None:
    """Вес ячейки в Decimal. Пусто — это не ошибка, мусор — ошибка.

    Молча потерять вес хуже, чем отказать: оператор об этом никогда не узнает,
    а посылка уедет клиенту с нулевой стоимостью доставки.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        result = Decimal(text.replace(",", "."))
    except InvalidOperation:
        raise ImportFormatError(f"Вес «{text}» не является числом")
    if not result.is_finite():
        raise ImportFormatError(f"Вес «{text}» не является числом")
    return result
