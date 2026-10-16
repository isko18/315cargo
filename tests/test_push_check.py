"""Разбор «не пришёл пуш» по конкретному клиенту.

Команда ценна вердиктом: снаружи «нет пуша» выглядит одинаково, а лечится
по-разному — у одного выключены уведомления, у другого мёртвый токен, у
третьего с сервера всё ушло и искать надо на телефоне. Тесты держат именно
то, что команда различает эти случаи.

FCM подменяем: настоящий dry_run ходит в Google.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from notifications.management.commands import push_check
from notifications.models import DeviceToken
from notifications.services import get_or_create_preference
from tests.factories import UserFactory


@pytest.fixture(autouse=True)
def fake_fcm(monkeypatch):
    """dead — токены, которые FCM признаёт мёртвыми."""
    dead = set()
    monkeypatch.setattr(push_check, "_ensure_firebase_initialized", lambda: True)
    monkeypatch.setattr(
        push_check,
        "dry_run",
        lambda tokens: {t: ("NotRegistered" if t in dead else None) for t in tokens},
    )
    return dead


def run(*args, **kwargs):
    out = StringIO()
    call_command("push_check", *args, stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_healthy_client_points_to_the_phone(cargo):
    client = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=client, token="tok-live", platform="android")

    out = run(client.phone)

    assert "рабочий" in out
    assert "искать на телефоне" in out


@pytest.mark.django_db
def test_found_by_client_code_too(cargo):
    client = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=client, token="tok-code", platform="ios")

    out = run(client.client_code.lower())

    assert client.phone in out


@pytest.mark.django_db
def test_push_disabled_by_client(cargo):
    client = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=client, token="tok-off", platform="android")
    pref = get_or_create_preference(client)
    pref.push_enabled = False
    pref.save(update_fields=["push_enabled"])

    assert "сам выключил пуши" in run(client.phone)


@pytest.mark.django_db
def test_parcel_statuses_disabled(cargo):
    """Хитрый случай: нет даже записи в приложении, не только пуша."""
    client = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=client, token="tok-st", platform="android")
    pref = get_or_create_preference(client)
    pref.parcel_status_enabled = False
    pref.save(update_fields=["parcel_status_enabled"])

    assert "статусы посылок" in run(client.phone)


@pytest.mark.django_db
def test_never_registered_device(cargo):
    client = UserFactory(cargo=cargo)

    assert "ни разу не зарегистрировано" in run(client.phone)


@pytest.mark.django_db
def test_all_tokens_dead(cargo, fake_fcm):
    client = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=client, token="tok-dead", platform="ios")
    fake_fcm.add("tok-dead")

    out = run(client.phone)

    assert "МЁРТВЫЙ" in out
    assert "выйти и войти заново" in out


@pytest.mark.django_db
def test_unknown_client():
    assert "не найден" in run("+996000000000")


@pytest.mark.django_db
def test_summary_lists_clients_push_will_not_reach(cargo, fake_fcm):
    from notifications.models import Notification, NotificationType

    reachable = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=reachable, token="tok-ok", platform="android")
    lost = UserFactory(cargo=cargo)
    DeviceToken.objects.create(user=lost, token="tok-gone", platform="ios")
    fake_fcm.add("tok-gone")
    for user in (reachable, lost):
        Notification.objects.create(
            user=user, title="Посылка в ПВЗ", body="...",
            type=NotificationType.PARCEL_AT_PICKUP_POINT,
        )

    out = run(days=3)

    assert "клиентов 2" in out
    assert "с рабочим токеном: 1" in out
    assert lost.phone in out
    assert reachable.phone not in out.split("пуш не дойдёт")[1]
