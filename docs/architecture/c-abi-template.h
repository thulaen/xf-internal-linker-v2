#ifndef XF_TEMPLATE_H
#define XF_TEMPLATE_H

#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#  define XF_API __declspec(dllexport)
#else
#  define XF_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
#  define XF_NOEXCEPT noexcept
extern "C" {
#else
#  define XF_NOEXCEPT
#endif

typedef uint32_t xf_status_t;

enum {
  XF_OK = 0,
  XF_INVALID_ARGUMENT = 1,
  XF_NOT_FOUND = 2,
  XF_CANCELLED = 3,
  XF_INTERNAL = 255
};

typedef struct xf_template_config {
  uint32_t abi_size;
  uint32_t abi_version;
  uint32_t flags;
} xf_template_config;

typedef struct xf_template_span {
  uint32_t abi_size;
  uint32_t abi_version;
  const uint8_t *data;
  size_t length;
} xf_template_span;

XF_API xf_status_t xf_template_create(
  const xf_template_config *config,
  void **handle
) XF_NOEXCEPT;

XF_API xf_status_t xf_template_destroy(void *handle) XF_NOEXCEPT;

XF_API const char *xf_template_last_error(void *handle) XF_NOEXCEPT;

#ifdef __cplusplus
}
#endif

#endif

