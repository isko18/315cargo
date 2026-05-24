import logging

from .models import AuditLog

logger = logging.getLogger("cargo.audit")


def _client_ip(request):
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _user_agent(request):
    if not request:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:512]


def log_audit(
    action,
    *,
    actor=None,
    target_user=None,
    description="",
    metadata=None,
    request=None,
):
    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    try:
        record = AuditLog.objects.create(
            actor=actor,
            target_user=target_user,
            action=action,
            description=description or "",
            metadata=metadata or {},
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:
        logger.exception("Failed to write audit log for action %s", action)
        return None
    logger.info(
        "audit %s actor=%s target=%s",
        action,
        actor.id if actor else None,
        target_user.id if target_user else None,
    )
    return record
