"""Страница привязки WhatsApp: QR и состояние сессии шлюза.

Шлюз WAHA намеренно слушает только localhost — наружу он отдал бы весь свой
админский API. Поэтому наружу выведена одна страница под авторизацией Django,
а в шлюз ходит сервер: браузер получает только картинку QR и статус.

Временная страница, живёт ровно столько, сколько self-hosted шлюз: с переходом
на Meta Cloud API привязка по QR исчезает вместе с ней.
"""

import logging

import requests
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

TIMEOUT = 20


def _require_superuser(request):
    # Привязка номера — действие уровня владельца, а не любого сотрудника.
    if not request.user.is_superuser:
        raise PermissionDenied("Только владелец может привязывать WhatsApp")


def _waha(path, method="get", **kwargs):
    base = (settings.WHATSAPP_API_URL or "").rstrip("/")
    if not base:
        raise RuntimeError("WHATSAPP_API_URL не задан")
    headers = {"X-Api-Key": settings.WHATSAPP_API_KEY} if settings.WHATSAPP_API_KEY else {}
    return requests.request(
        method, f"{base}{path}", headers=headers, timeout=TIMEOUT, **kwargs
    )


@staff_member_required
def qr_page(request):
    _require_superuser(request)
    return render(
        request,
        "waha/qr.html",
        {
            "session": settings.WHATSAPP_SESSION,
            "configured": bool(settings.WHATSAPP_API_URL),
            "channels": settings.OTP_CHANNELS,
        },
    )


@staff_member_required
def qr_status(request):
    """Состояние сессии для опроса со страницы."""
    _require_superuser(request)
    try:
        response = _waha(f"/api/sessions/{settings.WHATSAPP_SESSION}")
    except Exception as exc:  # шлюз не поднят — страница должна это показать
        logger.warning("WAHA status failed: %s", exc)
        return JsonResponse({"status": "GATEWAY_DOWN", "detail": str(exc)}, status=200)

    if response.status_code == 404:
        return JsonResponse({"status": "NO_SESSION"})
    if response.status_code >= 400:
        return JsonResponse(
            {"status": "ERROR", "detail": response.text[:300]}, status=200
        )

    data = response.json()
    me = data.get("me") or {}
    return JsonResponse(
        {
            "status": data.get("status", "UNKNOWN"),
            "phone": me.get("id", "").split("@")[0] if me.get("id") else "",
            "name": me.get("pushName", ""),
        }
    )


@staff_member_required
def qr_image(request):
    """Прокси картинки QR. Живёт ~20 секунд, страница сама перезапрашивает."""
    _require_superuser(request)
    try:
        response = _waha(
            f"/api/{settings.WHATSAPP_SESSION}/auth/qr", params={"format": "image"}
        )
    except Exception as exc:
        logger.warning("WAHA QR failed: %s", exc)
        return HttpResponse(status=503)

    if response.status_code >= 400:
        # Уже привязано либо сессия не в том состоянии — не ошибка страницы.
        return HttpResponse(status=409)

    return HttpResponse(
        response.content,
        content_type=response.headers.get("Content-Type", "image/png"),
        headers={"Cache-Control": "no-store"},
    )


@staff_member_required
@require_POST
def session_restart(request):
    """Перезапуск сессии — иначе при её падении пришлось бы лезть по SSH."""
    _require_superuser(request)
    name = settings.WHATSAPP_SESSION
    try:
        response = _waha(f"/api/sessions/{name}/restart", method="post")
        if response.status_code == 404:
            # Сессии ещё нет — создаём.
            response = _waha(
                "/api/sessions", method="post", json={"name": name, "start": True}
            )
    except Exception as exc:
        logger.warning("WAHA restart failed: %s", exc)
        return JsonResponse({"ok": False, "detail": str(exc)}, status=200)

    return JsonResponse({"ok": response.status_code < 400, "code": response.status_code})
