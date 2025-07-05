import pytest
from django.contrib import admin
from django_easy_query_builder.mixins import QueryBuilderAdminMixin
from examples.models import Person


@pytest.fixture
def admin_instance():
    class TestAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
        model = Person
        query_builder_fields = ['first_name', 'date_of_birth', 'email']

    return TestAdmin(Person, admin.site)

def test_get_query_builder_fields_mapping(admin_instance):
    fields = admin_instance.get_query_builder_fields_mapping()
    assert isinstance(fields, list)
    assert len(fields) == 3
    assert fields[0]['name'] == 'first_name'
    assert fields[1]['name'] == 'date_of_birth'
    assert fields[2]['name'] == 'email'

