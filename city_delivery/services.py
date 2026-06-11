from .models import CityDeliveryTariff


def resolve_tariff(parcel) -> CityDeliveryTariff | None:
    pickup_point_id = getattr(parcel.user, "pickup_point_id", None)
    if pickup_point_id:
        tariff = (
            CityDeliveryTariff.objects.filter(
                is_active=True, pickup_point_id=pickup_point_id
            )
            .order_by("-is_default", "title")
            .first()
        )
        if tariff:
            return tariff
    # Fallback to a general tariff (no specific pickup point). A tariff bound to
    # a cargo applies only to that cargo's clients, so one cargo's tariff can
    # never price another's parcels. A cargo-agnostic tariff (cargo IS NULL) is
    # a true global default usable by everyone, and a cargo-specific tariff
    # takes precedence over the global one.
    fallback = CityDeliveryTariff.objects.filter(
        is_active=True, pickup_point__isnull=True
    )
    cargo_id = getattr(parcel.user, "cargo_id", None)
    if cargo_id:
        specific = (
            fallback.filter(cargo_id=cargo_id).order_by("-is_default", "title").first()
        )
        if specific:
            return specific
    return fallback.filter(cargo__isnull=True).order_by("-is_default", "title").first()


def calculate_price(parcel, tariff: CityDeliveryTariff | None = None):
    tariff = tariff or resolve_tariff(parcel)
    if not tariff:
        return None, None
    price = tariff.calculate(weight_kg=parcel.weight or 0)
    return price, tariff
