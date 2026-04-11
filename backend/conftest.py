"""
Shared pytest fixtures for the entire backend test suite.

These fixtures are automatically available in every test file.
Add project-wide fixtures here; app-specific fixtures belong
in each app's own conftest.py.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """A plain authenticated user with no special permissions."""
    return User.objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="testpassword123",
    )


@pytest.fixture
def admin_user(db):
    """A superuser for testing admin-only endpoints."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpassword123",
    )


@pytest.fixture
def api_client():
    """DRF APIClient, unauthenticated. Use .force_authenticate(user=...) as needed."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    """DRF APIClient pre-authenticated as the plain test user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """DRF APIClient pre-authenticated as the admin superuser."""
    api_client.force_authenticate(user=admin_user)
    return api_client
