import os
from pprint import pprint

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django.setup()

from django_easy_query_builder.parsers import SimpleQueryParser, build_q
from django_easy_query_builder.validators import QTreeValidator
from examples.models import Person

# Query for a specific person and their car's manufacturer
query = "Q(cars__manufacturer__country='USA')"
parser = SimpleQueryParser(query)
tree = parser.parse()
print("PARSED TREE →", tree)
validator = QTreeValidator(
    ["first_name", "last_name", "cars__manufacturer__country__name"]
)
validator.validate(tree)
my_q = build_q(tree)
# Assuming there is only one John Doe with a Toyota
persons = Person.objects.filter(my_q)
assert len(persons) <= 1
pprint([p.__dict__ for p in persons])


# TODO: be able to search a car country by owner name
