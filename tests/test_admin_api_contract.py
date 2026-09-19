"""Контракт панели: имена ключей, параметры поиска, фото в рассылке.

Эти тесты стерегут не логику, а слова. Мобильная панель читала ключи сводки,
угаданные по скриншоту, и строку поиска слала сразу под тремя именами, потому
что схема их не объявляла. Переименование любого ключа здесь гасит плитку на
чужом экране молча — ошибки не будет.
"""

import io

import pytest
from PIL import Image

from notifications.models import Notification
from notifications.services import get_or_create_preference
from tests.factories import PickupPointFactory, UserFactory


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    buf.seek(0)
    buf.name = "banner.png"
    return buf


# --- Сводка ---


@pytest.mark.django_db
def test_dashboard_keeps_every_key_the_app_reads(cargo_admin_client):
    """Список из BACKEND_ADMIN_API.md — то, что приложение реально читает."""
    expected = {
        "period_revenue_kgs",
        "period_issued_count",
        "period_received_count",
        "period_avg_check_kgs",
        "period_avg_weight_kg",
        "period_weight_kg",
        "issued_revenue_kgs",
        "potential_revenue_kgs",
        "total_weight_kg",
        "parcels_count",
        "orders_count",
        "clients_count",
        "pickup_points_count",
        "parcels_pending_count",
        "price_per_kg_kgs",
        "by_status",
    }

    r = cargo_admin_client.get("/api/manage/dashboard/")

    assert r.status_code == 200
    assert expected <= set(r.data)


@pytest.mark.django_db
def test_dashboard_synonyms_hold_the_same_numbers(cargo_admin_client):
    """Веб-панель читает старые имена, мобильная — новые. Разъехаться нельзя."""
    d = cargo_admin_client.get("/api/manage/dashboard/").data

    assert d["clients_count"] == d["users_count"]
    assert d["by_status"] == d["parcels_by_status"]


# --- Поиск ---


@pytest.mark.django_db
@pytest.mark.parametrize("param", ["q", "search", "query"])
def test_client_search_accepts_every_param_name(cargo_admin_client, param):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo, full_name="Искомый Клиент")

    r = cargo_admin_client.get(f"/api/clients/search/?{param}=Искомый")

    assert r.status_code == 200
    assert client.id in [c["id"] for c in r.data]


@pytest.mark.django_db
@pytest.mark.parametrize("param", ["search", "q", "query"])
def test_client_list_accepts_every_param_name(cargo_admin_client, param):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo, full_name="Искомый Клиент")
    UserFactory(cargo=cargo, full_name="Другой Человек")

    rows = cargo_admin_client.get(f"/api/manage/clients/?{param}=Искомый").data

    assert [c["id"] for c in rows] == [client.id]


# --- Переключатель пушей ---


@pytest.mark.django_db
def test_patch_client_turns_push_off(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)

    r = cargo_admin_client.patch(
        f"/api/manage/clients/{client.id}/", {"push_enabled": False}, format="json"
    )

    assert r.status_code == 200
    assert r.data["push_enabled"] is False
    assert get_or_create_preference(client).push_enabled is False


@pytest.mark.django_db
def test_patch_client_keeps_counters_in_response(cargo_admin_client):
    """Счётчики — аннотации; refresh_from_db() их терял."""
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)

    r = cargo_admin_client.patch(
        f"/api/manage/clients/{client.id}/", {"push_enabled": True}, format="json"
    )

    assert r.data["orders_count"] == 0
    assert r.data["parcels_count"] == 0


@pytest.mark.django_db
def test_patch_client_of_other_cargo_is_not_found(cargo_admin_client):
    from tests.factories import CargoCompanyFactory

    stranger = UserFactory(cargo=CargoCompanyFactory())

    r = cargo_admin_client.patch(
        f"/api/manage/clients/{stranger.id}/", {"push_enabled": False}, format="json"
    )

    assert r.status_code == 404


# --- Фото в рассылке ---


@pytest.mark.django_db
def test_broadcast_accepts_an_image(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    UserFactory(cargo=cargo, pickup_point=PickupPointFactory(cargo=cargo))

    r = cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "С фото", "body": "текст", "send_push": False, "image": png_bytes()},
        format="multipart",
    )

    assert r.status_code == 201
    sent = Notification.objects.filter(title="С фото")
    assert sent.exists()
    assert all(n.image for n in sent)


@pytest.mark.django_db
def test_broadcast_stores_one_copy_for_all_recipients(cargo_admin_client):
    """Файл в каждой строке дал бы N копий одной картинки в хранилище."""
    cargo = cargo_admin_client.user.cargo
    point = PickupPointFactory(cargo=cargo)
    for _ in range(3):
        UserFactory(cargo=cargo, pickup_point=point)

    cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Одна картинка", "body": "текст", "send_push": False, "image": png_bytes()},
        format="multipart",
    )

    names = set(Notification.objects.filter(title="Одна картинка").values_list("image", flat=True))
    assert len(names) == 1


@pytest.mark.django_db
def test_broadcast_without_image_still_works_as_json(cargo_admin_client):
    """Поле необязательное: панель шлёт JSON и про картинку не знает."""
    cargo = cargo_admin_client.user.cargo
    UserFactory(cargo=cargo)

    r = cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Без фото", "body": "текст", "send_push": False},
        format="json",
    )

    assert r.status_code == 201
    assert not Notification.objects.filter(title="Без фото").exclude(image="").exists()


@pytest.mark.django_db
def test_client_sees_the_image_in_his_notifications(api_client, cargo_admin_client, cargo_admin):
    from rest_framework_simplejwt.tokens import RefreshToken

    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo)
    cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Клиенту", "body": "текст", "send_push": False, "image": png_bytes()},
        format="multipart",
    )

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(client).access_token}"
    )
    rows = api_client.get("/api/notifications/").data
    rows = rows["results"] if isinstance(rows, dict) and "results" in rows else rows

    row = next(n for n in rows if n["title"] == "Клиенту")
    assert row["image"]


@pytest.mark.django_db
def test_broadcast_list_carries_the_image(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    UserFactory(cargo=cargo)
    cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "В списке", "body": "текст", "send_push": False, "image": png_bytes()},
        format="multipart",
    )

    rows = cargo_admin_client.get("/api/manage/notifications/").data

    row = next(r for r in rows if r["title"] == "В списке")
    assert row["image"]
