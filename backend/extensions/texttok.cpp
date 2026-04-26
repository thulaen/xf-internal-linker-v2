#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif
#include <string>
#include <unordered_set>
#include <vector>

#include "include/texttok_core.h"

namespace {

bool is_ascii_alnum(char ch) {
  return (ch >= '0' && ch <= '9') || (ch >= 'A' && ch <= 'Z') ||
         (ch >= 'a' && ch <= 'z');
}

char ascii_lower(char ch) {
  if (ch >= 'A' && ch <= 'Z') {
    return static_cast<char>(ch - 'A' + 'a');
  }
  return ch;
}

} // namespace

std::unordered_set<std::string>
tokenize_one_core(const std::string &text,
                  const std::unordered_set<std::string> &stopwords) {
  std::unordered_set<std::string> unique_tokens;
  const size_t text_size = text.size();
  size_t index = 0;

  while (index < text_size) {
    if (!is_ascii_alnum(text[index])) {
      ++index;
      continue;
    }

    std::string token;
    while (index < text_size && is_ascii_alnum(text[index])) {
      token.push_back(ascii_lower(text[index]));
      ++index;
    }

    if (index + 1 < text_size && text[index] == '\'' &&
        is_ascii_alnum(text[index + 1])) {
      token.push_back('\'');
      ++index;
      while (index < text_size && is_ascii_alnum(text[index])) {
        token.push_back(ascii_lower(text[index]));
        ++index;
      }
    }

    if (!token.empty() && stopwords.find(token) == stopwords.end()) {
      unique_tokens.insert(token);
    }
  }

  return unique_tokens;
}

std::vector<std::unordered_set<std::string>>
tokenize_text_batch_core(const std::vector<std::string> &texts,
                         const std::unordered_set<std::string> &stopwords) {
  std::vector<std::unordered_set<std::string>> results;
  results.reserve(texts.size());
  for (const auto &text : texts) {
    results.push_back(tokenize_one_core(text, stopwords));
  }
  return results;
}

#ifndef XF_BENCH_MODE
py::list tokenize_text_batch(const std::vector<std::string> &texts,
                             const py::iterable &stopwords) {
  std::unordered_set<std::string> stopword_lookup;
  stopword_lookup.reserve(py::len(stopwords));
  for (const auto &item : stopwords) {
    stopword_lookup.insert(py::cast<std::string>(item));
  }

  py::list results;
  for (const auto &text : texts) {
    auto tokens = tokenize_one_core(text, stopword_lookup);
    py::set token_set;
    for (const auto &token : tokens) {
      token_set.add(py::str(token));
    }
    results.append(py::frozenset(token_set));
  }
  return results;
}

PYBIND11_MODULE(texttok, m) {
  m.def("tokenize_text_batch", &tokenize_text_batch,
        "Tokenize texts into lowercase frozensets with stopword filtering");
}
#endif
