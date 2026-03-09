import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.exceptions import SuspiciousOperation
from django.test import RequestFactory
from model_bakery import baker

from django_easy_query_builder.builders import QueryBuilder
from django_easy_query_builder.mixins import QueryBuilderAdminMixin
from django_easy_query_builder.parsers import AliasReference, StructuredQueryParser
from django_easy_query_builder.validators import QTreeValidator
from examples.models import Car, Country, Manufacturer, Person

LOOKUP_FILTER_CASES = [
    ("exact", "first_name", "__exact", "Maria", {"maria"}),
    ("iexact", "first_name", "__iexact", "maria", {"maria"}),
    ("eq_alias", "first_name", "__eq", "Maria", {"maria"}),
    ("ne_alias", "first_name", "__ne", "Maria", {"marco", "anna"}),
    ("starts_with_alias", "first_name", "starts_with", "Mar", {"maria", "marco"}),
    (
        "dunder_starts_with_alias",
        "first_name",
        "__starts_with",
        "Mar",
        {"maria", "marco"},
    ),
    ("contains", "email", "__contains", "example", {"maria"}),
    ("icontains", "email", "__icontains", "EXAMPLE", {"maria"}),
    ("gt", "age", "__gt", "30", {"marco"}),
    ("gte", "age", "__gte", "30", {"maria", "marco"}),
    ("lt", "age", "__lt", "30", {"anna"}),
    ("lte", "age", "__lte", "30", {"maria", "anna"}),
    ("startswith", "first_name", "__startswith", "Maria", {"maria"}),
    ("istartswith", "first_name", "__istartswith", "mari", {"maria"}),
    ("endswith", "last_name", "__endswith", "son", {"marco"}),
    ("iendswith", "last_name", "__iendswith", "SON", {"marco"}),
    ("date", "date_of_birth", "__date", "1995-01-15", {"maria"}),
    ("year", "date_of_birth", "__year", "1995", {"maria", "anna"}),
    ("month", "date_of_birth", "__month", "1", {"maria", "marco"}),
]


@pytest.mark.django_db
def test_structured_query_parser_and_builder_filters_people() -> None:
    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {"field": "first_name", "operator": "not_equals", "value": "Ivan"},
        ],
        "groups": [
            {
                "logicalOperator": "OR",
                "conditions": [
                    {"field": "last_name", "operator": "equals", "value": "Petrov"},
                    {"field": "email", "operator": "contains", "value": "example.com"},
                ],
                "groups": [
                    {
                        "logicalOperator": "AND",
                        "conditions": [
                            {"field": "age", "operator": "greater_than", "value": "18"},
                            {"field": "age", "operator": "less_than", "value": "65"},
                        ],
                        "groups": [],
                        "negated": False,
                    }
                ],
                "negated": False,
            }
        ],
        "negated": False,
    }

    parser = StructuredQueryParser(json.dumps(payload))
    tree = parser.parse()

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
    assert result_ids == {petrov.id, age_match.id, email_match.id}


def test_structured_query_parser_rejects_unknown_condition_keys() -> None:
    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {
                "field": "first_name",
                "operator": "equals",
                "value": "Ivan",
                "raw_sql": "bad",
            }
        ],
        "groups": [],
        "negated": False,
    }

    with pytest.raises(SyntaxError):
        StructuredQueryParser(json.dumps(payload)).parse()


def test_structured_query_parser_respects_per_boundary_operators() -> None:
    payload = {
        "logicalOperator": "AND",
        "operators": ["OR"],
        "conditions": [
            {"field": "first_name", "operator": "equals", "value": "Maria"},
            {"field": "last_name", "operator": "equals", "value": "Petrova"},
        ],
        "groups": [],
        "negated": False,
    }

    tree = StructuredQueryParser(json.dumps(payload)).parse()
    assert tree == [{"first_name": "Maria"}, {"op": "|"}, {"last_name": "Petrova"}]


def test_structured_query_parser_rejects_invalid_group_operator_boundaries() -> None:
    payload = {
        "logicalOperator": "AND",
        "operators": ["OR", "AND"],
        "conditions": [
            {"field": "first_name", "operator": "equals", "value": "Maria"},
            {"field": "last_name", "operator": "equals", "value": "Petrova"},
        ],
        "groups": [],
        "negated": False,
    }

    with pytest.raises(SyntaxError):
        StructuredQueryParser(json.dumps(payload)).parse()


def test_structured_query_parser_supports_dunder_lookup_operators() -> None:
    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {"field": "email", "operator": "__icontains", "value": "example.com"},
            {"field": "first_name", "operator": "__eq", "value": "Ivan"},
            {"field": "last_name", "operator": "__ne", "value": "Petrov"},
        ],
        "groups": [],
        "negated": False,
    }

    tree = StructuredQueryParser(json.dumps(payload)).parse()
    assert tree == [
        {"email__icontains": "example.com"},
        {"op": "&"},
        {"first_name": "Ivan"},
        {"op": "&"},
        {"not": {"last_name": "Petrov"}},
    ]


def test_structured_query_parser_supports_alias_value_references() -> None:
    payload = {
        "logicalOperator": "AND",
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
                "field": "age",
                "operator": "greater_than",
                "value": "count_cars",
                "valueRef": {
                    "type": "alias",
                    "transformId": "transform-count-cars",
                },
                "negated": False,
                "isVariableOnly": False,
            },
        ],
        "groups": [],
        "negated": False,
    }

    tree = StructuredQueryParser(json.dumps(payload)).parse()

    assert tree == [{"age__gt": AliasReference("count_cars")}]


@pytest.mark.django_db
def test_structured_query_subquery_exists_filters_related_records() -> None:
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

    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {
                "field": "cars",
                "operator": "exists",
                "query": {
                    "logicalOperator": "AND",
                    "conditions": [
                        {
                            "field": "manufacturer.country.name",
                            "operator": "equals",
                            "value": "Germany",
                        }
                    ],
                    "groups": [],
                    "negated": False,
                },
            }
        ],
        "groups": [],
        "negated": False,
    }

    tree = StructuredQueryParser(json.dumps(payload)).parse()
    validator = QTreeValidator(["cars__manufacturer__country__name"])
    validator.validate(tree)

    query_builder = QueryBuilder(root_model=Person)
    result_ids = set(
        Person.objects.filter(query_builder.build_q(tree)).values_list("id", flat=True)
    )
    assert result_ids == {person_one.id}
    assert person_two.id not in result_ids


@pytest.mark.django_db
def test_admin_mixin_applies_advanced_query_payload() -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = ["first_name", "email"]

    admin_instance = PersonAdmin(Person, admin.site)

    matching = baker.make(
        Person,
        first_name="John",
        last_name="Smith",
        age=30,
        email="john@example.com",
        date_of_birth=date(1994, 1, 1),
    )
    baker.make(
        Person,
        first_name="Jane",
        last_name="Doe",
        age=26,
        email="jane@other.org",
        date_of_birth=date(1998, 1, 1),
    )

    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {"field": "email", "operator": "contains", "value": "example.com"}
        ],
        "groups": [],
        "negated": False,
    }

    request = RequestFactory().get(
        "/admin/examples/person/", {"advanced_query": json.dumps(payload)}
    )
    queryset = admin_instance.get_queryset(request)

    result_ids = set(queryset.values_list("id", flat=True))
    assert result_ids == {matching.id}


@pytest.mark.django_db
def test_admin_mixin_rejects_invalid_payload() -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = ["first_name"]

    admin_instance = PersonAdmin(Person, admin.site)
    request = RequestFactory().get(
        "/admin/examples/person/", {"advanced_query": "{bad-json"}
    )

    with pytest.raises(SuspiciousOperation):
        admin_instance.get_queryset(request)


@pytest.mark.django_db
def test_admin_mixin_rejects_disallowed_lookup_from_admin_configuration() -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = ["email"]
        advanced_search_lookups = ["exact"]

    admin_instance = PersonAdmin(Person, admin.site)

    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {"field": "email", "operator": "__icontains", "value": "example.com"}
        ],
        "groups": [],
        "negated": False,
    }
    request = RequestFactory().get(
        "/admin/examples/person/", {"advanced_query": json.dumps(payload)}
    )

    with pytest.raises(SuspiciousOperation):
        admin_instance.get_queryset(request)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("_case", "field", "operator", "value", "expected_labels"),
    LOOKUP_FILTER_CASES,
)
def test_admin_mixin_supports_lookup_matrix_except_in_isnull_range(
    _case: str,
    field: str,
    operator: str,
    value: str,
    expected_labels: set[str],
) -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = [
            "first_name",
            "last_name",
            "email",
            "age",
            "date_of_birth",
        ]
        advanced_search_lookups = ["__all__"]

    admin_instance = PersonAdmin(Person, admin.site)

    maria = baker.make(
        Person,
        first_name="Maria",
        last_name="Petrova",
        age=30,
        email="maria@example.com",
        date_of_birth=date(1995, 1, 15),
    )
    marco = baker.make(
        Person,
        first_name="Marco",
        last_name="Johnson",
        age=35,
        email="marco@demo.org",
        date_of_birth=date(1991, 1, 20),
    )
    anna = baker.make(
        Person,
        first_name="Anna",
        last_name="Ivanova",
        age=25,
        email="anna@another.net",
        date_of_birth=date(1995, 5, 10),
    )

    people_by_label = {
        "maria": maria.id,
        "marco": marco.id,
        "anna": anna.id,
    }
    expected_ids = {people_by_label[label] for label in expected_labels}

    payload = {
        "logicalOperator": "AND",
        "conditions": [
            {"field": field, "operator": operator, "value": value},
        ],
        "groups": [],
        "negated": False,
    }

    request = RequestFactory().get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )

    result_ids = set(admin_instance.get_queryset(request).values_list("id", flat=True))
    assert result_ids == expected_ids


@pytest.mark.django_db
def test_admin_mixin_supports_alias_value_references() -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = ["age", "cars"]

    admin_instance = PersonAdmin(Person, admin.site)

    country = baker.make(Country, name="Germany")
    manufacturer = baker.make(Manufacturer, name="VW", country=country)
    golf = baker.make(
        Car,
        model="Golf",
        manufacturer=manufacturer,
        year=2020,
        price=Decimal("20000.00"),
        is_electric=False,
    )
    passat = baker.make(
        Car,
        model="Passat",
        manufacturer=manufacturer,
        year=2021,
        price=Decimal("25000.00"),
        is_electric=False,
    )

    younger = baker.make(Person, age=1)
    younger.cars.add(golf, passat)

    older = baker.make(Person, age=3)
    older.cars.add(golf, passat)

    payload = {
        "logicalOperator": "AND",
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
                "field": "age",
                "operator": "greater_than",
                "value": "count_cars",
                "negated": False,
                "isVariableOnly": False,
            },
        ],
        "groups": [],
        "negated": False,
    }

    request = RequestFactory().get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )

    result_ids = set(admin_instance.get_queryset(request).values_list("id", flat=True))
    assert result_ids == {older.id}


@pytest.mark.django_db
def test_admin_mixin_supports_scalar_alias_value_references() -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = ["age"]

    admin_instance = PersonAdmin(Person, admin.site)

    younger = baker.make(Person, age=10)
    middle = baker.make(Person, age=20)
    older = baker.make(Person, age=30)

    payload = {
        "logicalOperator": "AND",
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
                "value": "avg_age",
                "negated": False,
                "isVariableOnly": False,
            },
        ],
        "groups": [],
        "negated": False,
    }

    request = RequestFactory().get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )

    result_ids = set(admin_instance.get_queryset(request).values_list("id", flat=True))
    assert result_ids == {older.id}
    assert younger.id not in result_ids
    assert middle.id not in result_ids


@pytest.mark.django_db
def test_admin_mixin_rejects_unknown_alias_value_reference() -> None:
    class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        advanced_search_fields = ["age", "cars"]

    admin_instance = PersonAdmin(Person, admin.site)

    payload = {
        "logicalOperator": "AND",
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
                "field": "age",
                "operator": "greater_than",
                "value": "avvg_age",
                "negated": False,
                "isVariableOnly": False,
            },
        ],
        "groups": [],
        "negated": False,
    }

    request = RequestFactory().get(
        "/admin/examples/person/",
        {"advanced_query": json.dumps(payload)},
    )

    with pytest.raises(SuspiciousOperation, match="Unknown variable 'avvg_age'"):
        admin_instance.get_queryset(request)
