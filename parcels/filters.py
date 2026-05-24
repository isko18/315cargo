from common.filters import CreatedAtDateRangeFilter

from .models import Parcel


class ParcelFilter(CreatedAtDateRangeFilter):
    class Meta:
        model = Parcel
        fields = ("status", "track_number", "date_from", "date_to")
