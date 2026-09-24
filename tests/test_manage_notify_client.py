"""POST manage/notifications/send/ — адресное уведомление клиенту.

Рассылка по ПВЗ уже была; здесь админ пишет конкретным людям — например из
карточки клиента «ваша посылка ждёт в ПВЗ».

Главный риск не в доставке, а в границах: чужой клиент не должен получать
сообщение, а привязанный к ПВЗ оператор — писать за пределы своего пункта.
"""

import io

import pytest

from notifications.models import Notification, NotificationType
from tests.factories import PickupPointFactory, UserFactory

URL = "/api/manage/notifications/send/"


@pytest.fixture
def my_client(db, cargo_admin):
    return UserFactory(
        cargo=cargo_admin.cargo,
        pickup_point=cargo_admin.pickup_point,
        client_code="ISI-0106",
    )


def _png():
    """Однопиксельный PNG — ImageField требует настоящую картинку."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="PNG")
    buf.seek(0)
    buf.name = "promo.png"
    return buf


# --- отправка ---


@pytest.mark.django_db
def test_send_to_one_client_by_id(cargo_admin_client, my_client):
    r = cargo_admin_client.post(
        URL,
        {"clients": [my_client.id], "title": "Посылка ждёт", "body": "Заберите до пятницы"},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["recipients_count"] == 1

    note = Notification.objects.get(user=my_client, title="Посылка ждёт")
    assert note.body == "Заберите до пятницы"
    assert note.type == NotificationType.PERSONAL


@pytest.mark.django_db
def test_send_by_client_code(cargo_admin_client, my_client):
    """У оператора на руках код с коробки, а не внутренний id."""
    r = cargo_admin_client.post(
        URL,
        {"client_codes": ["ISI-0106"], "title": "Привет", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["recipients_count"] == 1
    assert Notification.objects.filter(user=my_client).exists()


@pytest.mark.django_db
def test_send_to_several_clients(cargo_admin_client, cargo_admin):
    one = UserFactory(cargo=cargo_admin.cargo, pickup_point=cargo_admin.pickup_point)
    two = UserFactory(cargo=cargo_admin.cargo, pickup_point=cargo_admin.pickup_point)
    r = cargo_admin_client.post(
        URL,
        {"clients": [one.id, two.id], "title": "Склад закрыт", "body": "1 января"},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["recipients_count"] == 2
    assert Notification.objects.filter(title="Склад закрыт").count() == 2


@pytest.mark.django_db
def test_id_and_code_pointing_at_same_client_send_once(cargo_admin_client, my_client):
    """Дубли в запросе не должны превращаться в два сообщения подряд."""
    r = cargo_admin_client.post(
        URL,
        {
            "clients": [my_client.id],
            "client_codes": ["ISI-0106"],
            "title": "Раз",
            "body": "Текст",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["recipients_count"] == 1
    assert Notification.objects.filter(user=my_client, title="Раз").count() == 1


@pytest.mark.django_db
def test_image_is_attached(cargo_admin_client, my_client):
    r = cargo_admin_client.post(
        URL,
        {
            "clients": [my_client.id],
            "title": "Акция",
            "body": "Смотрите",
            "image": _png(),
        },
        format="multipart",
    )
    assert r.status_code == 201, r.data
    assert Notification.objects.get(user=my_client, title="Акция").image


@pytest.mark.django_db
def test_client_sees_it_in_own_feed(cargo_admin_client, my_client, api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    cargo_admin_client.post(
        URL,
        {"clients": [my_client.id], "title": "Личное", "body": "Только вам"},
        format="json",
    )
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(my_client).access_token}"
    )
    r = api_client.get("/api/notifications/")
    rows = r.data["results"] if isinstance(r.data, dict) else r.data
    assert "Личное" in [x["title"] for x in rows]


@pytest.mark.django_db
def test_push_off_still_leaves_record(cargo_admin_client, my_client):
    """Клиент отключил пуши — сообщение обязано остаться в списке."""
    from notifications.services import get_or_create_preference

    prefs = get_or_create_preference(my_client)
    prefs.push_enabled = False
    prefs.save()

    r = cargo_admin_client.post(
        URL,
        {"clients": [my_client.id], "title": "Важное", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert Notification.objects.filter(user=my_client, title="Важное").exists()


@pytest.mark.django_db
def test_marketing_switch_does_not_mute_personal_message(cargo_admin_client, my_client):
    """Личное сообщение — не реклама: тумблер «рекламные» его не глушит."""
    from notifications.services import get_or_create_preference

    prefs = get_or_create_preference(my_client)
    prefs.marketing_enabled = False
    prefs.save()

    cargo_admin_client.post(
        URL,
        {"clients": [my_client.id], "title": "Личное", "body": "Текст"},
        format="json",
    )
    assert Notification.objects.filter(user=my_client, title="Личное").exists()


# --- границы ---


@pytest.mark.django_db
def test_foreign_cargo_client_is_refused(cargo_admin_client, db):
    from tests.factories import CargoCompanyFactory

    stranger = UserFactory(cargo=CargoCompanyFactory())
    r = cargo_admin_client.post(
        URL,
        {"clients": [stranger.id], "title": "Чужому", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 400
    assert Notification.objects.filter(user=stranger, title="Чужому").count() == 0


@pytest.mark.django_db
def test_bound_operator_cannot_write_outside_own_pickup(api_client, cargo_admin):
    """Привязанный оператор пишет только клиентам своего пункта."""
    from rest_framework_simplejwt.tokens import RefreshToken

    other_point = PickupPointFactory(cargo=cargo_admin.cargo)
    outsider = UserFactory(cargo=cargo_admin.cargo, pickup_point=other_point)
    operator = UserFactory(
        cargo=cargo_admin.cargo, pickup_point=cargo_admin.pickup_point, is_staff=True
    )
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(operator).access_token}"
    )

    r = api_client.post(
        URL,
        {"clients": [outsider.id], "title": "Мимо", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 400
    assert Notification.objects.filter(user=outsider, title="Мимо").count() == 0


@pytest.mark.django_db
def test_unknown_code_is_reported_but_others_are_delivered(cargo_admin_client, my_client):
    r = cargo_admin_client.post(
        URL,
        {
            "client_codes": ["ISI-0106", "НЕТ-ТАКОГО"],
            "title": "Половина",
            "body": "Текст",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["recipients_count"] == 1
    assert r.data["not_found"] == ["НЕТ-ТАКОГО"]
    assert Notification.objects.filter(user=my_client).exists()


@pytest.mark.django_db
def test_staff_are_not_valid_recipients(cargo_admin_client, cargo_admin):
    """Сотрудник — не клиент: рассылка по ПВЗ его тоже исключает."""
    colleague = UserFactory(
        cargo=cargo_admin.cargo, pickup_point=cargo_admin.pickup_point, is_staff=True
    )
    r = cargo_admin_client.post(
        URL,
        {"clients": [colleague.id], "title": "Коллеге", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_empty_recipients_is_rejected(cargo_admin_client):
    r = cargo_admin_client.post(
        URL, {"clients": [], "title": "Никому", "body": "Текст"}, format="json"
    )
    assert r.status_code == 400
    assert Notification.objects.filter(title="Никому").count() == 0


@pytest.mark.django_db
def test_client_cannot_send(auth_client, user):
    r = auth_client.post(
        URL, {"clients": [user.id], "title": "Себе", "body": "Текст"}, format="json"
    )
    assert r.status_code == 403


@pytest.mark.django_db
def test_anonymous_cannot_send(api_client, db):
    r = api_client.post(URL, {"clients": [1], "title": "X", "body": "Y"}, format="json")
    assert r.status_code == 401


# --- не мешается с рассылками ---


@pytest.mark.django_db
def test_personal_message_is_not_listed_as_broadcast(cargo_admin_client, my_client):
    """Список рассылок — про рассылки. Личное письмо там только мешает."""
    cargo_admin_client.post(
        URL, {"clients": [my_client.id], "title": "Личное", "body": "Текст"}, format="json"
    )
    r = cargo_admin_client.get("/api/manage/notifications/")
    assert [row["title"] for row in r.data] == []


@pytest.mark.django_db
def test_deleting_broadcast_keeps_personal_message(cargo_admin_client, my_client):
    """Удаление рассылки ищет по заголовку и тексту — личное под раздачу не идёт."""
    cargo_admin_client.post(
        "/api/manage/notifications/",
        {"title": "Совпало", "body": "Текст"},
        format="json",
    )
    cargo_admin_client.post(
        URL, {"clients": [my_client.id], "title": "Совпало", "body": "Текст"}, format="json"
    )
    personal = Notification.objects.get(type=NotificationType.PERSONAL)

    listed = cargo_admin_client.get("/api/manage/notifications/").data
    assert len(listed) == 1
    cargo_admin_client.delete(f"/api/manage/notifications/{listed[0]['id']}/")

    assert Notification.objects.filter(pk=personal.pk).exists()


@pytest.mark.django_db
def test_all_codes_unknown_is_rejected(cargo_admin_client, my_client):
    """Отправка в пустоту — ошибка оператора, а не успешный запрос."""
    r = cargo_admin_client.post(
        URL,
        {"client_codes": ["НЕТ-1", "НЕТ-2"], "title": "В пустоту", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["not_found"] == ["НЕТ-1", "НЕТ-2"]
    assert Notification.objects.filter(title="В пустоту").count() == 0


@pytest.mark.django_db
def test_blank_codes_are_ignored_not_counted(cargo_admin_client, my_client):
    """Пустые строки в списке кодов — мусор из формы, а не промах."""
    r = cargo_admin_client.post(
        URL,
        {"client_codes": ["ISI-0106", "", "  "], "title": "Чисто", "body": "Текст"},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["recipients_count"] == 1
    assert r.data["not_found"] == []
