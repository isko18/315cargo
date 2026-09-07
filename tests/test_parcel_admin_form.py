"""Форма посылки в админке.

client_code на посылке — копия кода клиента на момент приёмки. Из формы это
было не видно: копия показывалась редактируемым полем, ПВЗ у непринятой
посылки пуст, и оба выглядели как потерянные данные.
"""

import pytest

from parcels.admin import ParcelAdmin
from parcels.models import Parcel
from pickup_points.models import PickupPoint
from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory


@pytest.fixture
def admin_obj():
    from django.contrib import admin as dj_admin

    return ParcelAdmin(Parcel, dj_admin.site)


@pytest.mark.django_db
def test_shows_client_code_and_pickup_from_client_card(admin_obj):
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, title="1 КАРГО Ош")
    user = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI-0177")
    parcel = Parcel.objects.create(
        cargo=cargo, user=user, client_code="ISI-0177", track_number="T1", status="created"
    )

    assert admin_obj.user_client_code(parcel) == "ISI-0177"
    # У непринятой посылки своего ПВЗ нет — показываем ПВЗ клиента и то, что
    # именно за ним посылка сейчас числится.
    assert parcel.pickup_point_id is None
    shown = admin_obj.user_pickup_point(parcel)
    assert "1 КАРГО Ош" in shown
    assert "пока не принята" in shown


@pytest.mark.django_db
def test_marks_code_drift_between_parcel_and_client(admin_obj):
    """Расхождение копии и оригинала должно быть видно, а не тихо путать."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    user = UserFactory(cargo=cargo, client_code="MNS0003")
    parcel = Parcel.objects.create(
        cargo=cargo, user=user, client_code="ISI-0014", track_number="T2", status="created"
    )

    shown = admin_obj.user_client_code(parcel)
    assert "MNS0003" in shown
    assert "ISI-0014" in shown


@pytest.mark.django_db
def test_parcel_without_client_does_not_crash(admin_obj):
    cargo = CargoCompanyFactory()
    parcel = Parcel.objects.create(
        cargo=cargo, user=None, client_code="", track_number="T3", status="created"
    )

    assert "без клиента" in admin_obj.user_client_code(parcel)
    assert "без клиента" in admin_obj.user_pickup_point(parcel)


@pytest.mark.django_db
def test_client_code_editable_on_add_but_not_on_change(admin_obj, rf, superuser):
    """На создании поле обязательное, поэтому read-only только в изменении."""
    cargo = CargoCompanyFactory()
    parcel = Parcel.objects.create(
        cargo=cargo, user=None, client_code="X0001", track_number="T4", status="created"
    )
    request = rf.get("/")
    request.user = superuser

    assert "client_code" not in admin_obj.get_readonly_fields(request, None)
    assert "client_code" in admin_obj.get_readonly_fields(request, parcel)


@pytest.mark.django_db
def test_pickup_choices_limited_to_parcel_cargo(admin_obj, rf, superuser):
    """Раньше в списке лежали ПВЗ всех карго — можно было назначить чужой."""
    mine = CargoCompanyFactory()
    other = CargoCompanyFactory()
    my_point = PickupPointFactory(cargo=mine)
    foreign = PickupPointFactory(cargo=other)
    parcel = Parcel.objects.create(
        cargo=mine, user=None, client_code="", track_number="T5", status="created"
    )

    request = rf.get(f"/admin/parcels/parcel/{parcel.pk}/change/")
    request.user = superuser
    request.resolver_match = type("M", (), {"kwargs": {"object_id": str(parcel.pk)}})()

    field = admin_obj.formfield_for_foreignkey(
        Parcel._meta.get_field("pickup_point"), request
    )
    ids = set(field.queryset.values_list("id", flat=True))
    assert my_point.id in ids
    assert foreign.id not in ids


@pytest.mark.django_db
def test_pickup_mismatch_is_visible(admin_obj):
    """Принята не в свой ПВЗ — это нештатно и должно бросаться в глаза."""
    cargo = CargoCompanyFactory()
    home = PickupPointFactory(cargo=cargo, title="ПВЗ Ош")
    other = PickupPointFactory(cargo=cargo, title="ПВЗ Манас")
    user = UserFactory(cargo=cargo, pickup_point=home)
    parcel = Parcel.objects.create(
        cargo=cargo, user=user, client_code=user.client_code, track_number="T6",
        status="at_pickup_point", pickup_point=other,
    )

    shown = admin_obj.user_pickup_point(parcel)
    assert "ПВЗ Ош" in shown and "ПВЗ Манас" in shown


@pytest.mark.django_db
def test_pickup_match_is_stated_plainly(admin_obj):
    cargo = CargoCompanyFactory()
    home = PickupPointFactory(cargo=cargo, title="ПВЗ Ош")
    user = UserFactory(cargo=cargo, pickup_point=home)
    parcel = Parcel.objects.create(
        cargo=cargo, user=user, client_code=user.client_code, track_number="T7",
        status="at_pickup_point", pickup_point=home,
    )

    assert "совпадает" in admin_obj.user_pickup_point(parcel)


@pytest.mark.django_db
def test_client_pickup_row_sits_next_to_parcel_pickup(admin_obj, rf, superuser):
    """Пояснение бесполезно, если стоит далеко от самого поля «ПВЗ»."""
    cargo = CargoCompanyFactory()
    parcel = Parcel.objects.create(
        cargo=cargo, user=None, client_code="", track_number="T8", status="created"
    )
    request = rf.get("/")
    request.user = superuser

    fields = admin_obj.get_fields(request, parcel)
    assert fields.index("user_pickup_point") == fields.index("pickup_point") + 1
    assert fields.index("user_client_code") == fields.index("client_code") + 1
