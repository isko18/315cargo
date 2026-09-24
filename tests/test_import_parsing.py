"""Разбор файла накладной: кодировки, разделители, шапка, колонки, вес.

Всё здесь — чистые функции без БД и HTTP: именно они ломаются на реальных
файлах поставщиков, и чинить их надо без поднятия Django.
"""

import io
from decimal import Decimal

import pytest

from parcels.importers import (
    ImportFormatError,
    column_letter_to_index,
    decode_bytes,
    detect_layout,
    extract_rows,
    index_to_column_letter,
    parse_weight,
    read_rows,
)

# Шапка реальной выгрузки склада из веб-панели.
REAL_HEADER = 'Трек,Товар,Клиент,Код клиента,Телефон,Статус,"Вес, кг","Стоимость, сом",ПВЗ,Создан'
REAL_ROWS = [
    'ISI-0106,,,,,В ПВЗ,0.600,126.60,,"22 сент. 2026 г., 01:31"',
    '836809,,Иванова Айгуль,ISI-0106,+996700000001,В ПВЗ,0.140,29.54,1 КАРГО Ош,"21 сент."',
    'JT5517921201290,Leno夹板负离子不伤发护发直板夹,Асанова Нургуль,ISI-0192,+996700000002,Оформлен,,,1 КАРГО Ош,"21 сент."',
]
REAL_CSV = "\r\n".join([REAL_HEADER, *REAL_ROWS])


# --- кодировки ---


def test_utf8_bom_is_stripped():
    """BOM приклеивается к первой ячейке, и трек перестаёт совпадать с базой."""
    raw = "﻿Трек,Вес\r\nABC123,1.5".encode("utf-8")
    text = decode_bytes(raw)
    assert not text.startswith("﻿")
    assert text.splitlines()[0] == "Трек,Вес"


def test_plain_utf8():
    raw = "Трек,Вес\r\nABC123,1.5".encode("utf-8")
    assert "Трек" in decode_bytes(raw)


def test_cp1251_from_1c():
    """Выгрузки из 1С и старого Excel приходят в cp1251."""
    raw = "Трек,Код клиента\r\nABC123,ISI-0106".encode("cp1251")
    text = decode_bytes(raw)
    assert "Трек" in text
    assert "Код клиента" in text


# --- разделители ---


@pytest.mark.parametrize("sep", [",", ";", "\t"])
def test_delimiter_is_detected(sep):
    raw = sep.join(["Трек", "Вес", "Код клиента"]) + "\r\n" + sep.join(["ABC1", "0.5", "ISI-1"])
    rows = read_rows(io.BytesIO(raw.encode("utf-8")), "nakladnaya.csv")
    assert rows[0] == ["Трек", "Вес", "Код клиента"]
    assert rows[1] == ["ABC1", "0.5", "ISI-1"]


def test_quoted_commas_do_not_split_cells():
    """В реальной выгрузке запятые внутри кавычек: «Вес, кг», дата с запятой."""
    rows = read_rows(io.BytesIO(REAL_CSV.encode("utf-8")), "sklad.csv")
    assert rows[0][6] == "Вес, кг"
    assert rows[1][0] == "ISI-0106"
    # Китайское название товара не рвёт строку.
    assert "夹板" in rows[3][1]


# --- буквы колонок ---


@pytest.mark.parametrize(
    "letter,index", [("A", 0), ("B", 1), ("G", 6), ("Z", 25), ("AA", 26), ("AB", 27)]
)
def test_column_letter_to_index(letter, index):
    assert column_letter_to_index(letter) == index
    assert index_to_column_letter(index) == letter


def test_lowercase_letter_is_accepted():
    assert column_letter_to_index("g") == 6


@pytest.mark.parametrize("bad", ["", "1", "A1", "-", "ЯЯ"])
def test_bad_column_letter_is_rejected(bad):
    with pytest.raises(ImportFormatError):
        column_letter_to_index(bad)


# --- шапка ---


def test_layout_detected_on_real_export():
    rows = read_rows(io.BytesIO(REAL_CSV.encode("utf-8")), "sklad.csv")
    layout = detect_layout(rows)
    assert layout.start_row == 2
    assert layout.track_column == "A"
    assert layout.weight_column == "G"
    assert layout.client_code_column == "D"


def test_client_name_column_is_not_taken_as_code():
    """«Клиент» — это ФИО. Подставить её в код — привязать к несуществующим."""
    rows = read_rows(io.BytesIO(REAL_CSV.encode("utf-8")), "sklad.csv")
    layout = detect_layout(rows)
    # C — «Клиент» (ФИО), D — «Код клиента».
    assert layout.client_code_column != "C"


@pytest.mark.parametrize(
    "header",
    ["Трек-номер", "track number", "Штрих-код", "barcode", "Номер трека"],
)
def test_track_header_synonyms(header):
    csv = f"{header};Вес\r\nABC1;1.0"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    assert detect_layout(rows).track_column == "A"


@pytest.mark.parametrize("header", ["Вес", "weight", "Салмак", "Салмагы", "Вес, кг"])
def test_weight_header_synonyms(header):
    csv = f"Трек;{header}\r\nABC1;1.0"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    assert detect_layout(rows).weight_column == "B"


def test_header_found_below_first_row():
    """Шапку ищем в первых пяти строках: сверху бывает заголовок документа."""
    csv = "Накладная №17\r\n\r\nТрек;Вес\r\nABC1;1.0"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    layout = detect_layout(rows)
    assert layout.start_row == 4
    assert layout.track_column == "A"


def test_no_header_means_data_from_first_row():
    """Без шапки колонки обязан прислать клиент — сами не угадываем."""
    csv = "ABC1;1.0\r\nABC2;2.0"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    layout = detect_layout(rows)
    assert layout.start_row == 1
    assert layout.track_column is None


def test_row_is_header_only_if_it_has_track_column():
    """Строка с «Вес», но без трека — не шапка."""
    csv = "Вес;Стоимость\r\n1.0;10"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    assert detect_layout(rows).track_column is None


# --- вес ---


@pytest.mark.parametrize(
    "raw,expected",
    [("0,6", Decimal("0.6")), ("0.600", Decimal("0.600")), ("1", Decimal("1")), (" 2,5 ", Decimal("2.5"))],
)
def test_weight_accepts_comma_and_dot(raw, expected):
    assert parse_weight(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_weight_is_not_an_error(raw):
    assert parse_weight(raw) is None


@pytest.mark.parametrize("raw", ["—", "н/д", "0.6 кг", "abc", "1,2,3"])
def test_garbage_weight_is_rejected(raw):
    """Молча потерять вес хуже, чем отказать: оператор об этом не узнает."""
    with pytest.raises(ImportFormatError) as exc:
        parse_weight(raw)
    assert raw.strip() in str(exc.value)


# --- выборка строк ---


def test_extract_rows_uses_file_line_numbers():
    """row — номер строки в файле вместе с шапкой: с ним идут в Excel."""
    rows = read_rows(io.BytesIO(REAL_CSV.encode("utf-8")), "sklad.csv")
    layout = detect_layout(rows)
    items = extract_rows(rows, layout)
    assert [i.row for i in items] == [2, 3, 4]
    assert items[0].track_number == "ISI-0106"
    assert items[1].client_code == "ISI-0106"
    assert items[2].weight in ("", None)


def test_trailing_blank_rows_are_trimmed():
    """Хвост пустых строк — артефакт Excel, в total_rows ему не место."""
    csv = "Трек;Вес\r\nABC1;1.0\r\n;\r\n\r\n"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    items = extract_rows(rows, detect_layout(rows))
    assert [i.track_number for i in items] == ["ABC1"]


def test_blank_row_in_the_middle_keeps_line_numbers():
    """Пустую строку внутри файла срезать нельзя — уедут номера строк.

    Оператор идёт с номером в Excel, и строка 4 обязана быть строкой 4.
    """
    csv = "Трек;Вес\r\nABC1;1.0\r\n;\r\nABC2;2.0"
    rows = read_rows(io.BytesIO(csv.encode("utf-8")), "x.csv")
    items = extract_rows(rows, detect_layout(rows))
    assert [(i.row, i.track_number) for i in items] == [(2, "ABC1"), (3, ""), (4, "ABC2")]


# --- xlsx ---


def _xlsx_bytes(rows):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_xlsx_is_read():
    buf = _xlsx_bytes(
        [["Трек", "Код клиента", "Вес, кг"], ["ABC1", "ISI-1", 0.6], ["ABC2", "", None]]
    )
    rows = read_rows(buf, "nakladnaya.xlsx")
    layout = detect_layout(rows)
    assert layout.track_column == "A"
    assert layout.weight_column == "C"
    items = extract_rows(rows, layout)
    assert items[0].track_number == "ABC1"
    assert parse_weight(items[0].weight) == Decimal("0.6")


def test_xlsx_number_stored_as_text_still_parses():
    """Поставщики шлют числа текстом — это не должно ронять разбор."""
    buf = _xlsx_bytes([["Трек", "Вес"], ["ABC1", "0,6"]])
    rows = read_rows(buf, "x.xlsx")
    items = extract_rows(rows, detect_layout(rows))
    assert parse_weight(items[0].weight) == Decimal("0.6")


def test_xlsx_track_number_is_not_mangled_into_float():
    """Трек 836809 не должен превратиться в «836809.0»."""
    buf = _xlsx_bytes([["Трек", "Вес"], [836809, 0.14]])
    rows = read_rows(buf, "x.xlsx")
    items = extract_rows(rows, detect_layout(rows))
    assert items[0].track_number == "836809"


def test_unsupported_extension_is_rejected():
    with pytest.raises(ImportFormatError):
        read_rows(io.BytesIO(b"whatever"), "nakladnaya.pdf")


def test_broken_xlsx_gives_human_error():
    with pytest.raises(ImportFormatError) as exc:
        read_rows(io.BytesIO(b"not really a workbook"), "x.xlsx")
    assert "Traceback" not in str(exc.value)


def test_empty_file_is_rejected():
    with pytest.raises(ImportFormatError):
        read_rows(io.BytesIO(b""), "x.csv")
