"""Ссылки-приглашения карго: /j/<slug> и файлы верификации доменов.

Клиент переходит по ссылке карго → ОС открывает приложение с уже выбранным
карго. Чтобы ОС перехватывала ссылку, домен должен отдавать два файла:

* Android — ``/.well-known/assetlinks.json``
* iOS — ``/.well-known/apple-app-site-association`` (без расширения!)

Оба обязаны отдаваться по HTTPS, кодом ровно 200, с ``application/json`` и
**без редиректов** — иначе верификация домена молча не проходит.

Если приложение не установлено (или домен ещё не верифицирован), открывается
страница ``/j/<slug>`` с кнопкой перехода по схеме ``cargo315://`` и ссылками
на магазины.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control

from cargo.models import CargoCompany

WELL_KNOWN_DIR = Path(__file__).resolve().parent / "well_known"


@lru_cache(maxsize=4)
def _read_well_known(filename: str) -> str:
    return (WELL_KNOWN_DIR / filename).read_text(encoding="utf-8")


def _json_file_response(filename: str) -> HttpResponse:
    # Content-Type обязателен для обоих файлов, у AASA — тоже application/json.
    response = HttpResponse(
        _read_well_known(filename), content_type="application/json"
    )
    # ОС перечитывает файлы редко; сутки — безопасный компромисс.
    response["Cache-Control"] = "public, max-age=86400"
    return response


@cache_control(max_age=86400, public=True)
def assetlinks(request):
    """``/.well-known/assetlinks.json`` — Android App Links."""
    return _json_file_response("assetlinks.json")


@cache_control(max_age=86400, public=True)
def apple_app_site_association(request):
    """``/.well-known/apple-app-site-association`` — iOS Universal Links."""
    return _json_file_response("apple-app-site-association")


def invite_url_for(slug: str) -> str:
    """Готовая ссылка-приглашение карго — одна точка правды для панели и страницы."""
    return f"{settings.INVITE_LINK_BASE_URL}/j/{slug}"


def app_link_for(slug: str) -> str:
    """Ссылка по собственной схеме приложения (работает без верификации домена)."""
    return f"{settings.MOBILE_APP_SCHEME}://join/{slug}"


def cargo_invite(request, slug):
    """Страница-заглушка ``/j/<slug>``.

    Открывается, только если ссылку не перехватило приложение: десктоп,
    приложение не установлено, домен ещё не верифицирован.
    """
    cargo = CargoCompany.objects.filter(slug__iexact=slug, is_active=True).first()
    if cargo is None:
        return render(
            request,
            "invites/not_found.html",
            {"slug": slug, "site_url": settings.INVITE_LINK_BASE_URL},
            status=404,
        )

    play_url = (
        "https://play.google.com/store/apps/details"
        f"?id={settings.ANDROID_PACKAGE_NAME}&referrer=cargo%3D{cargo.slug}"
    )
    return render(
        request,
        "invites/cargo.html",
        {
            "cargo": cargo,
            # Код для ручного ввода в приложении — это slug, регистр не важен.
            "cargo_code": cargo.slug.upper(),
            "app_link": app_link_for(cargo.slug),
            "play_url": play_url,
            "app_store_url": settings.APP_STORE_URL,
        },
    )
