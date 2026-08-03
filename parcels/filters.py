import django_filters
from django.db.models import Q

from common.filters import CreatedAtDateRangeFilter

from .models import Parcel


class ParcelFilter(CreatedAtDateRangeFilter):
    # Точный поиск по коду клиента — для панели выдачи (клиент → его посылки).
    client_code = django_filters.CharFilter(field_name="client_code", lookup_expr="exact")
    # Список статусов через запятую: ?status_in=at_pickup_point,arrived_kyrgyzstan
    status_in = django_filters.BaseInFilter(field_name="status")
    # Свободный поиск по треку / коду клиента / названию товара — для склада.
    search = django_filters.CharFilter(method="filter_search")
    # Только непривязанные к клиенту (pending со сканера).
    pending = django_filters.BooleanFilter(field_name="user", lookup_expr="isnull")
    # Переключатель ПВЗ владельца: физически принятые в этот ПВЗ (в т.ч. «ничьи»)
    # + ещё не принятые, но адресованные его клиентам.
    pickup_point = django_filters.NumberFilter(method="filter_pickup_point")
    # Архив (выданные посылки). По умолчанию склад показывает активные.
    archived = django_filters.BooleanFilter(field_name="is_archived")

    def filter_search(self, queryset, name, value):
        value = (value or "").strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(track_number__icontains=value)
            | Q(client_code__icontains=value)
            | Q(order__product_title__icontains=value)
        )

    def filter_pickup_point(self, queryset, name, value):
        from common.cargo_scoping import bound_pickup_id

        # Привязанный оператор уже ограничен своим ПВЗ во ViewSet — параметр
        # переключателя игнорируем, иначе он спрячет посылки его же ПВЗ.
        user = getattr(self.request, "user", None)
        if user is not None and bound_pickup_id(user):
            return queryset
        return queryset.filter(
            Q(pickup_point_id=value)
            | Q(pickup_point__isnull=True, user__pickup_point_id=value)
        )

    class Meta:
        model = Parcel
        fields = (
            "status",
            "status_in",
            "track_number",
            "client_code",
            "search",
            "pending",
            "pickup_point",
            "archived",
            "date_from",
            "date_to",
        )
