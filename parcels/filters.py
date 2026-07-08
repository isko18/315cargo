import django_filters

from common.filters import CreatedAtDateRangeFilter

from .models import Parcel


class ParcelFilter(CreatedAtDateRangeFilter):
    # Точный поиск по коду клиента — для панели выдачи (клиент → его посылки).
    client_code = django_filters.CharFilter(field_name="client_code", lookup_expr="exact")

    class Meta:
        model = Parcel
        fields = ("status", "track_number", "client_code", "date_from", "date_to")
