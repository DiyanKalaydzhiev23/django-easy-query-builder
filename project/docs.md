# Django Easy Query Builder

This is a Django app that allows you to build complex queries using a simple query language.

## Installation

To install the app, you can use pip:

```bash
pip install django-easy-query-builder
```

## Configuration

To configure the app in a Django project, you need to add it to the `INSTALLED_APPS` in your `settings.py` file:

```python
INSTALLED_APPS = [
    ...
    'django_easy_query_builder',
    ...
]
```

## Usage

To use the `QueryBuilderAdminMixin` in a `ModelAdmin`, you need to inherit from it and specify the `query_builder_fields` attribute.

```python
from django.contrib import admin
from .models import MyModel
from django_easy_query_builder.mixins import QueryBuilderAdminMixin

@admin.register(MyModel)
class MyModelAdmin(QueryBuilderAdminMixin, admin.ModelAdmin):
    query_builder_fields = ['field1', 'field2']
```

This will add a query builder to the changelist view of the `MyModel` admin.

## Query Language

The query language is a simple language that allows you to build complex queries using `Q` objects.

The following operators are supported:

*   `&`: AND
*   `|`: OR
*   `~`: NOT
*   `()`: Grouping

You can also use lookups in the query language, for example:

```
Q(field1__icontains='value')
```

## Validation

The queries are validated to ensure that only allowed fields and lookups are used.

The allowed lookups are:

*   `exact`
*   `iexact`
*   `in`
*   `gt`
*   `gte`
*   `lt`
*   `lte`
*   `contains`
*   `icontains`
*   `startswith`
*   `istartswith`
*   `endswith`
*   `iendswith`
*   `range`
*   `isnull`
*   `date`
*   `year`
*   `month`
*   `day`
*   `week_day`

## Future Development

*   Add support for more complex queries.
*   Add support for more lookups.
*   Add support for more field types.
*   Add the js client
*   Add more support for relations
*   Views to save search queries
*
