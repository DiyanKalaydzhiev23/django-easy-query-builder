from datetime import date
from decimal import Decimal

import pytest
from django.db.models import Q
from model_bakery import baker

from django_easy_query_builder.builders import QueryBuilder
from django_easy_query_builder.parsers import QueryParser
from django_easy_query_builder.validators import QTreeValidator
from examples.models import Car, Country, Manufacturer, Person


@pytest.mark.django_db
def test_query_builder_filters_people() -> None:
    query = (
        "~Q(first_name=Ivan)&(Q(last_name=Petrov|age__gt=18&age__lt=65)"
        "|Q(email__icontains=example.com))"
    )
    parser = QueryParser(query)
    tree = parser.parse()

    expected_tree = [
        {"not": {"first_name": "Ivan"}},
        {"op": "&"},
        [
            {
                "or": [
                    {"last_name": "Petrov"},
                    {"and": [{"age__gt": "18"}, {"age__lt": "65"}]},
                ]
            },
            {"op": "|"},
            {"email__icontains": "example.com"},
        ],
    ]
    assert tree == expected_tree

    validator = QTreeValidator(["first_name", "last_name", "age", "email"])
    validator.validate(tree)

    petrov = baker.make(
        Person,
        first_name="Petr",
        last_name="Petrov",
        age=40,
        email="petr@example.com",
        date_of_birth=date(1983, 5, 5),
    )
    baker.make(
        Person,
        first_name="Ivan",
        last_name="Petrov",
        age=35,
        email="ivan@example.com",
        date_of_birth=date(1988, 1, 1),
    )
    age_match = baker.make(
        Person,
        first_name="Maria",
        last_name="Sidorova",
        age=30,
        email="maria@other.com",
        date_of_birth=date(1993, 7, 12),
    )
    email_match = baker.make(
        Person,
        first_name="John",
        last_name="Smith",
        age=28,
        email="john@example.com",
        date_of_birth=date(1995, 3, 20),
    )
    baker.make(
        Person,
        first_name="Anna",
        last_name="Ivanova",
        age=17,
        email="anna@demo.org",
        date_of_birth=date(2006, 10, 30),
    )

    query_builder = QueryBuilder()
    result_ids = set(
        Person.objects.filter(query_builder.build_q(tree)).values_list("id", flat=True)
    )
    expected_ids = {petrov.id, age_match.id, email_match.id}
    assert result_ids == expected_ids


@pytest.mark.django_db
def test_query_builder_handles_nested_relations() -> None:
    germany = baker.make(Country, name="Germany")
    japan = baker.make(Country, name="Japan")
    volkswagen = baker.make(Manufacturer, name="Volkswagen", country=germany)
    toyota = baker.make(Manufacturer, name="Toyota", country=japan)

    golf = baker.make(
        Car,
        model="Golf",
        manufacturer=volkswagen,
        year=2020,
        price=Decimal("20000.00"),
        is_electric=False,
    )
    prius = baker.make(
        Car,
        model="Prius",
        manufacturer=toyota,
        year=2021,
        price=Decimal("25000.00"),
        is_electric=True,
    )

    person_one = baker.make(Person)
    person_one.cars.add(golf)

    person_two = baker.make(Person)
    person_two.cars.add(prius)

    query = "Q(cars__manufacturer__country__name=Germany)"
    parser = QueryParser(query)
    tree = parser.parse()

    validator = QTreeValidator(
        ["first_name", "last_name", "cars__manufacturer__country__name"]
    )
    validator.validate(tree)

    query_builder = QueryBuilder()
    q_object = query_builder.build_q(tree)

    result_ids = set(Person.objects.filter(q_object).values_list("id", flat=True))
    expected_ids = set(
        Person.objects.filter(
            Q(cars__manufacturer__country__name="Germany")
        ).values_list("id", flat=True)
    )
    assert result_ids == expected_ids == {person_one.id}
