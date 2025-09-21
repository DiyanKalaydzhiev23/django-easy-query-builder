import os
from pprint import pprint

import django
from django.db.models import Q

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django.setup()

from django_easy_query_builder.builders import QueryBuilder
from django_easy_query_builder.parsers import QueryParser
from django_easy_query_builder.validators import QTreeValidator
from examples.models import Person

# Query for a specific person and their car's manufacturer
query = "Q(cars__manufacturer__country__name=Germany)"
parser = QueryParser(query)
tree = parser.parse()
print("PARSED TREE →", tree)
validator = QTreeValidator(
    ["first_name", "last_name", "cars__manufacturer__country__name"]
)
validator.validate(tree)
query_builder = QueryBuilder()
my_q = query_builder.build_q(tree)
original_q = Q(cars__manufacturer__country__name="Germany")
# Assuming there is only one John Doe with a Toyota
people = Person.objects.filter(my_q)
people_original = Person.objects.filter(original_q)
assert len(people) <= 1
pprint([p.__dict__ for p in people])
pprint([p.__dict__ for p in people_original])


# TODO: be able to search a car country by owner name
