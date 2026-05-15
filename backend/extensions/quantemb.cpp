#ifndef XF_BENCH_MODE
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#endif

#include <stddef.h>
#include <stdint.h>

#include <algorithm>
#include <limits>
#include <vector>

#include "include/quantemb_core.h"

#ifndef XF_BENCH_MODE
namespace py = pybind11;
#endif

/**
 * Perform OPQ encoding.
 * 1. Rotation: V' = V * R
 * 2. PQ: Find nearest centroid for each subvector
 */
void c_opq_encode(const float* vectors_ptr, size_t num_vectors, size_t dim,
                  const float* rotation_ptr, const float* codebooks_ptr,
                  size_t m, size_t k, uint8_t* out_codes) {
  size_t sub_dim = dim / m;

  for (size_t v_idx = 0; v_idx < num_vectors; ++v_idx) {
    const float* v_in = vectors_ptr + (v_idx * dim);
    std::vector<float> v_rot(dim, 0.0f);

    // 1. Apply Rotation
    for (size_t j = 0; j < dim; ++j) {
      float sum = 0.0f;
      for (size_t i = 0; i < dim; ++i) {
        sum += v_in[i] * rotation_ptr[i * dim + j];
      }
      v_rot[j] = sum;
    }

    // 2. PQ Encoding
    for (size_t m_idx = 0; m_idx < m; ++m_idx) {
      const float* sub_v = v_rot.data() + (m_idx * sub_dim);
      float min_dist = 1e30f;
      uint8_t best_k = 0;

      for (size_t k_idx = 0; k_idx < k; ++k_idx) {
        const float* centroid =
            codebooks_ptr + (m_idx * k * sub_dim) + (k_idx * sub_dim);
        float dist = 0.0f;
        for (size_t d = 0; d < sub_dim; ++d) {
          float diff = sub_v[d] - centroid[d];
          dist += diff * diff;
        }

        if (dist < min_dist) {
          min_dist = dist;
          best_k = (uint8_t)k_idx;
        }
      }
      out_codes[v_idx * m + m_idx] = best_k;
    }
  }
}

namespace {
float subvector_distance(const float* vector_ptr, const float* centroid_ptr,
                         size_t sub_dim) {
  float dist = 0.0f;
  for (size_t d = 0; d < sub_dim; ++d) {
    const float diff = vector_ptr[d] - centroid_ptr[d];
    dist += diff * diff;
  }
  return dist;
}

void fill_identity_rotation(size_t dim, float* rotation_ptr) {
  std::fill(rotation_ptr, rotation_ptr + (dim * dim), 0.0f);
  for (size_t idx = 0; idx < dim; ++idx) {
    rotation_ptr[(idx * dim) + idx] = 1.0f;
  }
}

void initialise_codebooks(const float* vectors_ptr, size_t num_vectors,
                          size_t dim, size_t m, size_t k,
                          float* codebooks_ptr) {
  const size_t sub_dim = dim / m;
  for (size_t m_idx = 0; m_idx < m; ++m_idx) {
    for (size_t k_idx = 0; k_idx < k; ++k_idx) {
      const size_t vector_idx = k_idx % num_vectors;
      const float* src = vectors_ptr + (vector_idx * dim) + (m_idx * sub_dim);
      float* dest = codebooks_ptr + (m_idx * k * sub_dim) + (k_idx * sub_dim);
      std::copy(src, src + sub_dim, dest);
    }
  }
}

size_t nearest_centroid(const float* sub_vector, const float* centroids,
                        size_t k, size_t sub_dim) {
  size_t best_idx = 0;
  float best_dist = std::numeric_limits<float>::max();
  for (size_t k_idx = 0; k_idx < k; ++k_idx) {
    const float* centroid = centroids + (k_idx * sub_dim);
    const float dist = subvector_distance(sub_vector, centroid, sub_dim);
    if (dist < best_dist) {
      best_dist = dist;
      best_idx = k_idx;
    }
  }
  return best_idx;
}

void refine_one_subquantizer(const float* vectors_ptr, size_t num_vectors,
                             size_t dim, size_t m_idx, size_t k, size_t sub_dim,
                             float* centroids) {
  std::vector<float> sums(k * sub_dim, 0.0f);
  std::vector<size_t> counts(k, 0);
  for (size_t v_idx = 0; v_idx < num_vectors; ++v_idx) {
    const float* sub_vector = vectors_ptr + (v_idx * dim) + (m_idx * sub_dim);
    const size_t best_idx = nearest_centroid(sub_vector, centroids, k, sub_dim);
    counts[best_idx] += 1;
    float* sum = sums.data() + (best_idx * sub_dim);
    for (size_t d = 0; d < sub_dim; ++d) {
      sum[d] += sub_vector[d];
    }
  }
  for (size_t k_idx = 0; k_idx < k; ++k_idx) {
    if (counts[k_idx] == 0) continue;
    float* centroid = centroids + (k_idx * sub_dim);
    const float* sum = sums.data() + (k_idx * sub_dim);
    const float inv_count = 1.0f / static_cast<float>(counts[k_idx]);
    for (size_t d = 0; d < sub_dim; ++d) {
      centroid[d] = sum[d] * inv_count;
    }
  }
}
}  // namespace

void c_opq_train_identity_kmeans(const float* vectors_ptr, size_t num_vectors,
                                 size_t dim, size_t m, size_t k, size_t n_iter,
                                 float* rotation_ptr, float* codebooks_ptr) {
  fill_identity_rotation(dim, rotation_ptr);
  initialise_codebooks(vectors_ptr, num_vectors, dim, m, k, codebooks_ptr);

  const size_t sub_dim = dim / m;
  const size_t passes = std::max<size_t>(n_iter, 1);
  for (size_t iter = 0; iter < passes; ++iter) {
    for (size_t m_idx = 0; m_idx < m; ++m_idx) {
      float* centroids = codebooks_ptr + (m_idx * k * sub_dim);
      refine_one_subquantizer(vectors_ptr, num_vectors, dim, m_idx, k, sub_dim,
                              centroids);
    }
  }
}

#ifndef XF_BENCH_MODE
/**
 * Python wrapper for opq_encode.
 * Expects:
 *   vectors: np.array((N, dim), dtype=float32)
 *   rotation: np.array((dim, dim), dtype=float32)
 *   codebooks: np.array((m, k, sub_dim), dtype=float32)
 * Returns: np.array((N, m), dtype=uint8)
 */
py::array_t<uint8_t> opq_encode(py::array_t<float> vectors,
                                py::array_t<float> rotation,
                                py::array_t<float> codebooks) {
  py::buffer_info v_info = vectors.request();
  py::buffer_info r_info = rotation.request();
  py::buffer_info cb_info = codebooks.request();

  if (v_info.ndim != 2) throw std::runtime_error("Vectors must be 2D");
  if (r_info.ndim != 2) throw std::runtime_error("Rotation must be 2D");
  if (cb_info.ndim != 3) throw std::runtime_error("Codebooks must be 3D");

  size_t num_vectors = (size_t)v_info.shape[0];
  size_t dim = (size_t)v_info.shape[1];
  size_t m = (size_t)cb_info.shape[0];
  size_t k = (size_t)cb_info.shape[1];
  size_t sub_dim = (size_t)cb_info.shape[2];

  if (dim != (size_t)r_info.shape[0] || dim != (size_t)r_info.shape[1])
    throw std::runtime_error("Rotation shape mismatch");
  if (dim != m * sub_dim)
    throw std::runtime_error("Codebook dimension mismatch");

  auto result =
      py::array_t<uint8_t>({(py::ssize_t)num_vectors, (py::ssize_t)m});
  py::buffer_info res_info = result.request();

  c_opq_encode(static_cast<const float*>(v_info.ptr), num_vectors, dim,
               static_cast<const float*>(r_info.ptr),
               static_cast<const float*>(cb_info.ptr), m, k,
               static_cast<uint8_t*>(res_info.ptr));

  return result;
}

py::tuple opq_train(
    py::array_t<float, py::array::c_style | py::array::forcecast> vectors,
    size_t m, size_t k, size_t n_iter) {
  py::buffer_info v_info = vectors.request();
  if (v_info.ndim != 2) throw std::runtime_error("Vectors must be 2D");
  if (v_info.shape[0] <= 0) throw std::runtime_error("Vectors cannot be empty");
  if (m == 0) throw std::runtime_error("M must be greater than zero");
  if (k == 0 || k > 256) {
    throw std::runtime_error("K must be between 1 and 256");
  }

  const size_t num_vectors = static_cast<size_t>(v_info.shape[0]);
  const size_t dim = static_cast<size_t>(v_info.shape[1]);
  if (dim == 0 || dim % m != 0) {
    throw std::runtime_error("Vector dimension must be divisible by M");
  }

  auto rotation = py::array_t<float>({(py::ssize_t)dim, (py::ssize_t)dim});
  auto codebooks = py::array_t<float>(
      {(py::ssize_t)m, (py::ssize_t)k, (py::ssize_t)(dim / m)});
  py::buffer_info r_info = rotation.request();
  py::buffer_info cb_info = codebooks.request();

  c_opq_train_identity_kmeans(
      static_cast<const float*>(v_info.ptr), num_vectors, dim, m, k, n_iter,
      static_cast<float*>(r_info.ptr), static_cast<float*>(cb_info.ptr));
  return py::make_tuple(rotation, codebooks);
}

PYBIND11_MODULE(quantemb, m) {
  m.doc() = "Vector quantization and OPQ kernels";
  m.def("opq_encode", &opq_encode, "Perform OPQ encoding on vectors");
  m.def("opq_train", &opq_train, "Train OPQ rotation and product quantizers");
}
#endif
