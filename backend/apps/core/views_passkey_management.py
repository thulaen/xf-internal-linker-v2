"""Passkey management endpoints — list / relabel / delete.

These endpoints back the ``/preferences`` "Passkeys" card in the
Angular frontend. They cover the complement of ``views_passkey``:

    GET    /api/auth/passkey/credentials/         → list mine
    PATCH  /api/auth/passkey/credentials/<int:pk>/ → rename mine
    DELETE /api/auth/passkey/credentials/<int:pk>/ → delete mine

All three are ``IsAuthenticated``-gated and only ever touch
``request.user``'s own credentials. We never expose the raw
``credential_id`` or ``public_key`` bytes — those are only useful to
the assertion verifier and the operator (via Django admin).

Lockout safety: the delete endpoint refuses to remove the LAST
credential when the user has no usable password. That combination
would lock the user out of the account entirely, with no recovery
path short of operator intervention.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PasskeyCredential

# Mirrors the model field's max_length; defined locally so the view
# layer never silently widens the limit if the model is changed.
CREDENTIAL_LABEL_MAX_LEN = 100


def _serialize(credential: PasskeyCredential) -> dict:
    """Plain-dict shape returned to the frontend. No raw bytes."""
    transports = [t for t in (credential.transports or "").split(",") if t]
    return {
        "id": credential.pk,
        "label": credential.label or "",
        "transports": transports,
        "sign_count": credential.sign_count,
        "last_used_at": credential.last_used_at.isoformat() if credential.last_used_at else None,
        "created_at": credential.created_at.isoformat() if credential.created_at else None,
    }


def _sanitize_label(raw: str) -> str:
    """Strip control characters and clamp to model max length."""
    cleaned = "".join(ch for ch in (raw or "") if ch.isprintable())
    return cleaned.strip()[:CREDENTIAL_LABEL_MAX_LEN]


class PasskeyCredentialListView(APIView):
    """GET → list of the current user's enrolled passkeys."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        creds = PasskeyCredential.objects.filter(user=request.user).order_by(
            "-last_used_at", "-created_at"
        )
        return Response([_serialize(c) for c in creds])


class PasskeyCredentialDetailView(APIView):
    """PATCH (rename) and DELETE for a single credential the user owns."""

    permission_classes = [IsAuthenticated]

    def _get_owned(self, request, pk: int) -> PasskeyCredential | None:
        return PasskeyCredential.objects.filter(user=request.user, pk=pk).first()

    def patch(self, request, pk: int):
        credential = self._get_owned(request, pk)
        if credential is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        new_label = _sanitize_label(str(request.data.get("label") or ""))
        credential.label = new_label
        credential.save(update_fields=["label", "updated_at"])
        return Response(_serialize(credential))

    def delete(self, request, pk: int):
        credential = self._get_owned(request, pk)
        if credential is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Lockout safety: refuse to delete the last credential when
        # the user has no usable password (passkey is the only way in).
        is_last = (
            PasskeyCredential.objects.filter(user=request.user).count() == 1
        )
        if is_last and not request.user.has_usable_password():
            return Response(
                {
                    "detail": (
                        "Refusing to delete your only passkey — you would lock "
                        "yourself out of this account. Set a password first, "
                        "then come back to delete this credential."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        credential.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
