from django.contrib import admin

from django_easy_query_builder.mixins import AdvancedSearchAdminMixin
from examples.models import Person


@admin.register(Person)
class PersonAdmin(AdvancedSearchAdminMixin, admin.ModelAdmin):
    list_display = ["first_name", "last_name", "age", "email", "date_of_birth"]
    advanced_search_fields = [
        "first_name",
        "date_of_birth",
        "email",
        "cars__manufacturer__country__name",
    ]
    # Todo add all option for relations filtering
