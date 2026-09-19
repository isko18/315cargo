"""Рассылка уведомлений клиентам из панели.

В клиентском API уведомления только читаются. Здесь — создание: сотрудник
пишет текст, выбирает склады (пусто — всем клиентам карго) и рассылает.

Рассылка идёт по клиентам своего карго: notify() сам уважает настройки
клиента, поэтому отключивший пуши получит запись в списке, но не получит
push — это правильно и менять не надо.
"""

import posixpath

from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.cargo_scoping import bound_pickup_id, get_request_cargo_id
from common.permissions import IsCargoManager
from pickup_points.models import PickupPoint
from users.models import User

from .models import Notification, NotificationType
from .services import notify_many


class BroadcastSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    body = serializers.CharField()
    # Пусто — всем клиентам карго. Иначе только клиентам этих ПВЗ.
    pickup_points = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.all(), many=True, required=False
    )
    send_push = serializers.BooleanField(default=True)
    # multipart: картинка к уведомлению. JSON-запросы продолжают работать —
    # поле необязательное.
    image = serializers.ImageField(required=False, allow_null=True)


class BroadcastListSerializer(serializers.Serializer):
    """Что уже разослано: рассылки группируются по заголовку и времени."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()
    recipients_count = serializers.IntegerField()
    image = serializers.CharField(allow_null=True, required=False)


@extend_schema_view(
    list=extend_schema(tags=["manage"], responses=BroadcastListSerializer(many=True)),
    create=extend_schema(tags=["manage"], request=BroadcastSerializer, responses={201: dict}),
    destroy=extend_schema(tags=["manage"], responses={204: None}),
)
class ManagedNotificationViewSet(GenericViewSet):
    """Создание и просмотр рассылок по клиентам карго."""

    permission_classes = (IsAuthenticated, IsCargoManager)
    serializer_class = BroadcastSerializer
    # Картинка приходит файлом, значит форма; JSON оставляем — им шлёт панель.
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    queryset = Notification.objects.none()

    def _recipients(self, pickup_points=None):
        """Клиенты карго, которым адресована рассылка."""
        qs = User.objects.filter(is_staff=False, is_superuser=False)
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(cargo_id=cargo_id)
        # Привязанный оператор рассылает только своему ПВЗ, даже если попросил
        # шире — иначе он достанет клиентов чужих пунктов.
        bound = bound_pickup_id(self.request.user)
        if bound:
            return qs.filter(pickup_point_id=bound)
        if pickup_points:
            qs = qs.filter(pickup_point__in=pickup_points)
        return qs

    def _sent_queryset(self):
        """Разосланное этим карго — по тем же клиентам, что и видит панель."""
        return Notification.objects.filter(
            user__in=self._recipients(), type=NotificationType.SYSTEM
        )

    def list(self, request):
        # Рассылка — это N одинаковых уведомлений, по одному на клиента.
        # Схлопываем их в строки «что и когда отправили».
        from django.db.models import Count, Min

        rows = (
            self._sent_queryset()
            .values("title", "body")
            # Считаем по user_id: алиас id перекрывает поле, и Count("id")
            # тогда считал бы уже агрегат.
            .annotate(
                id=Min("id"),
                created_at=Min("created_at"),
                recipients_count=Count("user_id"),
                image=Min("image"),
            )
            .order_by("-created_at")[:100]
        )
        return Response(BroadcastListSerializer(rows, many=True).data)

    def create(self, request):
        serializer = BroadcastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        points = data.get("pickup_points") or []
        cargo_id = get_request_cargo_id(request.user)
        for point in points:
            # ПВЗ чужого карго означал бы рассылку чужим клиентам.
            if cargo_id and point.cargo_id != cargo_id:
                return Response(
                    {"detail": "Пункт выдачи принадлежит другому карго"}, status=400
                )

        recipients = list(self._recipients(points))

        # Файл сохраняем один раз и раздаём остальным строкам путём: рассылка —
        # это N одинаковых уведомлений, и файл в каждом дал бы N копий картинки
        # в хранилище.
        image_name = None
        upload = data.get("image")
        if upload is not None:
            storage = Notification.image.field.storage
            # Путь собираем через posixpath, а не generate_filename(): тот на
            # Windows вернёт «notifications\файл.png», и ссылка не откроется.
            image_name = storage.save(
                posixpath.join("notifications", storage.get_valid_name(upload.name)), upload
            )

        with transaction.atomic():
            count = notify_many(
                recipients,
                data["title"],
                data["body"],
                type=NotificationType.SYSTEM,
                push=data["send_push"],
                image=image_name,
            )
        first = (
            Notification.objects.filter(user__in=recipients, title=data["title"])
            .order_by("-created_at")
            .first()
        )
        return Response({"id": first.id if first else None, "recipients_count": count}, status=201)

    def destroy(self, request, pk=None):
        """Удаляет всю рассылку, а не одну её копию.

        Уведомление создаётся по штуке на клиента, поэтому удаление одного id
        оставило бы остальных с тем же текстом в списке.
        """
        target = self._sent_queryset().filter(pk=pk).first()
        if target is None:
            return Response({"detail": "Рассылка не найдена"}, status=404)

        rows = self._sent_queryset().filter(title=target.title, body=target.body)
        # Картинку убираем вместе с рассылкой: имя файла уникально на рассылку
        # (storage.save разводит одноимённые), поэтому после удаления строк на
        # неё уже никто не сошлётся, а в хранилище она осталась бы навсегда.
        image_name = target.image.name
        rows.delete()
        if image_name:
            target.image.storage.delete(image_name)
        return Response(status=204)
