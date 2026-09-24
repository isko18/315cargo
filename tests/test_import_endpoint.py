"""POST manage/parcels/import/ — импорт накладной файлом.

Главное, что здесь проверяется: сумма по корзинам сходится с total_rows,
номера строк совпадают с номерами в Excel, dry_run ничего не пишет, а границы
(чужое карго, оператор Китая, размер файла) держатся серверно.
"""

import io

import pytest

from parcels.models import Parcel, ParcelImport
from tests.factories import PickupPointFactory, UserFactory

URL = "/api/manage/parcels/import/"


def _csv(text: str, name: str = "nakladnaya.csv", encoding: str = "utf-8"):
    buf = io.BytesIO(text.encode(encoding))
    buf.name = name
    return buf


def _xlsx(rows, name: str = "nakladnaya.xlsx"):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = name
    return buf


@pytest.fixture
def client_with_code(db, cargo_admin):
    return UserFactory(cargo=cargo_admin.cargo, client_code="ISI-0106")


# --- happy path ---


@pytest.mark.django_db
def test_csv_import_creates_parcels(cargo_admin_client, client_with_code):
    body = "Трек,Код клиента,\"Вес, кг\"\r\nABC1,ISI-0106,0.600\r\nABC2,ISI-0106,1,5\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body), "status": "at_pickup_point"},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    data = r.data
    assert data["total_rows"] == 2
    assert data["created"] == 2
    assert data["updated"] == 0
    assert data["errors"] == []
    assert Parcel.objects.filter(track_number="ABC1").exists()


@pytest.mark.django_db
def test_counts_always_add_up_to_total_rows(cargo_admin_client, client_with_code):
    """Если сумма не сходится, оператор не понимает, что с остатком."""
    body = (
        "Трек,Код клиента,Вес\r\n"
        "ABC1,ISI-0106,0.6\r\n"      # создастся
        ",,\r\n"                      # пустой трек → skipped
        "ABC2,НЕТ-ТАКОГО,1.0\r\n"     # клиент не найден → error
        "ABC3,ISI-0106,н/д\r\n"       # мусор в весе → error
    )
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 200, r.data
    d = r.data
    assert d["created"] + d["updated"] + d["skipped"] + len(d["errors"]) == d["total_rows"]
    assert d["total_rows"] == 4


@pytest.mark.django_db
def test_error_rows_carry_file_line_numbers(cargo_admin_client, client_with_code):
    """row — строка в файле вместе с шапкой: оператор идёт с ним в Excel."""
    body = "Трек,Код клиента,Вес\r\nABC1,ISI-0106,0.6\r\nABC2,ISI-0106,0.6 кг\r\n"
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 200, r.data
    assert [e["row"] for e in r.data["errors"]] == [3]
    assert r.data["errors"][0]["track_number"] == "ABC2"
    assert "0.6 кг" in r.data["errors"][0]["error"]


@pytest.mark.django_db
def test_second_upload_updates_instead_of_duplicating(cargo_admin_client, client_with_code):
    body = "Трек,Код клиента,Вес\r\nABC1,ISI-0106,0.6\r\n"
    payload = {"status": "arrived_china_warehouse"}
    first = cargo_admin_client.post(URL, {"file": _csv(body), **payload}, format="multipart")
    assert first.data["created"] == 1

    second = cargo_admin_client.post(URL, {"file": _csv(body), **payload}, format="multipart")
    assert second.data["created"] == 0
    assert second.data["updated"] == 1
    assert Parcel.objects.filter(track_number="ABC1").count() == 1


@pytest.mark.django_db
def test_xlsx_import(cargo_admin_client, client_with_code):
    buf = _xlsx([["Трек", "Код клиента", "Вес, кг"], [836809, "ISI-0106", 0.14]])
    r = cargo_admin_client.post(
        URL, {"file": buf, "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 200, r.data
    assert r.data["created"] == 1
    # Число из Excel не должно превратиться в «836809.0».
    assert Parcel.objects.filter(track_number="836809").exists()


@pytest.mark.django_db
def test_cp1251_file_is_read(cargo_admin_client, client_with_code):
    body = "Трек;Код клиента;Вес\r\nABC1;ISI-0106;0,6\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body, name="1c.csv", encoding="cp1251"), "status": "at_pickup_point"},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert r.data["created"] == 1


@pytest.mark.django_db
def test_bom_does_not_break_first_track(cargo_admin_client, client_with_code):
    """BOM приклеился бы к первому треку, и он не совпал бы ни с чем."""
    body = "﻿Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 200, r.data
    assert Parcel.objects.filter(track_number="ABC1").exists()


# --- detected / ручные колонки ---


@pytest.mark.django_db
def test_detected_is_returned(cargo_admin_client, client_with_code):
    body = "Трек,Товар,Клиент,Код клиента,Телефон,Статус,\"Вес, кг\"\r\nABC1,,Иванова,ISI-0106,+996,В ПВЗ,0.6\r\n"
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 200, r.data
    assert r.data["detected"] == {
        "start_row": 2,
        "track_column": "A",
        "weight_column": "G",
        "client_code_column": "D",
    }


@pytest.mark.django_db
def test_client_columns_override_detection(cargo_admin_client, client_with_code):
    """Автоопределение промахнулось — оператор указывает колонки руками."""
    body = "первая,вторая\r\nмусор,ABC1\r\n"
    r = cargo_admin_client.post(
        URL,
        {
            "file": _csv(body),
            "status": "at_pickup_point",
            "start_row": 2,
            "track_column": "B",
        },
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert r.data["created"] == 1
    assert r.data["detected"]["track_column"] == "B"
    assert Parcel.objects.filter(track_number="ABC1").exists()


@pytest.mark.django_db
def test_missing_track_column_is_a_human_400(cargo_admin_client):
    body = "Товар,Цена\r\nноутбук,100\r\n"
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 400
    assert "трек" in r.data["detail"].lower()
    assert "Traceback" not in r.data["detail"]


@pytest.mark.django_db
def test_bad_column_letter_is_rejected(cargo_admin_client):
    body = "Трек\r\nABC1\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body), "status": "at_pickup_point", "track_column": "A1"},
        format="multipart",
    )
    assert r.status_code == 400


# --- dry_run ---


@pytest.mark.django_db
def test_dry_run_writes_nothing_but_counts(cargo_admin_client, client_with_code):
    body = "Трек,Код клиента,Вес\r\nABC1,ISI-0106,0.6\r\nABC2,ISI-0106,0.7\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body), "status": "at_pickup_point", "dry_run": "true"},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert r.data["created"] == 2
    assert Parcel.objects.count() == 0
    assert ParcelImport.objects.count() == 0
    assert "source_file" not in r.data


@pytest.mark.django_db
def test_dry_run_returns_preview(cargo_admin_client, client_with_code):
    rows = "\r\n".join(f"ABC{i},ISI-0106,0.6" for i in range(1, 15))
    body = f"Трек,Код клиента,Вес\r\n{rows}\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body), "status": "at_pickup_point", "dry_run": "true"},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert len(r.data["preview"]) == 10
    assert r.data["preview"][0] == {
        "row": 2,
        "track_number": "ABC1",
        "weight": "0.6",
        "client_code": "ISI-0106",
    }


@pytest.mark.django_db
def test_dry_run_reports_same_errors_as_real_run(cargo_admin_client, client_with_code):
    """Предпросмотр бесполезен, если показывает не то, что будет при записи."""
    body = "Трек,Код клиента,Вес\r\nABC1,НЕТ-ТАКОГО,0.6\r\n"
    payload = {"file": _csv(body), "status": "at_pickup_point", "dry_run": "true"}
    dry = cargo_admin_client.post(URL, payload, format="multipart")
    real = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert [e["error"] for e in dry.data["errors"]] == [e["error"] for e in real.data["errors"]]


# --- хранение файла и журнал ---


@pytest.mark.django_db
def test_file_is_stored_and_linked(cargo_admin_client, client_with_code):
    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body, name="sklad-2026-09-22.csv"), "status": "at_pickup_point"},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert r.data["file_name"] == "sklad-2026-09-22.csv"
    assert "source_file" in r.data
    record = ParcelImport.objects.get()
    assert record.total_rows == 1
    assert record.created_count == 1
    assert record.actor_id == cargo_admin_client.user.id


@pytest.mark.django_db
def test_import_is_written_to_audit(cargo_admin_client, client_with_code):
    from common.models import AuditLog

    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert AuditLog.objects.filter(action=AuditLog.Action.PARCEL_IMPORTED).exists()


# --- границы ---


@pytest.mark.django_db
def test_china_operator_cannot_set_pickup_status(api_client, db):
    from users.models import User

    operator = User.objects.create(
        phone="+996700000778", is_staff=True, is_china_staff=True, cargo=None
    )
    from rest_framework_simplejwt.tokens import RefreshToken

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(operator).access_token}")
    body = "Трек\r\nABC1\r\n"
    r = api_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 403
    assert r.data["code"] == "forbidden_status"


@pytest.mark.django_db
def test_china_operator_can_use_china_status(api_client, db):
    from rest_framework_simplejwt.tokens import RefreshToken
    from users.models import User

    operator = User.objects.create(
        phone="+996700000779", is_staff=True, is_china_staff=True, cargo=None
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(operator).access_token}")
    body = "Трек\r\nABC1\r\n"
    r = api_client.post(
        URL, {"file": _csv(body), "status": "arrived_china_warehouse"}, format="multipart"
    )
    assert r.status_code == 200, r.data


@pytest.mark.django_db
def test_client_cannot_import(auth_client):
    body = "Трек\r\nABC1\r\n"
    r = auth_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 403


@pytest.mark.django_db
def test_anonymous_cannot_import(api_client):
    body = "Трек\r\nABC1\r\n"
    r = api_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 401


@pytest.mark.django_db
def test_unknown_status_is_rejected(cargo_admin_client):
    body = "Трек\r\nABC1\r\n"
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "телепортирован"}, format="multipart"
    )
    assert r.status_code == 400
    assert "status" in r.data


@pytest.mark.django_db
def test_unsupported_format_is_rejected(cargo_admin_client):
    buf = io.BytesIO(b"%PDF-1.4 whatever")
    buf.name = "nakladnaya.pdf"
    r = cargo_admin_client.post(
        URL, {"file": buf, "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 400
    assert ".xlsx" in r.data["detail"]


@pytest.mark.django_db
def test_empty_file_is_rejected(cargo_admin_client):
    r = cargo_admin_client.post(
        URL, {"file": _csv("   "), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_too_big_file_gets_413(cargo_admin_client, settings):
    from parcels import manage_views

    monkey = manage_views.IMPORT_MAX_FILE_BYTES
    manage_views.IMPORT_MAX_FILE_BYTES = 100
    try:
        body = "Трек,Код клиента\r\n" + "\r\n".join(f"ABC{i},X" for i in range(50))
        r = cargo_admin_client.post(
            URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
        )
        assert r.status_code == 413
        assert "МБ" in r.data["detail"]
    finally:
        manage_views.IMPORT_MAX_FILE_BYTES = monkey


@pytest.mark.django_db
def test_too_many_rows_is_rejected(cargo_admin_client):
    from parcels import manage_views

    monkey = manage_views.IMPORT_MAX_ROWS
    manage_views.IMPORT_MAX_ROWS = 3
    try:
        body = "Трек\r\n" + "\r\n".join(f"ABC{i}" for i in range(10))
        r = cargo_admin_client.post(
            URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
        )
        assert r.status_code == 400
        assert "строк" in r.data["detail"]
    finally:
        manage_views.IMPORT_MAX_ROWS = monkey


@pytest.mark.django_db
def test_pickup_point_is_applied(cargo_admin_client, client_with_code):
    point = PickupPointFactory(cargo=cargo_admin_client.user.cargo)
    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    r = cargo_admin_client.post(
        URL,
        {"file": _csv(body), "status": "at_pickup_point", "pickup_point": point.id},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert Parcel.objects.get(track_number="ABC1").pickup_point_id == point.id


@pytest.mark.django_db
def test_bulk_scan_still_works(cargo_admin_client):
    """Старый эндпоинт удалять нельзя: в сторах месяцами живут старые сборки."""
    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-scan/",
        {"status": "arrived_china_warehouse", "items": [{"track_number": "OLD-1"}]},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["created"] == 1


@pytest.mark.django_db
def test_history_links_back_to_the_uploaded_file(cargo_admin_client, client_with_code):
    """Из журнала операций должно открываться то, что реально залили."""
    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    imp = cargo_admin_client.post(
        URL,
        {"file": _csv(body, name="sklad.csv"), "status": "at_pickup_point"},
        format="multipart",
    )
    assert imp.status_code == 200, imp.data

    hist = cargo_admin_client.get("/api/history/?limit=50")
    rows = hist.data["results"] if isinstance(hist.data, dict) else hist.data
    imported = [r for r in rows if r["track_number"] == "ABC1"]
    assert imported, rows
    assert imported[0]["source_file"], "ссылка на накладную потерялась"
    assert "sklad" in imported[0]["source_file"]


@pytest.mark.django_db
def test_manual_scan_has_no_source_file(cargo_admin_client):
    """Операции руками файлом не помечаются — иначе ссылка врёт."""
    cargo_admin_client.post(
        "/api/manage/parcels/bulk-scan/",
        {"status": "arrived_china_warehouse", "items": [{"track_number": "MANUAL-1"}]},
        format="json",
    )
    hist = cargo_admin_client.get("/api/history/?limit=50")
    rows = hist.data["results"] if isinstance(hist.data, dict) else hist.data
    manual = [r for r in rows if r["track_number"] == "MANUAL-1"]
    assert manual
    assert manual[0]["source_file"] is None


# --- статус по умолчанию: импорт заводит посылку на складе в Китае ---


@pytest.mark.django_db
def test_import_without_status_lands_on_china_warehouse(cargo_admin_client, client_with_code):
    """Импорт — точка входа посылки в систему, отсюда и стартует цепочка."""
    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    r = cargo_admin_client.post(URL, {"file": _csv(body)}, format="multipart")
    assert r.status_code == 200, r.data
    assert Parcel.objects.get(track_number="ABC1").status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE


@pytest.mark.django_db
def test_import_sets_the_chain_anchor(cargo_admin_client, client_with_code):
    """Без записи в истории якорь цепочки уедет на created_at.

    Тогда отсчёт пойдёт от создания посылки, а не от приёмки на складе, и
    статусы будут меняться раньше времени.
    """
    from parcels.models import ParcelStatusHistory
    from parcels.services import _auto_anchor

    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    cargo_admin_client.post(URL, {"file": _csv(body)}, format="multipart")

    parcel = Parcel.objects.get(track_number="ABC1")
    anchor_row = ParcelStatusHistory.objects.filter(
        parcel=parcel, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    ).first()
    assert anchor_row is not None
    assert _auto_anchor(parcel) == anchor_row.created_at


@pytest.mark.django_db
def test_imported_parcel_moves_along_the_chain(cargo_admin_client, client_with_code):
    """Через сутки после импорта посылка обязана поехать «В пути»."""
    from datetime import timedelta

    from django.utils import timezone

    from parcels.models import ParcelStatusHistory
    from parcels.services import advance_parcel_auto

    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    cargo_admin_client.post(URL, {"file": _csv(body)}, format="multipart")

    parcel = Parcel.objects.get(track_number="ABC1")
    ParcelStatusHistory.objects.filter(
        parcel=parcel, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    ).update(created_at=timezone.now() - timedelta(days=1, hours=1))

    assert advance_parcel_auto(parcel) is True
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.IN_TRANSIT


@pytest.mark.django_db
def test_explicit_status_still_wins(cargo_admin_client, client_with_code):
    """Оператор ПВЗ принимает коробку — его статус важнее умолчания."""
    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    r = cargo_admin_client.post(
        URL, {"file": _csv(body), "status": "at_pickup_point"}, format="multipart"
    )
    assert r.status_code == 200, r.data
    assert Parcel.objects.get(track_number="ABC1").status == Parcel.Status.AT_PICKUP_POINT


@pytest.mark.django_db
def test_reupload_does_not_drag_parcel_backwards(cargo_admin_client, client_with_code):
    """Старая накладная не должна возвращать посылку на склад в Китае.

    С умолчанием «склад в Китае» это стало реальным сценарием: посылка уже
    уехала по цепочке, а оператор переливает ту же накладную. Откат отклоняется
    и попадает в errors — строка видна, но статус не портится.
    """
    body = "Трек,Код клиента\r\nABC1,ISI-0106\r\n"
    cargo_admin_client.post(URL, {"file": _csv(body)}, format="multipart")

    parcel = Parcel.objects.get(track_number="ABC1")
    parcel.status = Parcel.Status.CUSTOMS
    parcel.save(update_fields=["status"])

    again = cargo_admin_client.post(URL, {"file": _csv(body)}, format="multipart")
    assert again.status_code == 200, again.data
    assert again.data["created"] == 0
    assert len(again.data["errors"]) == 1
    assert "дальше по маршруту" in again.data["errors"][0]["error"]

    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.CUSTOMS
