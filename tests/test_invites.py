"""Ссылки-приглашения карго: /j/<slug> и файлы верификации доменов."""

import json

import pytest
from django.urls import reverse

from common.invites import play_store_url_for
from tests.factories import CargoCompanyFactory


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    ["/.well-known/assetlinks.json", "/.well-known/apple-app-site-association"],
)
def test_well_known_files_are_json_200_without_redirect(client, url):
    """ОС не верифицирует домен, если код не 200 или тип не application/json."""
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    json.loads(response.content)  # валидный JSON


@pytest.mark.django_db
def test_assetlinks_declares_android_package():
    from common.invites import _read_well_known

    data = json.loads(_read_well_known("assetlinks.json"))
    assert data[0]["target"]["package_name"] == "com.cargo315.app"
    assert data[0]["relation"] == ["delegate_permission/common.handle_all_urls"]
    # Два отпечатка: App signing key (Play) и Upload key (локальные сборки).
    assert len(data[0]["target"]["sha256_cert_fingerprints"]) == 2


@pytest.mark.django_db
def test_aasa_covers_invite_path():
    from common.invites import _read_well_known

    data = json.loads(_read_well_known("apple-app-site-association"))
    detail = data["applinks"]["details"][0]
    assert detail["appIDs"] == ["Y37HNJ3WU3.com.cargo315.app"]
    assert detail["components"][0]["/"] == "/j/*"


@pytest.mark.django_db
def test_invite_page_shows_cargo(client):
    cargo = CargoCompanyFactory(title="315CARGO Ош", slug="315cargo-osh")

    response = client.get(f"/j/{cargo.slug}")
    assert response.status_code == 200
    body = response.content.decode()
    assert "315CARGO Ош" in body
    assert "315CARGO-OSH" in body  # код для ручного ввода
    assert "cargo315://join/315cargo-osh" in body  # кнопка «Открыть в приложении»
    assert "play.google.com" in body


@pytest.mark.django_db
def test_invite_page_is_case_insensitive(client):
    cargo = CargoCompanyFactory(slug="cargo-case")
    assert client.get(f"/j/{cargo.slug.upper()}").status_code == 200


@pytest.mark.django_db
def test_invite_page_trailing_slash_works(client):
    cargo = CargoCompanyFactory(slug="cargo-slash")
    assert client.get(f"/j/{cargo.slug}/").status_code == 200


@pytest.mark.django_db
def test_unknown_slug_returns_404_page(client):
    response = client.get("/j/no-such-cargo")
    assert response.status_code == 404
    assert "Такого карго нет" in response.content.decode()


@pytest.mark.django_db
def test_inactive_cargo_is_not_shown(client):
    cargo = CargoCompanyFactory(slug="cargo-off", is_active=False)
    assert client.get(f"/j/{cargo.slug}").status_code == 404


@pytest.mark.django_db
def test_owner_sees_invite_link_and_qr(cargo_admin_client, cargo):
    response = cargo_admin_client.get("/api/manage/cargo/")
    assert response.status_code == 200
    assert response.data["invite_url"].endswith(f"/j/{cargo.slug}")
    assert response.data["invite_qr"].startswith("data:image/png;base64,")


@pytest.mark.django_db
def test_super_owner_sees_invite_link(superuser_client, cargo):
    response = superuser_client.get(f"/api/admin/cargos/{cargo.id}/")
    assert response.status_code == 200
    assert response.data["invite_url"].endswith(f"/j/{cargo.slug}")
    assert response.data["invite_qr"].startswith("data:image/png;base64,")


@pytest.mark.django_db
def test_invite_url_uses_configured_domain(settings):
    from common.invites import invite_url_for

    settings.INVITE_LINK_BASE_URL = "https://315cargo.com"
    assert invite_url_for("315cargo") == "https://315cargo.com/j/315cargo"


# --- Install Referrer: подстановка карго после установки из Play Market ---
# Вся механика держится на одном параметре в ссылке на Play. Если он пропадёт
# или потеряет кодирование, сценарий сломается молча: страница откроется, кнопка
# будет работать, а карго после установки просто не подставится.


@pytest.mark.django_db
def test_play_url_carries_encoded_referrer():
    from common.invites import play_store_url_for

    url = play_store_url_for("315cargo-osh")
    assert "&referrer=cargo%3D315cargo-osh" in url
    # Незакодированный `=` внутри значения Play Market обрезал бы по нему.
    assert "referrer=cargo=" not in url


@pytest.mark.django_db
def test_play_url_has_exactly_two_equals_signs():
    """Проверка из инструкции: `=` только после `id` и после `referrer`."""
    from common.invites import play_store_url_for

    assert play_store_url_for("osh").count("=") == 2


@pytest.mark.django_db
def test_play_url_has_no_pcampaignid():
    """`pcampaignid` прилипает к ссылке из кнопки «Поделиться» в Play Market."""
    from common.invites import play_store_url_for

    assert "pcampaignid" not in play_store_url_for("osh")


@pytest.mark.django_db
def test_invite_page_play_button_has_referrer(client):
    """Страница должна отдавать ссылку с referrer, а не голый листинг."""
    cargo = CargoCompanyFactory(slug="referrer-page")

    body = client.get(f"/j/{cargo.slug}").content.decode()
    # В HTML `&` экранирован — сравниваем с той же заменой.
    assert "&amp;referrer=cargo%3Dreferrer-page" in body


@pytest.mark.django_db
def test_invite_page_shows_cargo_code_as_ios_fallback(client):
    """Запасной путь: на iOS автоподстановки нет, код вводят руками."""
    cargo = CargoCompanyFactory(slug="ios-fallback")

    body = client.get(f"/j/{cargo.slug}").content.decode()
    assert "IOS-FALLBACK" in body


@pytest.mark.django_db
def test_owner_sees_play_url_with_referrer(cargo_admin_client, cargo):
    """Админка не может показать ссылку, которой нет в ответе API."""
    response = cargo_admin_client.get("/api/manage/cargo/")
    assert response.status_code == 200
    assert response.data["play_url"] == play_store_url_for(cargo.slug)
    assert f"referrer=cargo%3D{cargo.slug}" in response.data["play_url"]


@pytest.mark.django_db
def test_super_owner_sees_play_url_with_referrer(superuser_client, cargo):
    response = superuser_client.get(f"/api/admin/cargos/{cargo.id}/")
    assert response.status_code == 200
    assert response.data["play_url"] == play_store_url_for(cargo.slug)
