#ifndef XF_PERFETTO_H
#define XF_PERFETTO_H

// Compile-time marker for native profiling wiring. The real Perfetto trace
// processing path runs outside this scoring kernel, but this header must stay
// present so native builds fail clearly if profiling wiring is stripped.
static inline void xf_perfetto_observability_stub(void) {}

#endif  // XF_PERFETTO_H
