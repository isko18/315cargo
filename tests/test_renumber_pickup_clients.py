"""Перенумерация клиентов ПВЗ.

Команда меняет то, по чему коробку опознают на складе в Китае, и откатить это
нечем. Поэтому проверяем не только «коды поменялись», но и что ничего не
осталось со старым значением: посылки, QR, счётчик.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory
from parcels.models import Parcel
from users.models import User


def run(point, apply=False):
    args = ["renumber_pickup_clients", "--pickup", str(point.id)]
    if apply:
        args.append("--apply")
    call_command(*args)


@pytest.mark.django_db
def test_dry_run_changes_nothing():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    user = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")

    run(point)

    user.refresh_from_db()
    assert user.client_code == "ISI0007"


@pytest.mark.django_db
def test_renumbers_in_registration_order():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    first = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0009")
    second = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0003")

    run(point, apply=True)

    first.refresh_from_db()
    second.refresh_from_db()
    # Порядок по регистрации, а не по старому номеру.
    assert first.client_code == "MNS0001"
    assert second.client_code == "MNS0002"


@pytest.mark.django_db
def test_parcels_follow_the_new_code():
    """Код продублирован на посылке — иначе поиск перестанет их находить."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    user = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")
    parcel = Parcel.objects.create(
        cargo=cargo, user=user, client_code="ISI0007", track_number="T1", status="created"
    )

    run(point, apply=True)

    parcel.refresh_from_db()
    user.refresh_from_db()
    assert parcel.client_code == user.client_code == "MNS0001"


@pytest.mark.django_db
def test_qr_regenerated():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    user = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")

    run(point, apply=True)

    user.refresh_from_db()
    # Имя файла QR содержит код: старый QR показывал бы старый код на выдаче.
    assert "MNS0001" in user.qr_code_image.name


@pytest.mark.django_db
def test_counter_moves_so_next_client_does_not_collide():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")

    run(point, apply=True)

    point.refresh_from_db()
    assert point.client_code_seq == 1
    assert point.next_client_code() == "MNS0002"


@pytest.mark.django_db
def test_second_run_is_noop():
    """Команду могут запустить дважды — второй раз не должен сдвигать коды."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    user = UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")

    run(point, apply=True)
    run(point, apply=True)

    user.refresh_from_db()
    point.refresh_from_db()
    assert user.client_code == "MNS0001"
    assert point.client_code_seq == 1


@pytest.mark.django_db
def test_other_pickup_untouched():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    osh = PickupPointFactory(cargo=cargo, client_code_prefix="")
    UserFactory(cargo=cargo, pickup_point=manas, client_code="ISI0007")
    other = UserFactory(cargo=cargo, pickup_point=osh, client_code="ISI0008")

    run(manas, apply=True)

    other.refresh_from_db()
    assert other.client_code == "ISI0008"


@pytest.mark.django_db
def test_refuses_without_prefix():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="")
    UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")

    with pytest.raises(CommandError):
        run(point, apply=True)


@pytest.mark.django_db
def test_refuses_on_code_clash():
    """Код мог быть занят вручную — молча перетереть чужой код нельзя."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    UserFactory(cargo=cargo, pickup_point=point, client_code="ISI0007")
    UserFactory(cargo=cargo, client_code="MNS0001")  # занял будущий код

    with pytest.raises(CommandError):
        run(point, apply=True)

    assert User.objects.filter(client_code="ISI0007").exists()
