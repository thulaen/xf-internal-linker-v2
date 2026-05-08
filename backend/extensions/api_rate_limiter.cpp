// FR-250 — Unified token-bucket rate limiter for outbound analytics API
// calls (GSC, GA4, Matomo, XenForo, WordPress). Spec: docs/specs/fr250-api-rate-limiter.md
//
// Algorithm: Turner 1986 "New directions in communications" (IEEE
// Communications). PARITY reference: backend/apps/sources/token_bucket.py
//
// Concurrency: per-bucket std::mutex; per CPP-RULES line 72 the GIL is
// released for every Python-facing method (py::call_guard) so we never
// hold a C++ mutex while Python is doing anything.
//
// Function-length cap: every method ≤50 lines (CLAUDE.md
// THINK-BEFORE-YOU-CODE).

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace {

using clock_t_ = std::chrono::steady_clock;

// Monotonic-clock nanoseconds since process start. Wrapped in a helper
// because the standard library's spelling is verbose enough to warrant it.
std::uint64_t now_ns() {
    const auto t = clock_t_::now().time_since_epoch();
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t).count());
}

struct Bucket {
    double tokens;             // current available tokens
    std::uint64_t last_refill; // monotonic ns
    double capacity;           // max tokens (burst)
    double rate_per_sec;       // refill rate
    std::int64_t daily_remaining;  // -1 = disabled
    std::uint64_t daily_reset_ns;  // when the daily counter resets
    std::int64_t daily_quota;      // initial value, used at reset
    std::mutex mu;             // per-bucket lock; protects all fields
};

}  // namespace

class RateLimiterRegistry {
public:
    // Register or replace a bucket. Replacing resets tokens to capacity —
    // the old token count would otherwise over- or under-count against the
    // new rate. PARITY: matches Python ``InMemoryBucketRegistry.register``.
    void register_bucket(const std::string& name, double capacity,
                         double rate_per_sec, std::int64_t daily_quota) {
        if (capacity <= 0.0 || rate_per_sec <= 0.0) {
            throw std::invalid_argument("capacity and rate must be positive");
        }
        std::lock_guard<std::mutex> g(registry_mu_);
        auto& slot = buckets_[name];
        if (!slot) {
            slot = std::make_unique<Bucket>();
        }
        std::lock_guard<std::mutex> bg(slot->mu);
        slot->tokens = capacity;
        slot->last_refill = now_ns();
        slot->capacity = capacity;
        slot->rate_per_sec = rate_per_sec;
        slot->daily_quota = daily_quota;
        slot->daily_remaining = daily_quota;  // -1 propagates through
        slot->daily_reset_ns = next_midnight_ns_(slot->last_refill);
    }

    // Remove cost tokens immediately if available. Returns true on success.
    // PARITY: matches Python ``try_acquire``.
    bool try_acquire(const std::string& name, double cost) {
        if (cost <= 0.0) {
            throw std::invalid_argument("cost must be > 0");
        }
        Bucket* b = locate_(name);
        std::lock_guard<std::mutex> g(b->mu);
        const auto now = now_ns();
        refill_(*b, now);
        if (b->daily_remaining == 0) {
            return false;  // quota exhausted; reset will happen on its own
        }
        if (b->tokens < cost) {
            return false;
        }
        b->tokens -= cost;
        if (b->daily_remaining > 0) {
            b->daily_remaining -= 1;
        }
        return true;
    }

    // Seconds until cost tokens can be acquired. 0.0 means now.
    // PARITY: derived from Python ``deficit / tokens_per_second``.
    double wait_seconds(const std::string& name, double cost) {
        if (cost <= 0.0) {
            throw std::invalid_argument("cost must be > 0");
        }
        Bucket* b = locate_(name);
        std::lock_guard<std::mutex> g(b->mu);
        const auto now = now_ns();
        refill_(*b, now);
        if (b->daily_remaining == 0) {
            const auto until = b->daily_reset_ns > now ? b->daily_reset_ns - now : 0;
            return static_cast<double>(until) / 1e9;
        }
        if (b->tokens >= cost) {
            return 0.0;
        }
        return (cost - b->tokens) / b->rate_per_sec;
    }

    // Refill + return current token count.
    double available(const std::string& name) {
        Bucket* b = locate_(name);
        std::lock_guard<std::mutex> g(b->mu);
        refill_(*b, now_ns());
        return b->tokens;
    }

    // Refill + return remaining daily quota (-1 if disabled).
    std::int64_t daily_remaining(const std::string& name) {
        Bucket* b = locate_(name);
        std::lock_guard<std::mutex> g(b->mu);
        refill_(*b, now_ns());
        return b->daily_remaining;
    }

    // Test-only: reset every bucket back to its initial config.
    void reset_all() {
        std::lock_guard<std::mutex> g(registry_mu_);
        for (auto& [name, slot] : buckets_) {
            std::lock_guard<std::mutex> bg(slot->mu);
            slot->tokens = slot->capacity;
            slot->last_refill = now_ns();
            slot->daily_remaining = slot->daily_quota;
            slot->daily_reset_ns = next_midnight_ns_(slot->last_refill);
        }
    }

private:
    // Look up an existing bucket; throw if not registered. Callers should
    // call register_bucket() during app startup. We deliberately do NOT
    // auto-create with a conservative default like the Python reference
    // does — for outbound API calls we'd rather fail loudly than silently
    // throttle to 1 req/s.
    Bucket* locate_(const std::string& name) {
        std::lock_guard<std::mutex> g(registry_mu_);
        auto it = buckets_.find(name);
        if (it == buckets_.end()) {
            throw std::out_of_range("bucket not registered: " + name);
        }
        return it->second.get();
    }

    // Advance b.tokens for the time elapsed since last_refill.
    // PARITY: ``elapsed * rate``, capped at capacity.
    void refill_(Bucket& b, std::uint64_t now) {
        if (now > b.daily_reset_ns) {
            b.daily_remaining = b.daily_quota;
            b.daily_reset_ns = next_midnight_ns_(now);
        }
        if (now <= b.last_refill) {
            return;
        }
        const double elapsed_s = static_cast<double>(now - b.last_refill) / 1e9;
        const double refill = elapsed_s * b.rate_per_sec;
        b.tokens = std::min(b.capacity, b.tokens + refill);
        b.last_refill = now;
    }

    // Next UTC midnight expressed in our monotonic-clock ns space.
    // We can't use system_clock for the threshold because monotonic_clock
    // and system_clock are independent — instead we offset from now by the
    // wall-clock seconds-until-midnight, in monotonic-ns.
    std::uint64_t next_midnight_ns_(std::uint64_t now_mono_ns) const {
        const auto wall = std::chrono::system_clock::now();
        const auto wall_t = std::chrono::system_clock::to_time_t(wall);
        std::tm utc{};
#if defined(_WIN32)
        gmtime_s(&utc, &wall_t);
#else
        gmtime_r(&wall_t, &utc);
#endif
        const long secs_today =
            static_cast<long>(utc.tm_hour) * 3600
            + static_cast<long>(utc.tm_min) * 60
            + static_cast<long>(utc.tm_sec);
        const long secs_until_midnight = 86400 - secs_today;
        return now_mono_ns
            + static_cast<std::uint64_t>(secs_until_midnight) * 1'000'000'000ULL;
    }

    std::unordered_map<std::string, std::unique_ptr<Bucket>> buckets_;
    std::mutex registry_mu_;  // protects buckets_ map (insert / lookup)
};

#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

PYBIND11_MODULE(api_rate_limiter, m) {
    m.doc() = "FR-250 — token-bucket rate limiter for GSC/GA4/Matomo/XF/WP";
    py::class_<RateLimiterRegistry>(m, "RateLimiterRegistry")
        .def(py::init<>())
        .def("register_bucket", &RateLimiterRegistry::register_bucket,
             py::arg("name"), py::arg("capacity"),
             py::arg("rate_per_sec"), py::arg("daily_quota") = -1,
             py::call_guard<py::gil_scoped_release>())
        .def("try_acquire", &RateLimiterRegistry::try_acquire,
             py::arg("name"), py::arg("cost") = 1.0,
             py::call_guard<py::gil_scoped_release>())
        .def("wait_seconds", &RateLimiterRegistry::wait_seconds,
             py::arg("name"), py::arg("cost") = 1.0,
             py::call_guard<py::gil_scoped_release>())
        .def("available", &RateLimiterRegistry::available,
             py::arg("name"), py::call_guard<py::gil_scoped_release>())
        .def("daily_remaining", &RateLimiterRegistry::daily_remaining,
             py::arg("name"), py::call_guard<py::gil_scoped_release>())
        .def("reset_all", &RateLimiterRegistry::reset_all,
             py::call_guard<py::gil_scoped_release>());
}
#endif
