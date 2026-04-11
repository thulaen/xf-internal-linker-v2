#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <mutex>

static constexpr std::size_t RING_SIZE = 1000;
static constexpr double WINDOW_SECS = 3600.0;

struct PulseEvent {
    double timestamp_epoch;
    int severity;
    double latency_ms;
    uint64_t items_count;
};

struct PulseSummary {
    int64_t total_events;
    int64_t events_last_hour;
    int64_t errors_last_hour;
    double error_rate;
    double avg_latency_ms;
    double throughput_per_min;
    const char* trend;
};

class PulseRing {
   public:
    PulseRing();
    void push(double ts, int severity, double latency_ms, uint64_t items);
    PulseSummary summary_raw() const;
    std::size_t size() const;

   private:
    double latest_ts() const;
    double oldest_ts_in_window(double cutoff) const;

    mutable std::mutex mu_;
    std::array<PulseEvent, RING_SIZE> events_;
    uint64_t head_ = 0;
    std::size_t count_ = 0;
};
