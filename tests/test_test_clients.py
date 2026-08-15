"""Тестовый клиент в каждом ПВЗ.

Смысл команды: оператор привязан к своему пункту и видит в поиске только своих
клиентов, поэтому одним аккаунтом выдачу во всех ПВЗ не проверить — нужен
аккаунт на пункт. Тесты держат главное: покрыты все пункты, повторный запуск
не плодит дублей, и каждый оператор действительно находит своего клиента.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from parcels.models import Parcel
from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory

User = get_user_model()


def run(**kwargs):
    out = StringIO()
    call_command("create_test_clients", stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_client_created_for_every_active_pickup(cargo):
    first = PickupPointFactory(cargo=cargo)
    second = PickupPointFactory(cargo=cargo)
    other_cargo = PickupPointFactory(cargo=CargoCompanyFactory())

    run()

    for pickup in (first, second, other_cargo):
        client = User.objects.get(phone=f"+996700{pickup.id:06d}")
        assert client.pickup_point_id == pickup.id
        assert client.cargo_id == pickup.cargo_id  # карго берётся у пункта
        assert client.client_code
        assert not client.is_staff and not client.is_superuser


@pytest.mark.django_db
def test_inactive_pickup_skipped(cargo):
    active = PickupPointFactory(cargo=cargo)
    closed = PickupPointFactory(cargo=cargo, is_active=False)

    run()

    assert User.objects.filter(phone=f"+996700{active.id:06d}").exists()
    assert not User.objects.filter(phone=f"+996700{closed.id:06d}").exists()


@pytest.mark.django_db
def test_rerun_does_not_duplicate(pickup_point):
    run()
    code = User.objects.get(phone=f"+996700{pickup_point.id:06d}").client_code

    run()

    clients = User.objects.filter(phone=f"+996700{pickup_point.id:06d}")
    assert clients.count() == 1
    assert clients.first().client_code == code  # код не перевыдаётся
    assert Parcel.objects.filter(user=clients.first()).count() == 2


@pytest.mark.django_db
def test_demo_parcels_land_in_their_pickup(pickup_point):
    run()

    ready = Parcel.objects.get(track_number=f"TEST-PVZ-{pickup_point.id}-A")
    assert ready.status == Parcel.Status.AT_PICKUP_POINT
    assert ready.pickup_point_id == pickup_point.id  # выдачу есть чем проверить
    in_transit = Parcel.objects.get(track_number=f"TEST-PVZ-{pickup_point.id}-B")
    assert in_transit.pickup_point_id is None


@pytest.mark.django_db
def test_bound_operator_finds_own_test_client(api_client, cargo):
    """Ради этого всё и делается: у каждого оператора свой тестовый клиент."""
    from rest_framework_simplejwt.tokens import RefreshToken

    mine = PickupPointFactory(cargo=cargo)
    foreign = PickupPointFactory(cargo=cargo)
    run()

    operator = UserFactory(cargo=cargo, pickup_point=mine, is_staff=True)
    refresh = RefreshToken.for_user(operator)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    found = api_client.get("/api/clients/search/?q=Тест").data
    phones = {row["phone"] for row in found}
    assert f"+996700{mine.id:06d}" in phones
    assert f"+996700{foreign.id:06d}" not in phones


@pytest.mark.django_db
def test_dry_run_writes_nothing(pickup_point):
    output = run(dry_run=True)

    assert f"+996700{pickup_point.id:06d}" in output
    assert not User.objects.filter(phone=f"+996700{pickup_point.id:06d}").exists()


@pytest.mark.django_db
def test_env_line_covers_all_numbers(pickup_point):
    """Без OTP_TEST_NUMBERS вход попросит настоящую SMS — строку печатаем готовой."""
    output = run(code="1234")

    line = next(l for l in output.splitlines() if l.startswith("OTP_TEST_NUMBERS="))
    assert f"+996700{pickup_point.id:06d}:1234" in line
    assert "+996700000000:1234" in line  # номер ревьюера не теряем
