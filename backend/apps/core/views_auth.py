"""
User profile, logout, and local setup views extracted from ``views_capacity.py``.
Part of the domain-driven decomposition to stay under the 1500-line cap.
"""

from __future__ import annotations

import logging

from django.conf import settings as django_settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class UserMeView(APIView):
    """Returns the currently authenticated user's profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "is_staff": request.user.is_staff,
                "date_joined": request.user.date_joined,
            }
        )


class UserLogoutView(APIView):
    """Deletes the user's auth token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Exception:
            logger.debug("Auth token delete failed or already gone", exc_info=True)
        return Response({"status": "success"})


class LocalVerificationBootstrapView(APIView):
    """Mint a localhost-only auth token for browser verification."""

    authentication_classes = []
    permission_classes = []
    VERIFICATION_HEADER = "HTTP_X_XFIL_VERIFICATION"
    _PLAYWRIGHT_USERNAME = "playwright-local"
    _PLAYWRIGHT_EMAIL = "playwright-local@example.invalid"

    def post(self, request):
        if not self._request_is_authorised(request):
            return Response({"detail": "Not found."}, status=404)

        from rest_framework.authtoken.models import Token

        user = self._get_or_repair_playwright_user()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})

    def _request_is_authorised(self, request) -> bool:
        if not getattr(django_settings, "LOCAL_VERIFICATION_BOOTSTRAP_ENABLED", False):
            return False
        if request.META.get(self.VERIFICATION_HEADER) != "playwright":
            return False
        peer_ip = request.META.get("REMOTE_ADDR", "")
        return peer_ip in {"127.0.0.1", "::1"}

    def _get_or_repair_playwright_user(self):
        from django.contrib.auth import get_user_model
        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=self._PLAYWRIGHT_USERNAME,
            defaults={
                "email": self._PLAYWRIGHT_EMAIL,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        fields_to_update: list[str] = []
        if not user.is_staff:
            user.is_staff = True
            fields_to_update.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            fields_to_update.append("is_superuser")
        if user.email != self._PLAYWRIGHT_EMAIL:
            user.email = self._PLAYWRIGHT_EMAIL
            fields_to_update.append("email")
        if user.has_usable_password():
            user.set_unusable_password()
            fields_to_update.append("password")
        if fields_to_update:
            user.save(update_fields=fields_to_update)
        return user


def _client_is_local_setup_request(request) -> bool:
    peer_ip = request.META.get("REMOTE_ADDR", "")
    forwarded_for = (
        (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    )
    if peer_ip in {"127.0.0.1", "::1"}:
        return True
    return peer_ip.startswith("172.") and forwarded_for in {"127.0.0.1", "::1"}


class FirstOperatorSetupView(APIView):
    """Create the first local operator account when the user table is empty."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.contrib.auth import get_user_model
        available = (
            _client_is_local_setup_request(request)
            and not get_user_model().objects.exists()
        )
        return Response({"available": available, "username": "admin"})

    def post(self, request):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        from rest_framework.authtoken.models import Token

        if not _client_is_local_setup_request(request):
            return Response({"detail": "Not found."}, status=404)

        user_model = get_user_model()
        if user_model.objects.exists():
            return Response({"detail": "First operator setup is already closed."}, status=404)

        username = str(request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "")
        email = str(request.data.get("email") or "admin@example.com").strip()
        if username != "admin":
            return Response({"detail": "The first operator username must be admin."}, status=400)
        if not password:
            return Response({"detail": "Password is required."}, status=400)
        try:
            validate_password(password)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)

        user = user_model.objects.create_superuser(
            username=username, email=email, password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})
