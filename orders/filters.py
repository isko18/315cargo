from common.filters import CreatedAtDateRangeFilter

from .models import Order


class OrderFilter(CreatedAtDateRangeFilter):
    class Meta:
        model = Order
        fields = ("source", "status", "track_number", "date_from", "date_to")
