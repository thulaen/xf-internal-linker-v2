#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>

#include "../include/lesson_index.h"

namespace {

std::string fuzz_string(const uint8_t* data, size_t size, size_t offset) {
  if (offset >= size) {
    return {};
  }
  const size_t length = std::min<size_t>(size - offset, 64);
  return std::string(reinterpret_cast<const char*>(data + offset), length);
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (data == nullptr || size < 4) {
    return 0;
  }

  xf::lesson_index::ScopedLessonIndex lessons(16);
  xf::lesson_index::LessonRecord lesson{
      static_cast<std::uint64_t>(data[0]) + 1U,
      static_cast<std::uint64_t>(data[1]) * 31U,
      static_cast<std::uint8_t>(data[2] % 4U),
      static_cast<std::int64_t>(data[3]),
  };
  const std::string path = fuzz_string(data, size, 4);
  lessons.add(path, lesson);
  (void)lessons.find_by_path(path, 4);
  (void)lessons.remove(lesson.autoissue_id);

  xf::lesson_index::PerfBaselineCache baselines(16);
  xf::lesson_index::BaselineRecord baseline{1, 2, 3, 2, 1, 4};
  baselines.put(path, baseline);
  (void)baselines.get(path);
  (void)baselines.erase(path);

  xf::lesson_index::CitationCache citations(16);
  xf::lesson_index::CitationRecord citation{};
  citation.kind = 'u';
  citation.accessible = static_cast<std::uint8_t>(data[0] % 4U);
  citations.put(path, citation);
  (void)citations.get(path);
  (void)citations.erase(path);
  return 0;
}
