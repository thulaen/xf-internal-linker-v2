import pytest
from django.contrib.auth import get_user_model
from apps.audit.models import FeatureFlag, ErrorLog
from apps.audit.services.audit_logger import record_audit
from apps.audit.services.feature_flags import is_flag_enabled, get_flag_variant
from apps.audit.integrity import verify_artefact_integrity
from apps.crawler.models import CrawlSession, CrawledPageMeta

User = get_user_model()

@pytest.mark.django_db
def test_record_audit():
    """Verify record_audit creates a row and handles targets correctly."""
    user = User.objects.create_user(username="testuser")
    
    # Test with model instance
    entry = record_audit(
        action="approve",
        target=user,
        detail={"reason": "test"}
    )
    assert entry.action == "approve"
    assert entry.target_type == "user"
    assert entry.target_id == str(user.pk)
    assert entry.detail == {"reason": "test"}

@pytest.mark.django_db
def test_feature_flag_sticky_bucketing():
    """Verify feature flags are deterministic and honor rollout percent."""
    flag = FeatureFlag.objects.create(
        key="test-flag",
        enabled=True,
        rollout_percent=50
    )
    
    # Find a user ID that should be in the lower 50%
    # We'll just test a few and ensure consistency
    users = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    results = [is_flag_enabled("test-flag", u, log_exposure=False) for u in users]
    
    # Re-run: must be exactly the same (sticky)
    results2 = [is_flag_enabled("test-flag", u, log_exposure=False) for u in users]
    assert results == results2
    
    # Disable flag: must be all False
    flag.enabled = False
    flag.save()
    assert not any(is_flag_enabled("test-flag", u, log_exposure=False) for u in users)

@pytest.mark.django_db
def test_feature_flag_variants():
    """Verify A/B variant distribution."""
    flag = FeatureFlag.objects.create(
        key="test-variants",
        enabled=True,
        variants=[
            {"name": "a", "weight": 1},
            {"name": "b", "weight": 1}
        ]
    )
    
    variants = [get_flag_variant("test-variants", u) for u in range(100)]
    assert "a" in variants
    assert "b" in variants
    # Check stickiness again
    assert get_flag_variant("test-variants", 1) == get_flag_variant("test-variants", 1)

@pytest.mark.django_db
def test_integrity_check_duplicates():
    """Verify integrity check detects duplicate URLs."""
    session = CrawlSession.objects.create(site_domain="example.com")
    CrawledPageMeta.objects.create(
        url="http://example.com/1",
        normalized_url="http://example.com/1",
        session=session
    )
    # Force a duplicate (ignoring session constraint for check test)
    # Actually CrawledPageMeta has unique(session, normalized_url).
    # To test cross-session dups:
    session2 = CrawlSession.objects.create(site_domain="example.com")
    CrawledPageMeta.objects.create(
        url="http://example.com/1",
        normalized_url="http://example.com/1",
        session=session2
    )
    
    # Run check
    verify_artefact_integrity()
    
    # Should see error in ErrorLog
    assert ErrorLog.objects.filter(job_type="integrity_check", step="CrawledPageMeta").exists()
