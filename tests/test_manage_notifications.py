"""Рассылка уведомлений клиентам из панели.

Опасность здесь — охват: рассылка уходит живым людям, и ошибка в скоупе
означает сообщение чужим клиентам, которое уже не отозвать.
"""

import pytest

from notifications.models import Notification
from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory


@pytest.fixture
def clients(db, cargo_admin):
    cargo = cargo_admin.cargo
    a = PickupPointFactory(cargo=cargo, title="ПВЗ А")
    b = PickupPointFactory(cargo=cargo, title="ПВЗ Б")
    return {
        "a": [UserFactory(cargo=cargo, pickup_point=a) for _ in range(2)],
        "b": [UserFactory(cargo=cargo, pickup_point=b)],
        "point_a": a,
        "point_b": b,
    }


@pytest.mark.django_db
def test_broadcast_reaches_all_cargo_clients(cargo_admin_client, clients):
    r = cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Поступление", "body": "Заказы до 23 августа", "send_push": False},
        format="json",
    )

    assert r.status_code == 201
    assert r.data["recipients_count"] == 3
    assert Notification.objects.filter(title="Поступление").count() == 3


@pytest.mark.django_db
def test_broadcast_limited_to_selected_pickup(cargo_admin_client, clients):
    r = cargo_admin_client.post(
        "/api/manage/notifications/",
        {
            "title": "Только А",
            "body": "текст",
            "pickup_points": [clients["point_a"].id],
            "send_push": False,
        },
        format="json",
    )

    assert r.data["recipients_count"] == 2
    got = set(Notification.objects.filter(title="Только А").values_list("user_id", flat=True))
    assert got == {u.id for u in clients["a"]}


@pytest.mark.django_db
def test_broadcast_never_reaches_other_cargo(cargo_admin_client, clients):
    """Клиент чужого карго не должен получить рассылку ни при каких фильтрах."""
    stranger = UserFactory(cargo=CargoCompanyFactory())

    cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Всем", "body": "текст", "send_push": False},
        format="json",
    )

    # Не «вообще без уведомлений»: при регистрации клиент получает приветствие.
    assert not Notification.objects.filter(user=stranger, title="Всем").exists()


@pytest.mark.django_db
def test_pickup_of_other_cargo_is_rejected(cargo_admin_client, clients):
    foreign = PickupPointFactory(cargo=CargoCompanyFactory())

    r = cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Чужим", "body": "текст", "pickup_points": [foreign.id], "send_push": False},
        format="json",
    )

    assert r.status_code == 400
    assert not Notification.objects.filter(title="Чужим").exists()


@pytest.mark.django_db
def test_list_groups_broadcast_into_one_row(cargo_admin_client, clients):
    """Рассылка — это N копий; в списке она должна быть одной строкой."""
    cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Одна рассылка", "body": "текст", "send_push": False},
        format="json",
    )

    rows = cargo_admin_client.get("/api/manage/notifications/").data
    mine = [r for r in rows if r["title"] == "Одна рассылка"]
    assert len(mine) == 1
    assert mine[0]["recipients_count"] == 3


@pytest.mark.django_db
def test_delete_removes_whole_broadcast(cargo_admin_client, clients):
    """Удаление одной копии оставило бы остальных с тем же текстом."""
    created = cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Удалить", "body": "текст", "send_push": False},
        format="json",
    ).data

    r = cargo_admin_client.delete(f"/api/manage/notifications/{created['id']}/")

    assert r.status_code == 204
    assert not Notification.objects.filter(title="Удалить").exists()


@pytest.mark.django_db
def test_push_enabled_visible_in_client_list(cargo_admin_client, clients):
    from notifications.services import get_or_create_preference

    client = clients["a"][0]
    pref = get_or_create_preference(client)
    pref.push_enabled = False
    pref.save(update_fields=["push_enabled"])

    rows = cargo_admin_client.get("/api/manage/clients/").data
    row = next(r for r in rows if r["id"] == client.id)
    assert row["push_enabled"] is False


@pytest.mark.django_db
def test_push_enabled_defaults_true_without_preference(cargo_admin_client, clients):
    """У старых клиентов настройки нет — считаем, что пуши разрешены."""
    rows = cargo_admin_client.get("/api/manage/clients/").data
    assert all(r["push_enabled"] is True for r in rows)
