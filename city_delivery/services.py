from .models import CityDeliveryTariff


def resolve_tariff(parcel) -> CityDeliveryTariff | None:
    pickup_point_id = getattr(parcel.user, "pickup_point_id", None)
    if pickup_point_id:
        tariff = (
            CityDeliveryTariff.objects.filter(
                is_active=True, pickup_point_id=pickup_point_id
            )
            .order_by("-is_default")
            .first()
        )
        if tariff:
            return tariff
    return (
        CityDeliveryTariff.objects.filter(is_active=True, pickup_point__isnull=True)
        .order_by("-is_default", "title")
        .first()
    )


def calculate_price(parcel, tariff: CityDeliveryTariff | None = None):
    tariff = tariff or resolve_tariff(parcel)
    if not tariff:
        return None, None
    price = tariff.calculate(weight_kg=parcel.weight or 0)
    return price, tariff
