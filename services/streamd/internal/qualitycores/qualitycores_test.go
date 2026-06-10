package qualitycores

import "testing"

func TestQualityCoresDefaultUsesVisibleCPUs(t *testing.T) {
	t.Setenv("XF_QUALITY_CORES", "")
	result := QualityCores("go-test")
	if result.Workers != result.VisibleCPUs {
		t.Fatalf("workers=%d, want %d", result.Workers, result.VisibleCPUs)
	}
	if result.Source != "default" {
		t.Fatalf("source=%q, want default", result.Source)
	}
}

func TestQualityCoresClampsLargeOverride(t *testing.T) {
	t.Setenv("XF_QUALITY_CORES", "99999")
	result := QualityCores("go-test")
	if result.Workers != result.VisibleCPUs {
		t.Fatalf("workers=%d, want %d", result.Workers, result.VisibleCPUs)
	}
	if result.Source != "override-clamped" {
		t.Fatalf("source=%q, want override-clamped", result.Source)
	}
}

func TestQualityCoresUsesSmallOverride(t *testing.T) {
	t.Setenv("XF_QUALITY_CORES", "2")
	result := QualityCores("go-test")
	if result.Workers != 2 && result.VisibleCPUs >= 2 {
		t.Fatalf("workers=%d, want 2", result.Workers)
	}
	if result.Source != "override" && result.VisibleCPUs >= 2 {
		t.Fatalf("source=%q, want override", result.Source)
	}
}

func TestQualityCoresIgnoresInvalidOverride(t *testing.T) {
	t.Setenv("XF_QUALITY_CORES", "garbage")
	result := QualityCores("go-test")
	if result.Workers != result.VisibleCPUs {
		t.Fatalf("workers=%d, want %d", result.Workers, result.VisibleCPUs)
	}
	if result.Source != "default" {
		t.Fatalf("source=%q, want default", result.Source)
	}
}
