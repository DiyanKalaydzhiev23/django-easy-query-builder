import json
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from examples.models import Car, Country, Manufacturer, Person


@pytest.fixture
def admin_client(client):
    user = get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin",
    )
    client.force_login(user)
    return client


def _first_name_equals_payload(value: str) -> dict:
    return {
        "id": "group-1",
        "logicalOperator": "AND",
        "negated": False,
        "conditions": [
            {
                "id": "condition-1",
                "field": "first_name",
                "operator": "equals",
                "value": value,
                "negated": False,
                "isVariableOnly": False,
            }
        ],
        "groups": [],
    }


@pytest.mark.django_db
def test_admin_changelist_applies_advanced_query_and_repeat_request(
    admin_client,
) -> None:
    maria = Person.objects.create(
        first_name="Maria",
        last_name="Petrova",
        age=30,
        email="maria@example.com",
        date_of_birth=date(1995, 1, 1),
    )
    Person.objects.create(
        first_name="Ivan",
        last_name="Ivanov",
        age=33,
        email="ivan@example.com",
        date_of_birth=date(1992, 1, 1),
    )

    payload = _first_name_equals_payload("maria")

    response = admin_client.get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )
    assert response.status_code == 200

    result_ids = {obj.id for obj in response.context["cl"].result_list}
    assert result_ids == {maria.id}

    # Simulates clicking Apply again after the page hydrates from initialQuery.
    hydrated_payload = json.loads(
        response.context["query_builder_frontend_config"]["initialQuery"]
    )
    second_response = admin_client.get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(hydrated_payload)},
    )

    assert second_response.status_code == 200
    second_result_ids = {obj.id for obj in second_response.context["cl"].result_list}
    assert second_result_ids == {maria.id}


@pytest.mark.django_db
def test_admin_changelist_invalid_filter_does_not_crash(admin_client) -> None:
    Person.objects.create(
        first_name="Maria",
        last_name="Petrova",
        age=30,
        email="maria@example.com",
        date_of_birth=date(1995, 1, 1),
    )

    invalid_payload = {
        "id": "group-1",
        "logicalOperator": "AND",
        "negated": False,
        "conditions": [
            {
                "id": "condition-1",
                "field": "date_of_birth",
                "operator": "contains",
                "value": "maria",
                "negated": False,
                "isVariableOnly": False,
            }
        ],
        "groups": [],
    }

    response = admin_client.get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(invalid_payload)},
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_changelist_applies_count_transform_filter(admin_client) -> None:
    country = Country.objects.create(name="Germany")
    manufacturer = Manufacturer.objects.create(name="VW", country=country)
    golf = Car.objects.create(
        model="Golf",
        manufacturer=manufacturer,
        year=2020,
        price="20000.00",
        is_electric=False,
    )
    passat = Car.objects.create(
        model="Passat",
        manufacturer=manufacturer,
        year=2021,
        price="25000.00",
        is_electric=False,
    )

    maria = Person.objects.create(
        first_name="Maria",
        last_name="Petrova",
        age=30,
        email="maria@example.com",
        date_of_birth=date(1995, 1, 1),
    )
    maria.cars.add(golf, passat)

    ivan = Person.objects.create(
        first_name="Ivan",
        last_name="Ivanov",
        age=33,
        email="ivan@example.com",
        date_of_birth=date(1992, 1, 1),
    )
    ivan.cars.add(golf)

    payload = {
        "id": "group-1",
        "logicalOperator": "AND",
        "operators": [],
        "negated": False,
        "conditions": [
            {
                "id": "condition-transform",
                "field": "cars",
                "operator": "equals",
                "value": "",
                "negated": False,
                "isVariableOnly": True,
                "transforms": [{"id": "transform-count-cars", "value": "count"}],
            },
            {
                "id": "condition-filter",
                "field": "count_cars",
                "fieldRef": {
                    "type": "alias",
                    "transformId": "transform-count-cars",
                },
                "operator": "greater_than",
                "value": "1",
                "negated": False,
                "isVariableOnly": False,
            },
        ],
        "groups": [],
    }

    response = admin_client.get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )
    assert response.status_code == 200
    assert {obj.id for obj in response.context["cl"].result_list} == {maria.id}

    hydrated_payload = json.loads(
        response.context["query_builder_frontend_config"]["initialQuery"]
    )
    second_response = admin_client.get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(hydrated_payload)},
    )

    assert second_response.status_code == 200
    assert {obj.id for obj in second_response.context["cl"].result_list} == {maria.id}


@pytest.mark.django_db
def test_admin_changelist_invalid_variable_shows_message_and_does_not_crash(
    admin_client,
) -> None:
    maria = Person.objects.create(
        first_name="Maria",
        last_name="Petrova",
        age=30,
        email="maria@example.com",
        date_of_birth=date(1995, 1, 1),
    )
    ivan = Person.objects.create(
        first_name="Ivan",
        last_name="Ivanov",
        age=33,
        email="ivan@example.com",
        date_of_birth=date(1992, 1, 1),
    )

    payload = {
        "id": "group-1",
        "logicalOperator": "AND",
        "negated": False,
        "conditions": [
            {
                "id": "condition-transform",
                "field": "age",
                "operator": "equals",
                "value": "",
                "negated": False,
                "isVariableOnly": True,
                "transforms": [{"id": "transform-avg-age", "value": "avg"}],
            },
            {
                "id": "condition-filter",
                "field": "age",
                "operator": "greater_than",
                "value": "avg_agee",
                "negated": False,
                "isVariableOnly": False,
            },
        ],
        "groups": [],
    }

    response = admin_client.get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert {obj.id for obj in response.context["cl"].result_list} == {
        maria.id,
        ivan.id,
    }

    messages = [message.message for message in response.context["messages"]]
    assert "Invalid advanced query payload: Unknown variable 'avg_agee'." in messages
