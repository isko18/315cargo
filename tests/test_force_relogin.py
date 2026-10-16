"""Принудительный выход клиентов, у которых не осталось ни одного рабочего push-токена.

Приложение присылает токен только при входе. Токен меняется при обновлении или
переустановке, а сессия остаётся — новый токен до сервера не доходит, и push
перестаёт приходить молча. На проде так 97 клиентов. Пока приложение не начнёт
слать токен при каждом запуске, вылечить их можно только повторным входом —
поэтому аннулируем им сессию: приложение при обновлении токена доступа получит
отказ, выкинет на вход, а вход зарегистрирует свежий токен.

Главные риски здесь — выкинуть не того: оператора посреди смены или клиента,
чей токен на самом деле жив, а FCM просто ответил временной ошибкой.
"""

import pytest
from django.core.management import call_command
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.models import DeviceToken
from tests.factories import UserFactory

ALIVE, DEAD, UNKNOWN = True, False, None


@pytest.fixture
def fcm(monkeypatch, settings):
    """Подменяем проверку в FCM: tokens → {token: True|False|None}."""
    # Фабрика выдаёт номера с +996700000000, а он по умолчанию тестовый —
    # команда законно его пропускает. Тест про тестовые номера задаёт свои.
    settings.OTP_TEST_NUMBERS = {}
    verdicts = {}

    def fake_probe(tokens):
        return {t: verdicts.get(t, ALIVE) for t in tokens}

    monkeypatch.setattr("notifications.services.probe_tokens", fake_probe)
    return verdicts


def _client(**kwargs):
    user = UserFactory(**kwargs)
    DeviceToken.objects.filter(user=user).delete()
    return user


def _token(user, token, platform="ios"):
    return DeviceToken.objects.create(user=user, token=token, platform=platform)


def _blacklisted(refresh):
    return BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()


# --- кого выкидываем ---


@pytest.mark.django_db
def test_client_with_only_dead_tokens_is_logged_out(fcm):
    user = _client()
    _token(user, "dead-1")
    fcm["dead-1"] = DEAD
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert _blacklisted(refresh)


@pytest.mark.django_db
def test_old_session_really_stops_working(fcm, api_client):
    """Не просто запись в чёрном списке — приложение действительно получит отказ."""
    user = _client()
    _token(user, "dead-1")
    fcm["dead-1"] = DEAD
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    r = api_client.post("/api/auth/refresh/", {"refresh": str(refresh)}, format="json")
    assert r.status_code == 401


@pytest.mark.django_db
def test_dead_tokens_are_deactivated(fcm):
    user = _client()
    token = _token(user, "dead-1")
    fcm["dead-1"] = DEAD

    call_command("force_relogin_dead_push", "--apply")

    token.refresh_from_db()
    assert token.is_active is False


@pytest.mark.django_db
def test_relogin_after_logout_registers_fresh_token(fcm, api_client):
    """Ради этого всё и делается: после повторного входа токен снова живой."""
    user = _client()
    _token(user, "dead-1")
    fcm["dead-1"] = DEAD
    call_command("force_relogin_dead_push", "--apply")

    fresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {fresh.access_token}")
    r = api_client.post(
        "/api/device-tokens/", {"token": "fresh-1", "platform": "ios"}, format="json"
    )
    assert r.status_code == 201
    assert DeviceToken.objects.get(token="fresh-1").is_active is True


# --- кого не трогаем ---


@pytest.mark.django_db
def test_client_with_one_live_token_is_left_alone(fcm):
    """Хотя бы одно устройство получает push — выкидывать незачем."""
    user = _client()
    _token(user, "dead-1")
    _token(user, "alive-1", platform="android")
    fcm["dead-1"] = DEAD
    fcm["alive-1"] = ALIVE
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert not _blacklisted(refresh)


@pytest.mark.django_db
def test_transient_fcm_error_never_logs_anyone_out(fcm):
    """FCM недоступен — это не повод выкидывать человека из приложения."""
    user = _client()
    _token(user, "flaky-1")
    fcm["flaky-1"] = UNKNOWN
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert not _blacklisted(refresh)
    assert DeviceToken.objects.get(token="flaky-1").is_active is True


@pytest.mark.django_db
def test_staff_is_never_logged_out(fcm):
    """Приложение у сотрудников и клиентов одно — оператора посреди смены не трогаем."""
    for flags in ({"is_staff": True}, {"is_cargo_admin": True}, {"is_china_staff": True}):
        user = _client(**flags)
        _token(user, f"dead-{user.id}")
        fcm[f"dead-{user.id}"] = DEAD
        refresh = RefreshToken.for_user(user)

        call_command("force_relogin_dead_push", "--apply")

        assert not _blacklisted(refresh), flags


@pytest.mark.django_db
def test_test_accounts_are_left_alone(fcm, settings):
    """Тестовые номера ревьюеров и мобильной команды не выкидываем."""
    user = _client(phone="+996999000316")
    settings.OTP_TEST_NUMBERS = {"+996999000316": "0000"}
    _token(user, "dead-1")
    fcm["dead-1"] = DEAD
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert not _blacklisted(refresh)


@pytest.mark.django_db
def test_dry_run_changes_nothing(fcm):
    user = _client()
    token = _token(user, "dead-1")
    fcm["dead-1"] = DEAD
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push")

    assert not _blacklisted(refresh)
    token.refresh_from_db()
    assert token.is_active is True


# --- проверка в FCM ---


@pytest.mark.django_db
def test_probe_classifies_fcm_answers(monkeypatch):
    """Живой, мёртвый навсегда и «не понять» — три разных исхода, не два."""
    from firebase_admin import exceptions as fb_exceptions
    from firebase_admin import messaging

    from notifications.services import probe_tokens

    class _R:
        def __init__(self, exc=None):
            self.success = exc is None
            self.exception = exc

    def fake_send_each(messages, dry_run=False):
        assert dry_run is True, "проверка не должна ничего доставлять"

        class _Resp:
            responses = [
                _R(),
                _R(messaging.UnregisteredError("gone")),
                _R(fb_exceptions.UnavailableError("later", cause=None)),
            ]

        return _Resp()

    monkeypatch.setattr("notifications.services._ensure_firebase_initialized", lambda: True)
    monkeypatch.setattr(messaging, "send_each", fake_send_each)

    assert probe_tokens(["a", "b", "c"]) == {"a": True, "b": False, "c": None}


# --- токены уже погашены сервером ---


@pytest.mark.django_db
def test_client_whose_tokens_server_already_deactivated_is_logged_out(fcm):
    """Самый частый случай, и раньше команда его не видела.

    Сервер сам гасит токен, получив NotRegistered при обычной отправке. Клиент
    остаётся в приложении без единого активного токена, пуши не уходят вовсе.
    """
    user = _client()
    DeviceToken.objects.create(user=user, token="gone", platform="ios", is_active=False)
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert _blacklisted(refresh)


@pytest.mark.django_db
def test_already_logged_out_client_is_left_alone(fcm):
    """Без живой сессии делать нечего: при входе токен и так зарегистрируется."""
    from common.models import AuditLog

    user = _client()
    DeviceToken.objects.create(user=user, token="gone", platform="ios", is_active=False)
    refresh = RefreshToken.for_user(user)
    refresh.blacklist()  # клиент уже вышел сам

    call_command("force_relogin_dead_push", "--apply")

    assert not AuditLog.objects.filter(target_user=user).exists()


@pytest.mark.django_db
def test_client_who_never_registered_a_device_is_not_kicked_every_night(fcm):
    """Без токена в истории вход ничего не даст — скорее всего, не дал разрешение."""
    user = _client()
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert not _blacklisted(refresh)


@pytest.mark.django_db
def test_deleted_account_is_not_touched(fcm):
    user = _client()
    user.phone = f"deleted-{user.id}"
    user.is_active = False
    user.save(update_fields=["phone", "is_active"])
    _token(user, "dead-del")
    fcm["dead-del"] = DEAD
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert not _blacklisted(refresh)


@pytest.mark.django_db
def test_client_with_one_live_token_among_dead_ones_stays(fcm):
    user = _client()
    DeviceToken.objects.create(user=user, token="old", platform="ios", is_active=False)
    _token(user, "live")
    refresh = RefreshToken.for_user(user)

    call_command("force_relogin_dead_push", "--apply")

    assert not _blacklisted(refresh)
