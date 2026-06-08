//! Adaptive worker-count policy for Rust quality wrappers.

#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::{env, fs, num::NonZeroUsize};

/// Worker policy result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QualityCores {
    /// Worker count selected for the tool.
    pub workers: usize,
    /// Selection source: default, override, override-clamped, or fallback.
    pub source: &'static str,
    /// Logical processors visible to this process.
    pub visible_cpus: usize,
    /// Normalised platform name used in quality logs.
    pub platform: &'static str,
}

fn platform_name() -> &'static str {
    if cfg!(target_os = "macos") {
        "darwin"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else {
        "linux"
    }
}

fn visible_cpus() -> usize {
    let count = std::thread::available_parallelism()
        .map(NonZeroUsize::get)
        .unwrap_or_else(|_| {
            eprintln!("[quality_cores] warning: cpu count unavailable; using 1");
            1
        });
    #[cfg(target_os = "linux")]
    {
        if let Some(quota) = linux_cgroup_quota_count() {
            return quota.min(count).max(1);
        }
    }
    count.max(1)
}

#[cfg(target_os = "linux")]
fn linux_cgroup_quota_count() -> Option<usize> {
    let raw = fs::read_to_string("/sys/fs/cgroup/cpu.max").ok()?;
    let mut parts = raw.split_whitespace();
    let quota = parts.next()?;
    let period = parts.next()?;
    if quota == "max" {
        return None;
    }
    let quota: usize = quota.parse().ok()?;
    let period: usize = period.parse().ok()?;
    if quota == 0 || period == 0 {
        return None;
    }
    Some((quota / period).max(1))
}

/// Return and log the adaptive worker count for one tool.
pub fn quality_cores(tool: &str) -> QualityCores {
    let visible = visible_cpus();
    let mut workers = visible;
    let mut source = "default";
    if let Ok(raw) = env::var("XF_QUALITY_CORES") {
        if !raw.is_empty() {
            match raw.parse::<usize>() {
                Ok(parsed) if parsed > 0 && parsed <= visible => {
                    workers = parsed;
                    source = "override";
                }
                Ok(parsed) if parsed > visible => {
                    workers = visible;
                    source = "override-clamped";
                    eprintln!(
                        "[quality_cores] warning: XF_QUALITY_CORES={parsed} clamped to visible_cpus={visible}"
                    );
                }
                _ => eprintln!("[quality_cores] warning: invalid XF_QUALITY_CORES='{raw}' ignored"),
            }
        }
    }
    let result = QualityCores {
        workers: workers.max(1),
        source,
        visible_cpus: visible,
        platform: platform_name(),
    };
    eprintln!(
        "[quality_cores] tool={tool} workers={} source={} visible_cpus={} platform={}",
        result.workers, result.source, result.visible_cpus, result.platform
    );
    result
}

#[cfg(test)]
mod tests {
    use super::quality_cores;
    use std::sync::Mutex;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn default_uses_visible_cpus() {
        let _guard = ENV_LOCK.lock().expect("env test lock poisoned");
        std::env::remove_var("XF_QUALITY_CORES");
        let result = quality_cores("cargo-test");
        assert_eq!(result.source, "default");
        assert!(result.workers >= 1);
        assert_eq!(result.workers, result.visible_cpus);
    }

    #[test]
    fn large_override_is_clamped() {
        let _guard = ENV_LOCK.lock().expect("env test lock poisoned");
        std::env::set_var("XF_QUALITY_CORES", "99999");
        let result = quality_cores("cargo-test");
        assert_eq!(result.source, "override-clamped");
        assert_eq!(result.workers, result.visible_cpus);
        std::env::remove_var("XF_QUALITY_CORES");
    }

    #[test]
    fn small_override_is_used() {
        let _guard = ENV_LOCK.lock().expect("env test lock poisoned");
        std::env::set_var("XF_QUALITY_CORES", "2");
        let result = quality_cores("cargo-test");
        if result.visible_cpus >= 2 {
            assert_eq!(result.source, "override");
            assert_eq!(result.workers, 2);
        }
        std::env::remove_var("XF_QUALITY_CORES");
    }

    #[test]
    fn invalid_override_falls_back_to_default() {
        let _guard = ENV_LOCK.lock().expect("env test lock poisoned");
        std::env::set_var("XF_QUALITY_CORES", "garbage");
        let result = quality_cores("cargo-test");
        assert_eq!(result.source, "default");
        assert_eq!(result.workers, result.visible_cpus);
        std::env::remove_var("XF_QUALITY_CORES");
    }
}
