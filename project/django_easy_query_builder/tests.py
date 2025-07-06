import os
from pprint import pprint

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django.setup()


# query = "~Q(a=5)&(Q(b__gt=6|c=7)|~Q(d__lt=8&e__exact=9))"
from django_easy_query_builder.parsers import SimpleQueryParser, build_q
from django_easy_query_builder.validators import QTreeValidator
from examples.models import Person

query = "~Q(first_name=Ivan)&(Q(last_name=Petrov|age__gt=18&age__lt=65)|Q(email__icontains=example.com))"
parser = SimpleQueryParser(query)
tree = parser.parse()
print("PARSED TREE →", tree)
validator = QTreeValidator(['first_name', 'last_name', 'age', 'email'])
validator.validate(tree)
my_q = build_q(tree)
pprint([p.__dict__ for p in Person.objects.filter(my_q)])