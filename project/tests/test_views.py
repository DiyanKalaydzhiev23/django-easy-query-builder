import pytest
from django.contrib import admin
from django.test import RequestFactory

from django_easy_query_builder.mixins import QueryBuilderAdminMixin
from examples.models import Person


@pytest.fixture
def admin_instance():
    class TestAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        query_builder_fields = ["first_name", "date_of_birth", "email"]

    return TestAdmin(Person, admin.site)


def test_get_query_builder_fields_mapping(admin_instance):
    fields = admin_instance.get_query_builder_fields_mapping()
    assert isinstance(fields, list)
    assert len(fields) == 3
    assert fields[0]["name"] == "first_name"
    assert fields[1]["name"] == "date_of_birth"
    assert fields[2]["name"] == "email"


def test_get_query_builder_fields_mapping_with_nested_relation():
    class TestAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        query_builder_fields = ["cars__manufacturer__country__name"]

    admin_instance = TestAdmin(Person, admin.site)
    fields = admin_instance.get_query_builder_fields_mapping()

    assert len(fields) == 1
    assert fields[0]["name"] == "cars.manufacturer.country.name"
    assert fields[0]["orm_path"] == "cars__manufacturer__country__name"


def test_get_query_builder_frontend_config(admin_instance):
    request = RequestFactory().get(
        "/admin/examples/person/",
        {
            "advanced_query": '{"logicalOperator":"AND","conditions":[],"groups":[],"negated":false}'
        },
    )

    config = admin_instance.get_query_builder_frontend_config(request)

    assert config["queryParam"] == "advanced_query"
    assert "first_name" in config["availableFields"]
    assert config["initialQuery"].startswith("{")
    assert config["enableTransforms"] is False
