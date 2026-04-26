#pragma once

#include <cstddef>
#include <cstdint>
#include <random>
#include <string>
#include <unordered_set>
#include <vector>

namespace xf_bench {

inline std::vector<float> random_floats(std::size_t n, unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
  std::vector<float> v(n);
  for (auto &x : v)
    x = dist(gen);
  return v;
}

inline std::vector<double> random_doubles(std::size_t n, unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::uniform_real_distribution<double> dist(-1.0, 1.0);
  std::vector<double> v(n);
  for (auto &x : v)
    x = dist(gen);
  return v;
}

inline std::vector<int32_t> random_int32s(std::size_t n, int32_t lo, int32_t hi,
                                          unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::uniform_int_distribution<int32_t> dist(lo, hi);
  std::vector<int32_t> v(n);
  for (auto &x : v)
    x = dist(gen);
  return v;
}

inline std::vector<uint32_t> random_uint32s(std::size_t n, uint32_t lo,
                                            uint32_t hi, unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::uniform_int_distribution<uint32_t> dist(lo, hi);
  std::vector<uint32_t> v(n);
  for (auto &x : v)
    x = dist(gen);
  return v;
}

inline std::vector<std::string>
random_tokens(std::size_t n, std::size_t max_len = 8, unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::uniform_int_distribution<int> char_dist('a', 'z');
  std::uniform_int_distribution<std::size_t> len_dist(2, max_len);
  std::vector<std::string> tokens(n);
  for (auto &t : tokens) {
    auto len = len_dist(gen);
    t.resize(len);
    for (auto &c : t)
      c = static_cast<char>(char_dist(gen));
  }
  return tokens;
}

inline std::unordered_set<std::string>
random_token_set(std::size_t n, std::size_t max_len = 8, unsigned seed = 42) {
  auto v = random_tokens(n, max_len, seed);
  return {v.begin(), v.end()};
}

inline std::string random_bbcode(std::size_t approx_len, unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::string result;
  result.reserve(approx_len);

  std::uniform_int_distribution<int> type_dist(0, 2);
  std::uniform_int_distribution<int> char_dist('a', 'z');

  while (result.size() < approx_len) {
    int link_type = type_dist(gen);
    std::string url = "https://example.com/";
    for (int i = 0; i < 10; ++i)
      url.push_back(static_cast<char>(char_dist(gen)));

    std::string anchor;
    for (int i = 0; i < 6; ++i)
      anchor.push_back(static_cast<char>(char_dist(gen)));

    if (link_type == 0) {
      result += "[url=" + url + "]" + anchor + "[/url] ";
    } else if (link_type == 1) {
      result += "<a href=\"" + url + "\">" + anchor + "</a> ";
    } else {
      result += url + " ";
    }

    /* Add some plain text between links */
    for (int i = 0; i < 20; ++i)
      result.push_back(static_cast<char>(char_dist(gen)));
    result.push_back(' ');
  }
  return result;
}

/* Generate a sparse CSR graph for pagerank benchmarks */
struct CsrGraph {
  std::vector<int32_t> indptr;
  std::vector<int32_t> indices;
  std::vector<double> data;
  std::vector<double> ranks;
  std::vector<bool> dangling;
  int node_count;
};

inline CsrGraph random_csr(int nodes, int avg_edges_per_node,
                           unsigned seed = 42) {
  std::mt19937 gen(seed);
  std::uniform_int_distribution<int> neighbor_dist(0, nodes - 1);
  std::uniform_int_distribution<int> degree_dist(0, avg_edges_per_node * 2);

  CsrGraph g;
  g.node_count = nodes;
  g.indptr.push_back(0);
  g.ranks.resize(static_cast<std::size_t>(nodes),
                 1.0 / static_cast<double>(nodes));
  g.dangling.resize(static_cast<std::size_t>(nodes), false);

  for (int row = 0; row < nodes; ++row) {
    int deg = degree_dist(gen);
    if (deg == 0) {
      g.dangling[static_cast<std::size_t>(row)] = true;
    }
    for (int e = 0; e < deg; ++e) {
      g.indices.push_back(neighbor_dist(gen));
      g.data.push_back(1.0 / static_cast<double>(deg));
    }
    g.indptr.push_back(static_cast<int32_t>(g.indices.size()));
  }
  return g;
}

} // namespace xf_bench
