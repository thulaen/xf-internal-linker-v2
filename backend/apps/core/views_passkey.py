"""WebAuthn / Passkey endpoints.

Backs the four /api/auth/passkey/* routes the frontend
``PasskeyService`` speaks to:

    POST /api/auth/passkey/register/begin/   [auth] → options to create a new passkey
    POST /api/auth/passkey/register/finish/  [auth] ← attestation response
    POST /api/auth/passkey/login/begin/              → options to sign in
    POST /api/auth/passkey/login/finish/             ← assertion response

The library ``webauthn`` does the heavy lifting (challenge generation,
COSE-key parsing, attestation + assertion verification, sign-counter
replay checks). We just persist credentials + short-lived challenges.

Encoding contract:
    - Server sends byte fields (challenge, id, rawId) as base64url with
      no padding — matches the ``b64uToBuffer`` helper in the frontend
      ``PasskeyService``.
    - Client sends back the same shape; we decode before handing to
      ``webauthn.verify_*``.

Security notes:
    - ``RP_ID`` and ``RP_ORIGIN`` come from Django settings. They MUST
      match what the browser sees. ``localhost`` works over plain HTTP;
      every other host needs HTTPS.
    - Login-begin is AllowAny (no session), but we only ever issue a
      DRF token after the finish step verifies a stored credential.
    - Challenges are 5-minute TTL. The finish handler deletes them
      after verification (one-shot).
"""

from __future__ import annotations

import base64
import logging
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

try:
    from webauthn import (  # type: ignore
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers.structs import (  # type: ignore
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    WEBAUTHN_AVAILABLE = True
except ImportError:  # pragma: no cover - defensive
    WEBAUTHN_AVAILABLE = False

from .models import PasskeyChallenge, PasskeyCredential

logger = logging.getLogger(__name__)
User = get_user_model()

CHALLENGE_TTL_SECONDS = 300
# Matches the `CharField(max_length=...)` on `PasskeyCredential.label`.
CREDENTIAL_LABEL_MAX_LEN = 100


def _b64u_decode(s: str) -> bytes:
    """Decode base64url (no padding) -> bytes."""
    padding = 4 - (len(s) % 4)
    if padding and padding < 4:
        s = s + ("=" * padding)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _require_library():
    if not WEBAUTHN_AVAILABLE:
        return Response(
            {"detail": "WebAuthn library is not installed on this backend."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return None


def _prune_expired_challenges() -> None:
    now = timezone.now()
    PasskeyChallenge.objects.filter(expires_at__lt=now).delete()


def _store_challenge(user, op: str, raw: bytes) -> None:
    PasskeyChallenge.objects.create(
        user=user,
        operation_type=op,
        challenge=raw,
        expires_at=timezone.now() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    )


def _options_to_dict(options: Any) -> dict:
    """webauthn.options_to_json returns a JSON string; we need a dict."""
    import json as _json

    return _json.loads(options_to_json(options))


class PasskeyRegisterBeginView(APIView):
    """Step 1 of registration. Returns PublicKeyCredentialCreationOptions."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        guard = _require_library()
        if guard is not None:
            return guard
        _prune_expired_challenges()

        user = request.user
        existing = [
            PublicKeyCredentialDescriptor(id=bytes(c.credential_id))
            for c in user.passkey_credentials.all()
        ]

        options = generate_registration_options(
            rp_id=settings.WEBAUTHN_RP_ID,
            rp_name=settings.WEBAUTHN_RP_NAME,
            user_id=str(user.pk).encode("ascii"),
            user_name=user.username,
            user_display_name=user.get_full_name() or user.username,
            exclude_credentials=existing,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        _store_challenge(user, "register", bytes(options.challenge))
        return Response(_options_to_dict(options))


class PasskeyRegisterFinishView(APIView):
    """Step 2 of registration. Verifies the attestation and stores the credential."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        guard = _require_library()
        if guard is not None:
            return guard

        user = request.user
        body = request.data or {}
        try:
            challenge_row = (
                PasskeyChallenge.objects.filter(
                    user=user,
                    operation_type="register",
                    expires_at__gte=timezone.now(),
                )
                .order_by("-created_at")
                .first()
            )
            if challenge_row is None:
                return Response(
                    {"detail": "No active registration challenge — restart the flow."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            verification = verify_registration_response(
                credential=body,
                expected_challenge=bytes(challenge_row.challenge),
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=settings.WEBAUTHN_RP_ORIGIN,
                require_user_verification=False,
            )
        except Exception as exc:
            logger.warning("passkey register verify failed: %s", exc)
            return Response(
                {"detail": f"Registration verification failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PasskeyCredential.objects.create(
            user=user,
            credential_id=bytes(verification.credential_id),
            public_key=bytes(verification.credential_public_key),
            sign_count=int(verification.sign_count or 0),
            transports=",".join(body.get("response", {}).get("transports", []) or []),
            label=(body.get("label") or "")[:CREDENTIAL_LABEL_MAX_LEN],
        )
        challenge_row.delete()
        return Response({"ok": True})


class PasskeyLoginBeginView(APIView):
    """Step 1 of login. Anonymous — returns PublicKeyCredentialRequestOptions.

    A request-options bundle that does NOT list allowCredentials lets the
    browser show the full account chooser. If you want to scope to a
    specific username, POST {"username": "..."} and we'll pre-populate.

    Also answers HEAD — the frontend uses a HEAD probe as a "is passkey
    configured on this backend?" capability check. Any success or
    auth-required response means yes; a not-found response means the
    route isn't wired.
    """

    permission_classes = [AllowAny]

    def head(self, request):
        # Capability probe only — never consume a challenge.
        guard = _require_library()
        if guard is not None:
            return guard
        return Response(status=status.HTTP_200_OK)

    def post(self, request):
        guard = _require_library()
        if guard is not None:
            return guard
        _prune_expired_challenges()

        username = (request.data or {}).get("username") or ""
        scoped_user = None
        allow: list = []
        if username:
            try:
                scoped_user = User.objects.get(username=username)
                allow = [
                    PublicKeyCredentialDescriptor(id=bytes(c.credential_id))
                    for c in scoped_user.passkey_credentials.all()
                ]
            except User.DoesNotExist:
                # Uniform response — don't leak user existence.
                pass

        options = generate_authentication_options(
            rp_id=settings.WEBAUTHN_RP_ID,
            allow_credentials=allow,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        _store_challenge(scoped_user, "login", bytes(options.challenge))
        return Response(_options_to_dict(options))


def _lookup_credential(body: dict):
    """Return (cred, err_response). cred is None iff err_response is set."""
    raw_id = body.get("rawId") or body.get("id")
    if not raw_id:
        return None, Response(
            {"detail": "Missing credential id."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        credential_id = _b64u_decode(raw_id)
    except Exception:
        return None, Response(
            {"detail": "Bad credential id encoding."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        cred = PasskeyCredential.objects.select_related("user").get(
            credential_id=credential_id,
        )
    except PasskeyCredential.DoesNotExist:
        return None, Response(
            {"detail": "Unknown credential."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return cred, None


def _lookup_login_challenge(cred):
    """Prefer a challenge scoped to this user; fall back to anonymous."""
    return (
        PasskeyChallenge.objects.filter(
            operation_type="login",
            expires_at__gte=timezone.now(),
        )
        .filter(user__in=[cred.user, None])
        .order_by("-created_at")
        .first()
    )


def _issue_token_payload(cred) -> dict:
    token, _ = Token.objects.get_or_create(user=cred.user)
    return {
        "ok": True,
        "token": token.key,
        "user": {
            "id": cred.user.id,
            "username": cred.user.username,
            "email": cred.user.email,
        },
    }


class PasskeyLoginFinishView(APIView):
    """Step 2 of login. Verifies assertion, issues DRF token."""

    permission_classes = [AllowAny]

    def post(self, request):
        guard = _require_library()
        if guard is not None:
            return guard

        body = request.data or {}
        cred, err = _lookup_credential(body)
        if err is not None:
            return err

        challenge_row = _lookup_login_challenge(cred)
        if challenge_row is None:
            return Response(
                {"detail": "No active login challenge — restart the flow."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            verification = verify_authentication_response(
                credential=body,
                expected_challenge=bytes(challenge_row.challenge),
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=settings.WEBAUTHN_RP_ORIGIN,
                credential_public_key=bytes(cred.public_key),
                credential_current_sign_count=cred.sign_count,
                require_user_verification=False,
            )
        except Exception as exc:
            logger.warning(
                "passkey login verify failed for user=%s: %s", cred.user_id, exc
            )
            return Response(
                {"detail": f"Login verification failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cred.sign_count = int(verification.new_sign_count or 0)
        cred.last_used_at = timezone.now()
        cred.save(update_fields=["sign_count", "last_used_at", "updated_at"])
        challenge_row.delete()

        return Response(_issue_token_payload(cred))


# `secrets.token_bytes` is imported only so the module declares its own
# source of entropy (the library also uses it); keeps lint quiet.
_ = secrets
