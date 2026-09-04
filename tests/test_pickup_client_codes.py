"""Своя нумерация клиентских кодов у ПВЗ.

По клиентскому коду коробку опознают на складе в Китае, где лежат посылки всех
карго сразу. Поэтому здесь важнее всего две вещи: коды не должны повторяться,
а уже выданные — не должны меняться.
"""

import pytest

from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory
from users.services import generate_client_code


@pytest.mark.django_db
def test_pickup_with_prefix_uses_own_numbering():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="ISIM")

    assert generate_client_code(cargo, manas) == "ISIM0001"
    assert generate_client_code(cargo, manas) == "ISIM0002"


@pytest.mark.django_db
def test_each_pickup_numbers_independently():
    """Нумерация у ПВЗ своя: второй ПВЗ начинает с единицы, а не продолжает."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="ISIM")
    osh = PickupPointFactory(cargo=cargo, client_code_prefix="ISIO")

    assert generate_client_code(cargo, manas) == "ISIM0001"
    assert generate_client_code(cargo, osh) == "ISIO0001"
    assert generate_client_code(cargo, manas) == "ISIM0002"


@pytest.mark.django_db
def test_pickup_without_prefix_falls_back_to_cargo():
    """Существующие ПВЗ префикса не имеют — они обязаны работать как раньше."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    point = PickupPointFactory(cargo=cargo, client_code_prefix="")

    assert generate_client_code(cargo, point) == "ISI0001"
    assert generate_client_code(cargo, None) == "ISI0002"


@pytest.mark.django_db
def test_pickup_numbering_does_not_touch_cargo_counter():
    """Счётчик карго не должен двигаться из-за ПВЗ со своей нумерацией."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="ISIM")

    generate_client_code(cargo, manas)
    generate_client_code(cargo, manas)
    cargo.refresh_from_db()

    assert cargo.client_code_seq == 0
    assert generate_client_code(cargo, None) == "ISI0001"


@pytest.mark.django_db
def test_taken_code_is_skipped():
    """Код мог быть выставлен руками в админке — занятый номер пропускаем."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="ISIM")
    UserFactory(cargo=cargo, pickup_point=manas, client_code="ISIM0001")

    assert generate_client_code(cargo, manas) == "ISIM0002"


@pytest.mark.django_db
def test_full_save_does_not_rewind_counter():
    """Обычное сохранение ПВЗ не должно откатывать счётчик к прочитанному."""
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="ISIM")
    stale = type(manas).objects.get(pk=manas.pk)  # прочитан до выдачи кода

    generate_client_code(cargo, manas)
    stale.title = "Переименован"
    stale.save()

    manas.refresh_from_db()
    assert manas.client_code_seq == 1
    assert generate_client_code(cargo, manas) == "ISIM0002"


@pytest.mark.django_db
def test_next_client_code_preview():
    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="ISIM")
    plain = PickupPointFactory(cargo=cargo, client_code_prefix="")

    assert manas.next_client_code() == "ISIM0001"
    # Без своего префикса предпросмотр показывает код карго.
    assert plain.next_client_code() == cargo.next_client_code()


# --- Уникальность префикса ---


@pytest.mark.django_db
def test_pickup_prefix_cannot_clash_with_cargo(cargo_admin_client, pickup_point):
    CargoCompanyFactory(client_code_prefix="ZZZ")

    response = cargo_admin_client.patch(
        f"/api/manage/pickup-points/{pickup_point.id}/",
        {"client_code_prefix": "ZZZ"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_pickup_prefix_cannot_clash_with_other_pickup(cargo_admin_client, pickup_point):
    PickupPointFactory(cargo=pickup_point.cargo, client_code_prefix="QQQ")

    response = cargo_admin_client.patch(
        f"/api/manage/pickup-points/{pickup_point.id}/",
        {"client_code_prefix": "QQQ"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_pickup_prefix_can_be_cleared(cargo_admin_client, pickup_point):
    """Пустой префикс разрешён — это возврат к общей нумерации карго."""
    response = cargo_admin_client.patch(
        f"/api/manage/pickup-points/{pickup_point.id}/",
        {"client_code_prefix": ""},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["client_code_prefix"] == ""


@pytest.mark.django_db
def test_registration_uses_pickup_prefix(api_client):
    """Регрессия: код выдаётся сигналом на создании пользователя.

    ПВЗ проставлялся отдельным save() после создания, поэтому в момент выдачи
    кода его ещё не было — новый клиент ПВЗ со своим префиксом получал код
    карго. Ловится только через полный путь регистрации.
    """
    from users.models import SMSCode

    cargo = CargoCompanyFactory(client_code_prefix="ISI")
    manas = PickupPointFactory(cargo=cargo, client_code_prefix="MNS")
    SMSCode.objects.create(
        phone="+996700424242", cargo=cargo, code="1234",
        purpose=SMSCode.Purpose.REGISTER, expires_at=SMSCode.default_expires_at(),
    )

    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": "+996700424242", "code": "1234", "cargo_id": cargo.id,
            "pickup_point_id": manas.id, "full_name": "Новый Клиент",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["user"]["client_code"] == "MNS0001"
