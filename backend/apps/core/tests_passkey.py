"""Passkey tests — management endpoints + cleanup task + HEAD probe.

Plain-English: covers the bits we own (list / rename / delete +
challenge cleanup + the capability probe). The WebAuthn ceremonies
themselves (register/login begin/finish) are exercised by the
``webauthn`` library's own test suite — we only verify the wiring,
permission gating, and the lockout-safety rule.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.core.models import PasskeyChallenge, PasskeyCredential
from apps.core.tasks_passkey_cleanup import passkey_cleanup_expired_challenges


def _stub_credential(user, *, label="Stub", credential_id=b"\x00" * 16) -> PasskeyCredential:
    """Create a minimal PasskeyCredential row for permission tests.

    Real registration goes through the WebAuthn library; for management-
    endpoint tests we just need a row whose ``user`` and ``id`` we can
    address. The byte values don't matter to the views under test.
    """
    return PasskeyCredential.objects.create(
        user=user,
        credential_id=credential_id,
        public_key=b"\x00" * 32,
        sign_count=0,
        transports="internal",
        label=label,
    )


class PasskeyHeadProbeTests(APITestCase):
    """The frontend uses HEAD /api/auth/passkey/login/begin/ as a capability probe."""

    def test_head_probe_returns_200_anonymous(self):
        response = self.client.head("/api/auth/passkey/login/begin/")
        # 200 confirms the route is wired and the webauthn library is
        # installed. 503 is the documented "library missing" response.
        self.assertIn(response.status_code, {200, 503})


class PasskeyCredentialListViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="alice", password="aliceaa12345!")
        self.other = User.objects.create_user(username="bob", password="bobxxxx99988!")
        _stub_credential(self.user, label="Alice key", credential_id=b"\x01" * 16)
        _stub_credential(self.user, label="Alice backup", credential_id=b"\x02" * 16)
        _stub_credential(self.other, label="Bob key", credential_id=b"\x03" * 16)

    def test_anonymous_request_is_rejected(self):
        response = self.client.get("/api/auth/passkey/credentials/")
        # DRF returns 403 for unauthenticated requests against IsAuthenticated
        # views when no auth challenge header is set; 401 is acceptable too.
        self.assertIn(response.status_code, {401, 403})

    def test_lists_only_caller_credentials(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/auth/passkey/credentials/")
        self.assertEqual(response.status_code, 200)
        labels = sorted(row["label"] for row in response.json())
        self.assertEqual(labels, ["Alice backup", "Alice key"])

    def test_response_omits_raw_bytes(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/auth/passkey/credentials/")
        for row in response.json():
            self.assertNotIn("credential_id", row)
            self.assertNotIn("public_key", row)


class PasskeyCredentialDetailViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="claire", password="clairexx12345!")
        self.other = User.objects.create_user(username="dan", password="daneyy99988!")
        self.cred = _stub_credential(
            self.user, label="Old name", credential_id=b"\x10" * 16
        )
        self.other_cred = _stub_credential(
            self.other, label="Not yours", credential_id=b"\x11" * 16
        )

    def test_relabel_succeeds(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/auth/passkey/credentials/{self.cred.pk}/",
            {"label": "Friendly new name"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.label, "Friendly new name")

    def test_relabel_strips_control_characters(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/auth/passkey/credentials/{self.cred.pk}/",
            {"label": "Bad\x00name\x07"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.label, "Badname")

    def test_other_users_credential_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/auth/passkey/credentials/{self.other_cred.pk}/",
            {"label": "tampering"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.other_cred.refresh_from_db()
        self.assertEqual(self.other_cred.label, "Not yours")

    def test_delete_succeeds_when_user_has_password(self):
        self.client.force_login(self.user)
        response = self.client.delete(f"/api/auth/passkey/credentials/{self.cred.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PasskeyCredential.objects.filter(pk=self.cred.pk).exists())

    def test_delete_refuses_last_credential_when_password_unusable(self):
        # Lockout safety: deleting the only credential when there's no
        # usable password would lock the user out.
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.client.force_login(self.user)
        response = self.client.delete(f"/api/auth/passkey/credentials/{self.cred.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(PasskeyCredential.objects.filter(pk=self.cred.pk).exists())

    def test_delete_other_users_credential_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.delete(
            f"/api/auth/passkey/credentials/{self.other_cred.pk}/"
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PasskeyCredential.objects.filter(pk=self.other_cred.pk).exists())


class PasskeyCleanupTaskTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="erin", password="erinxx12345!")

    def test_deletes_only_expired_challenges(self):
        now = timezone.now()
        # Two expired, one fresh.
        PasskeyChallenge.objects.create(
            user=self.user,
            operation_type="register",
            challenge=b"a" * 32,
            expires_at=now - timedelta(minutes=10),
        )
        PasskeyChallenge.objects.create(
            user=self.user,
            operation_type="login",
            challenge=b"b" * 32,
            expires_at=now - timedelta(seconds=1),
        )
        PasskeyChallenge.objects.create(
            user=self.user,
            operation_type="login",
            challenge=b"c" * 32,
            expires_at=now + timedelta(minutes=5),
        )

        result = passkey_cleanup_expired_challenges.run()
        self.assertEqual(result, {"deleted_challenges": 2})
        self.assertEqual(PasskeyChallenge.objects.count(), 1)

    def test_zero_expired_returns_zero(self):
        result = passkey_cleanup_expired_challenges.run()
        self.assertEqual(result, {"deleted_challenges": 0})
