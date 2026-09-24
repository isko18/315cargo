"""Управление посылками из панели (веб и мобильная).

Отдельный модуль, чтобы не смешивать с клиентским ParcelViewSet: у него другой
скоуп (клиент видит только свои посылки) и другой набор операций.

До этого правка посылки собиралась из трёх вызовов — assign/, weight/ и scan/.
Смена статуса через scan/ работает, но пишет лишнюю строку в историю приёмки:
операция выглядит так, будто коробку снова сканировали на складе.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.audit import log_audit
from common.cargo_scoping import bound_pickup_id, get_request_cargo_id
from common.models import AuditLog
from common.permissions import IsCargoManager
from pickup_points.models import PickupPoint

from .importers import (
    ImportFormatError,
    column_letter_to_index,
    detect_layout,
    extract_rows,
    read_rows,
)
from .models import Parcel, ParcelImport, ParcelStatusHistory
from .serializers import ParcelSerializer
from .services import (
    ScanError,
    apply_import_rows,
    calc_delivery_price,
    scan_parcel,
    update_parcel_status,
)

# Названы для мобильной команды, чтобы приложение не давало отправить заведомо
# неподъёмный файл. Реальные накладные — 200–500 строк и меньше мегабайта.
IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024
IMPORT_MAX_ROWS = 5000

# Оператору склада в Китае доступны только «китайские» статусы — та же логика,
# что уже стоит на scan/.
CHINA_STATUSES = (
    Parcel.Status.WAITING_CHINA_WAREHOUSE,
    Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    Parcel.Status.SENT_TO_KYRGYZSTAN,
)


class ParcelUpdateSerializer(serializers.Serializer):
    """Поля, которые панель правит в карточке товара."""

    status = serializers.ChoiceField(choices=Parcel.Status.choices, required=False)
    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    client_code = serializers.CharField(required=False, allow_blank=True)
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.all(), required=False, allow_null=True
    )
    location = serializers.CharField(required=False, allow_blank=True)

    # Карточка товара. Записываются как есть — считать по ним нечего, кроме
    # объёма, который пересчитывается ниже из габаритов.
    length_cm = serializers.DecimalField(
        max_digits=8, decimal_places=1, required=False, allow_null=True
    )
    width_cm = serializers.DecimalField(
        max_digits=8, decimal_places=1, required=False, allow_null=True
    )
    height_cm = serializers.DecimalField(
        max_digits=8, decimal_places=1, required=False, allow_null=True
    )
    payment_status = serializers.ChoiceField(
        choices=Parcel.PaymentStatus.choices, required=False
    )
    receipt_method = serializers.ChoiceField(
        choices=Parcel.ReceiptMethod.choices, required=False
    )
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    usd_rate = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, allow_null=True, min_value=0
    )
    client_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    crating = serializers.BooleanField(required=False)
    packaging = serializers.BooleanField(required=False)


# Поля карточки, которые кладутся в посылку без обработки.
PLAIN_FIELDS = (
    "length_cm",
    "width_cm",
    "height_cm",
    "payment_status",
    "receipt_method",
    "delivery_address",
    "usd_rate",
    "client_price",
    "crating",
    "packaging",
)


class BulkScanItemSerializer(serializers.Serializer):
    # allow_blank, чтобы пустой трек попал в построчные ошибки: иначе одна
    # пустая строка отвергала бы всю накладную на валидации.
    track_number = serializers.CharField(allow_blank=True)
    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    client_code = serializers.CharField(required=False, allow_blank=True)


class BulkScanSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Parcel.Status.choices)
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.all(), required=False, allow_null=True
    )
    items = BulkScanItemSerializer(many=True)


class BulkStatusSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField())
    status = serializers.ChoiceField(choices=Parcel.Status.choices)


class BulkScanErrorSerializer(serializers.Serializer):
    """Строка накладной, которая не прошла."""

    index = serializers.IntegerField(help_text="Позиция строки в присланном items.")
    track_number = serializers.CharField(allow_blank=True)
    error = serializers.CharField()


class ParcelImportSerializer(serializers.Serializer):
    """Запрос на импорт накладной файлом (multipart/form-data)."""

    file = serializers.FileField(help_text=".xlsx, .xls или .csv")
    # Импорт — точка входа посылки в систему, поэтому по умолчанию она встаёт
    # на склад в Китае: отсюда стартует авто-цепочка статусов. Любой другой
    # статус можно прислать явно — например когда коробку принимают в ПВЗ.
    status = serializers.ChoiceField(
        choices=Parcel.Status.choices,
        required=False,
        default=Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
        help_text=(
            "Статус для всех строк. По умолчанию «Прибыл на склад в Китае» — "
            "с него начинается авто-цепочка."
        ),
    )
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.all(),
        required=False,
        allow_null=True,
        help_text="Не передан — берётся ПВЗ сотрудника, как в scan/.",
    )
    start_row = serializers.IntegerField(
        required=False, min_value=1, help_text="Первая строка с данными, счёт с 1."
    )
    track_column = serializers.CharField(
        required=False, allow_blank=True, help_text="Буква колонки в терминах Excel: A, G, AA."
    )
    weight_column = serializers.CharField(required=False, allow_blank=True)
    client_code_column = serializers.CharField(required=False, allow_blank=True)
    dry_run = serializers.BooleanField(
        required=False, default=False, help_text="Только разобрать и проверить, не записывая."
    )


class ImportErrorSerializer(serializers.Serializer):
    """Строка, которая не прошла.

    ``row`` — номер строки в файле вместе с шапкой, счёт с 1: оператор идёт
    с ним в Excel. Порядковый номер в массиве (как index у bulk-scan/) для
    файла бесполезен.
    """

    row = serializers.IntegerField()
    track_number = serializers.CharField(allow_blank=True)
    error = serializers.CharField()


class ImportDetectedSerializer(serializers.Serializer):
    """Что распознано в файле — чтобы оператор увидел, та ли колонка взята."""

    start_row = serializers.IntegerField()
    track_column = serializers.CharField(allow_null=True)
    weight_column = serializers.CharField(allow_null=True)
    client_code_column = serializers.CharField(allow_null=True)


class ImportPreviewRowSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    track_number = serializers.CharField(allow_blank=True)
    weight = serializers.CharField(allow_blank=True)
    client_code = serializers.CharField(allow_blank=True)


class ParcelImportResultSerializer(serializers.Serializer):
    """Ответ import/.

    Инвариант: created + updated + skipped + len(errors) == total_rows.
    """

    file_name = serializers.CharField()
    total_rows = serializers.IntegerField()
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    skipped = serializers.IntegerField()
    errors = ImportErrorSerializer(many=True)
    detected = ImportDetectedSerializer()
    source_file = serializers.CharField(
        required=False, help_text="Ссылка на загруженный файл. Нет при dry_run."
    )
    preview = ImportPreviewRowSerializer(
        many=True, required=False, help_text="Первые 10 строк. Только при dry_run."
    )


class BulkScanResultSerializer(serializers.Serializer):
    """Ответ bulk-scan/.

    Схема нужна не для красоты: без неё приложение, не найдя errors, считало
    успешными все отправленные строки — и оператор не узнавал, что половина
    накладной не прошла.
    """

    created = serializers.IntegerField(help_text="Сколько посылок заведено впервые.")
    updated = serializers.IntegerField(help_text="Сколько уже существовало и обновлено.")
    errors = BulkScanErrorSerializer(many=True)


class BulkStatusErrorSerializer(serializers.Serializer):
    index = serializers.IntegerField(help_text="Позиция id в присланном ids.")
    id = serializers.IntegerField()
    error = serializers.CharField()


class BulkStatusResultSerializer(serializers.Serializer):
    """Ответ bulk-status/.

    updated считает только реально изменённые: посылка, уже стоявшая в этом
    статусе, не попадает ни в updated, ни в errors.
    """

    updated = serializers.IntegerField()
    errors = BulkStatusErrorSerializer(many=True)


@extend_schema_view(
    partial_update=extend_schema(
        tags=["manage"], request=ParcelUpdateSerializer, responses=ParcelSerializer
    ),
    bulk_scan=extend_schema(
        tags=["manage"],
        request=BulkScanSerializer,
        responses={200: BulkScanResultSerializer},
    ),
    bulk_status=extend_schema(
        tags=["manage"],
        request=BulkStatusSerializer,
        responses={200: BulkStatusResultSerializer},
    ),
    import_file=extend_schema(
        tags=["manage"],
        request={"multipart/form-data": ParcelImportSerializer},
        responses={200: ParcelImportResultSerializer},
        summary="Импорт накладной файлом (.xlsx / .xls / .csv)",
    ),
)
class ManagedParcelViewSet(GenericViewSet):
    """Правка посылок сотрудником: одиночная и пачкой."""

    permission_classes = (IsAuthenticated, IsCargoManager)
    serializer_class = ParcelUpdateSerializer
    queryset = Parcel.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Parcel.objects.none()
        qs = Parcel.objects.select_related("user", "pickup_point", "cargo", "order")
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(cargo_id=cargo_id)
        pickup_id = bound_pickup_id(self.request.user)
        if pickup_id:
            # Привязанный оператор правит только то, что лежит в его ПВЗ, либо
            # адресовано его клиентам (ещё не принято) — тот же охват, что и
            # в фильтре списка посылок.
            qs = qs.filter(
                Q(pickup_point_id=pickup_id)
                | Q(pickup_point__isnull=True, user__pickup_point_id=pickup_id)
            )
        return qs

    def _china_only(self):
        user = self.request.user
        return getattr(user, "is_china_staff", False) and not (
            getattr(user, "is_cargo_admin", False) or user.is_superuser
        )

    def _forbidden_status(self, status):
        if status and self._china_only() and status not in CHINA_STATUSES:
            return "Оператору склада в Китае доступны только статусы Китая"
        return None

    def partial_update(self, request, pk=None):
        parcel = self.get_queryset().filter(pk=pk).first()
        if parcel is None:
            return Response({"detail": "Посылка не найдена"}, status=404)

        serializer = ParcelUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        forbidden = self._forbidden_status(data.get("status"))
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        has_point = "pickup_point" in data
        point = data.get("pickup_point")
        if has_point and point is not None and point.cargo_id != parcel.cargo_id:
            # ПВЗ чужого карго сделал бы посылку невидимой для обеих сторон.
            return Response({"detail": "Пункт выдачи принадлежит другому карго"}, status=400)

        with transaction.atomic():
            fields = []
            if "client_code" in data:
                code = (data["client_code"] or "").strip()
                if code:
                    from users.models import User

                    client = User.objects.filter(
                        client_code__iexact=code, cargo_id=parcel.cargo_id
                    ).first()
                    if client is None:
                        return Response(
                            {"detail": "Клиент с кодом %s не найден" % code}, status=400
                        )
                    parcel.user = client
                    parcel.client_code = client.client_code
                    fields += ["user", "client_code"]

            if "weight" in data:
                parcel.weight = data["weight"]
                parcel.delivery_price = calc_delivery_price(parcel.cargo, data["weight"])
                fields += ["weight", "delivery_price"]

            if has_point:
                parcel.pickup_point = point
                fields.append("pickup_point")
                if point is not None:
                    parcel.location = point.address
                    fields.append("location")

            if "location" in data:
                parcel.location = data["location"]
                fields.append("location")

            for name in PLAIN_FIELDS:
                if name in data:
                    setattr(parcel, name, data[name])
                    fields.append(name)

            # Объём считаем сами: оператор меряет коробку, а не м³, и вводить
            # одно и то же двумя способами — источник расхождений.
            if {"length_cm", "width_cm", "height_cm"} & set(data):
                dims = (parcel.length_cm, parcel.width_cm, parcel.height_cm)
                if all(d for d in dims):
                    parcel.volume = (dims[0] * dims[1] * dims[2] / Decimal(1_000_000)).quantize(
                        Decimal("0.001")
                    )
                    fields.append("volume")

            if fields:
                parcel.save(update_fields=[*dict.fromkeys(fields), "updated_at"])

            # Статус меняем сервисом: он пишет историю и шлёт уведомление.
            if data.get("status") and data["status"] != parcel.status:
                update_parcel_status(parcel, data["status"], changed_by=request.user)

        parcel.refresh_from_db()
        return Response(ParcelSerializer(parcel).data)

    @action(detail=False, methods=("post",), url_path="bulk-scan")
    def bulk_scan(self, request):
        """Приём накладной пачкой.

        Семантика строки — как у scan/ (upsert по треку). Каждая строка в своей
        транзакции: одна плохая не должна отменять всю накладную.
        """
        serializer = BulkScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        forbidden = self._forbidden_status(data["status"])
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        china_only = self._china_only()
        cargo = None
        if not china_only:
            from cargo.models import CargoCompany

            cargo_id = get_request_cargo_id(request.user)
            cargo = CargoCompany.objects.filter(pk=cargo_id).first() if cargo_id else None
        point = data.get("pickup_point")

        created = 0
        updated = 0
        errors = []
        for index, item in enumerate(data["items"]):
            track = (item.get("track_number") or "").strip()
            if not track:
                errors.append({"index": index, "track_number": "", "error": "Пустой трек-номер"})
                continue
            try:
                with transaction.atomic():
                    result, _parcel = scan_parcel(
                        track,
                        cargo=cargo,
                        actor=request.user,
                        status=data["status"],
                        weight=item.get("weight"),
                        client_code=(item.get("client_code") or "").strip() or None,
                        pickup_point=point.id if point else None,
                        request=request,
                        global_resolve=china_only,
                    )
            except ScanError as exc:
                errors.append({"index": index, "track_number": track, "error": exc.message})
                continue
            except Exception as exc:  # неожиданная ошибка не должна рвать накладную
                errors.append({"index": index, "track_number": track, "error": str(exc)})
                continue
            if result in ("updated", "unchanged"):
                updated += 1
            else:
                created += 1

        return Response({"created": created, "updated": updated, "errors": errors})

    @action(detail=False, methods=("post",), url_path="bulk-status")
    def bulk_status(self, request):
        """Смена статуса посылкам, выделенным галочками в списке."""
        serializer = BulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        forbidden = self._forbidden_status(data["status"])
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        found = {p.id: p for p in self.get_queryset().filter(pk__in=data["ids"])}

        updated = 0
        errors = []
        for index, pid in enumerate(data["ids"]):
            parcel = found.get(pid)
            if parcel is None:
                # Чужое карго и чужой ПВЗ выглядят одинаково: не найдено.
                errors.append({"index": index, "id": pid, "error": "Посылка не найдена"})
                continue
            if parcel.status == data["status"]:
                continue
            try:
                with transaction.atomic():
                    update_parcel_status(parcel, data["status"], changed_by=request.user)
                updated += 1
            except Exception as exc:
                errors.append({"index": index, "id": pid, "error": str(exc)})

        return Response({"updated": updated, "errors": errors})

    @action(
        detail=False,
        methods=("post",),
        url_path="import",
        parser_classes=(MultiPartParser, FormParser),
    )
    def import_file(self, request):
        """Импорт накладной файлом (.xlsx / .xls / .csv).

        Разбор на сервере, а не в приложении: формат у поставщиков плавает
        (объединённые ячейки, cp1251, числа текстом), и каждый новый случай
        иначе требовал бы релиза в сторах. Плюс исходник остаётся на диске —
        когда на складе не сходится остаток, первый вопрос «какую накладную
        залили», и ответить на него больше нечем.
        """
        serializer = ParcelImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        upload = data["file"]
        if upload.size > IMPORT_MAX_FILE_BYTES:
            return Response(
                {"detail": f"Файл больше {IMPORT_MAX_FILE_BYTES // (1024 * 1024)} МБ."},
                status=413,
            )

        forbidden = self._forbidden_status(data["status"])
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        try:
            rows = read_rows(upload, upload.name)
        except ImportFormatError as exc:
            return Response({"detail": str(exc)}, status=400)

        layout = detect_layout(rows)
        # Присланное клиентом важнее распознанного: оператор видит файл глазами.
        try:
            if data.get("start_row"):
                layout.start_row = data["start_row"]
            for field, attr in (
                ("track_column", "track_column"),
                ("weight_column", "weight_column"),
                ("client_code_column", "client_code_column"),
            ):
                value = (data.get(field) or "").strip()
                if value:
                    column_letter_to_index(value)  # проверка формата
                    setattr(layout, attr, value.upper())
        except ImportFormatError as exc:
            return Response({"detail": str(exc)}, status=400)

        if not layout.track_column:
            return Response(
                {
                    "detail": "Не удалось определить колонку трек-номера. "
                    "Укажите её вручную."
                },
                status=400,
            )

        items = extract_rows(rows, layout)
        if len(items) > IMPORT_MAX_ROWS:
            return Response(
                {
                    "detail": f"В файле {len(items)} строк, больше "
                    f"{IMPORT_MAX_ROWS} за один раз не принимаем."
                },
                status=400,
            )

        china_only = self._china_only()
        cargo = None
        if not china_only:
            from cargo.models import CargoCompany

            cargo_id = get_request_cargo_id(request.user)
            cargo = CargoCompany.objects.filter(pk=cargo_id).first() if cargo_id else None
        point = data.get("pickup_point")

        apply_kwargs = dict(
            cargo=cargo,
            actor=request.user,
            status=data["status"],
            pickup_point=point.id if point else None,
            request=request,
            global_resolve=china_only,
        )

        detected = {
            "start_row": layout.start_row,
            "track_column": layout.track_column,
            "weight_column": layout.weight_column,
            "client_code_column": layout.client_code_column,
        }

        if data.get("dry_run"):
            outcome = _dry_run_import(items, apply_kwargs)
            body = outcome.as_dict()
            body["file_name"] = upload.name
            body["detected"] = detected
            body["preview"] = outcome.preview
            return Response(body)

        # Запись заводим до применения: ею помечаются строки истории, чтобы из
        # журнала операций можно было открыть исходную накладную.
        upload.seek(0)
        record = ParcelImport.objects.create(
            cargo=cargo,
            actor=request.user,
            file=upload,
            file_name=upload.name,
            status=data["status"],
            detected=detected,
        )
        started_at = timezone.now()
        outcome = apply_import_rows(items, **apply_kwargs)

        if outcome.parcel_ids:
            ParcelStatusHistory.objects.filter(
                parcel_id__in=outcome.parcel_ids,
                created_at__gte=started_at,
                source_import__isnull=True,
            ).update(source_import=record)

        record.total_rows = outcome.total_rows
        record.created_count = outcome.created
        record.updated_count = outcome.updated
        record.skipped_count = outcome.skipped
        record.errors = outcome.errors
        record.save(
            update_fields=[
                "total_rows",
                "created_count",
                "updated_count",
                "skipped_count",
                "errors",
            ]
        )

        body = outcome.as_dict()
        body["file_name"] = upload.name
        body["detected"] = detected
        body["source_file"] = request.build_absolute_uri(record.file.url)

        log_audit(
            AuditLog.Action.PARCEL_IMPORTED,
            actor=request.user,
            description=f"Импорт накладной {upload.name}",
            metadata={
                "import_id": record.id,
                "file_name": upload.name,
                "status": data["status"],
                **outcome.as_dict(),
            },
            request=request,
        )
        return Response(body)


def _dry_run_import(items, apply_kwargs):
    """Прогнать импорт и откатить.

    Именно прогнать, а не считать отдельной веткой: предпросмотр должен
    показывать ровно то, что произойдёт при записи, иначе он бесполезен.
    """

    class _Rollback(Exception):
        pass

    outcome = None
    try:
        with transaction.atomic():
            outcome = apply_import_rows(items, **apply_kwargs)
            raise _Rollback()
    except _Rollback:
        pass
    return outcome
