import json

import pytest
from django.contrib.auth import get_user_model

from django_easy_query_builder.models import View
from django_easy_query_builder.saved_views import build_query_hash


@pytest.fixture
def admin_client(client):
    user = get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin",
    )
    client.force_login(user)
    return client


def _first_name_equals_payload(value: str, suffix: str = "1") -> dict:
    return {
        "id": f"group-{suffix}",
        "logicalOperator": "AND",
        "operators": [],
        "negated": False,
        "conditions": [
            {
                "id": f"condition-{suffix}",
                "field": "first_name",
                "operator": "equals",
                "value": value,
                "negated": False,
                "isVariableOnly": False,
            }
        ],
        "groups": [],
    }


@pytest.mark.django_db
def test_save_query_view_creates_saved_view_for_current_model(admin_client) -> None:
    payload = _first_name_equals_payload("Maria")
    response = admin_client.post(
        "/admin/examples/person/save-query/",
        data=json.dumps({"name": "Maria Only", "query": payload}),
        content_type="application/json",
    )

    assert response.status_code == 201
    response_payload = response.json()
    assert response_payload["created"] is True

    saved = View.objects.get(model_label="examples.person")
    assert saved.name == "Maria Only"
    assert saved.query_hash == response_payload["queryHash"]
    assert saved.query_payload == payload


@pytest.mark.django_db
def test_save_query_view_rejects_duplicate_queries_even_with_different_ids(
    admin_client,
) -> None:
    first_payload = _first_name_equals_payload("Maria", suffix="a")
    duplicate_payload = _first_name_equals_payload("Maria", suffix="b")

    first_response = admin_client.post(
        "/admin/examples/person/save-query/",
        data=json.dumps({"name": "Maria 1", "query": first_payload}),
        content_type="application/json",
    )
    assert first_response.status_code == 201

    duplicate_response = admin_client.post(
        "/admin/examples/person/save-query/",
        data=json.dumps({"name": "Maria 2", "query": duplicate_payload}),
        content_type="application/json",
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["created"] is False
    assert View.objects.filter(model_label="examples.person").count() == 1


@pytest.mark.django_db
def test_changelist_frontend_config_contains_saved_query_hashes(admin_client) -> None:
    payload = _first_name_equals_payload("Maria")
    query_hash = build_query_hash(payload)
    View.objects.create(
        name="Maria",
        model_label="examples.person",
        query_hash=query_hash,
        query_payload=payload,
    )

    response = admin_client.get("/admin/examples/person/")
    assert response.status_code == 200
    config = response.context["query_builder_frontend_config"]

    assert config["saveQueryUrl"] == "/admin/examples/person/save-query/"
    assert query_hash in config["savedQueryHashes"]
    assert len(config["savedQueries"]) == 1
    assert config["savedQueries"][0]["name"] == "Maria"
    assert config["savedQueries"][0]["query_payload"] == payload


@pytest.mark.django_db
def test_save_query_view_updates_existing_view(admin_client) -> None:
    original_payload = _first_name_equals_payload("Maria", suffix="original")
    updated_payload = _first_name_equals_payload("Ivan", suffix="updated")
    saved = View.objects.create(
        name="People: Maria",
        model_label="examples.person",
        query_hash=build_query_hash(original_payload),
        query_payload=original_payload,
    )

    response = admin_client.post(
        "/admin/examples/person/save-query/",
        data=json.dumps(
            {
                "name": "People: Ivan",
                "query": updated_payload,
                "mode": "update",
                "viewId": saved.id,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == saved.id
    assert payload["updated"] is True
    assert payload["created"] is False

    saved.refresh_from_db()
    assert saved.name == "People: Ivan"
    assert saved.query_hash == build_query_hash(updated_payload)
    assert saved.query_payload == updated_payload


@pytest.mark.django_db
def test_save_query_view_update_conflict_returns_409(admin_client) -> None:
    first_payload = _first_name_equals_payload("Maria", suffix="first")
    second_payload = _first_name_equals_payload("Ivan", suffix="second")
    first_view = View.objects.create(
        name="People: Maria",
        model_label="examples.person",
        query_hash=build_query_hash(first_payload),
        query_payload=first_payload,
    )
    second_view = View.objects.create(
        name="People: Ivan",
        model_label="examples.person",
        query_hash=build_query_hash(second_payload),
        query_payload=second_payload,
    )

    response = admin_client.post(
        "/admin/examples/person/save-query/",
        data=json.dumps(
            {
                "name": "Conflicting update",
                "query": second_payload,
                "mode": "update",
                "viewId": first_view.id,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["id"] == second_view.id
    assert payload["updated"] is False
    assert payload["created"] is False

    first_view.refresh_from_db()
    assert first_view.name == "People: Maria"
    assert first_view.query_hash == build_query_hash(first_payload)
