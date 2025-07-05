from django.contrib import admin

from django_easy_query_builder.mixins import QueryBuilderAdminMixin
from examples.models import Person


@admin.register(Person)
class PersonAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'age', 'email', 'date_of_birth']
    query_builder_fields = ['first_name', 'date_of_birth', 'email']