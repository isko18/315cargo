import django_filters


class CreatedAtDateRangeFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
