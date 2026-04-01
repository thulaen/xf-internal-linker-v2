#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cctype>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;

namespace {

constexpr const char* kBbcodeMethod = "bbcode_anchor";
constexpr const char* kHtmlMethod = "html_anchor";
constexpr const char* kBareMethod = "bare_url";

using RawMatch = std::tuple<std::string, std::string, std::string, int, int>;

char ascii_lower(char ch) {
    return static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
}

bool starts_with_ci(const std::string& text, size_t index, const std::string& needle) {
    if (index + needle.size() > text.size()) {
        return false;
    }
    for (size_t offset = 0; offset < needle.size(); ++offset) {
        if (ascii_lower(text[index + offset]) != ascii_lower(needle[offset])) {
            return false;
        }
    }
    return true;
}

size_t find_ci(const std::string& text, const std::string& needle, size_t start) {
    for (size_t index = start; index + needle.size() <= text.size(); ++index) {
        if (starts_with_ci(text, index, needle)) {
            return index;
        }
    }
    return std::string::npos;
}

bool span_overlaps(int start, int end, const std::vector<std::pair<int, int>>& occupied_spans) {
    for (const auto& [other_start, other_end] : occupied_spans) {
        if (start < other_end && end > other_start) {
            return true;
        }
    }
    return false;
}

std::string trim(const std::string& value) {
    size_t start = 0;
    while (start < value.size() && std::isspace(static_cast<unsigned char>(value[start]))) {
        ++start;
    }
    size_t end = value.size();
    while (end > start && std::isspace(static_cast<unsigned char>(value[end - 1]))) {
        --end;
    }
    return value.substr(start, end - start);
}

std::string html_unescape(const std::string& value) {
    std::string output;
    output.reserve(value.size());

    for (size_t index = 0; index < value.size(); ++index) {
        if (value[index] != '&') {
            output.push_back(value[index]);
            continue;
        }

        const size_t semicolon = value.find(';', index + 1);
        if (semicolon == std::string::npos) {
            output.push_back(value[index]);
            continue;
        }

        const std::string entity = value.substr(index + 1, semicolon - index - 1);
        if (entity == "amp") {
            output.push_back('&');
        } else if (entity == "lt") {
            output.push_back('<');
        } else if (entity == "gt") {
            output.push_back('>');
        } else if (entity == "quot") {
            output.push_back('"');
        } else if (entity == "apos" || entity == "#39") {
            output.push_back('\'');
        } else {
            output.append(value.substr(index, semicolon - index + 1));
        }
        index = semicolon;
    }

    return output;
}

std::string strip_markup(const std::string& value) {
    const std::string unescaped = html_unescape(value);
    std::string cleaned;
    cleaned.reserve(unescaped.size());

    for (size_t index = 0; index < unescaped.size(); ++index) {
        if (unescaped[index] == '<') {
            const size_t close = unescaped.find('>', index + 1);
            if (close != std::string::npos) {
                index = close;
                continue;
            }
        }
        if (unescaped[index] == '[') {
            const size_t close = unescaped.find(']', index + 1);
            if (close != std::string::npos) {
                index = close;
                continue;
            }
        }
        cleaned.push_back(unescaped[index]);
    }

    return trim(cleaned);
}

std::vector<RawMatch> find_urls_impl(const std::string& raw_bbcode) {
    std::vector<RawMatch> found_links;
    std::vector<std::pair<int, int>> occupied_spans;

    size_t index = 0;
    while (index < raw_bbcode.size()) {
        const size_t start = find_ci(raw_bbcode, "[url=", index);
        if (start == std::string::npos) {
            break;
        }
        const size_t url_end = raw_bbcode.find(']', start + 5);
        if (url_end == std::string::npos) {
            break;
        }
        const size_t close = find_ci(raw_bbcode, "[/url]", url_end + 1);
        if (close == std::string::npos) {
            break;
        }

        const int span_start = static_cast<int>(start);
        const int span_end = static_cast<int>(close + 6);
        occupied_spans.push_back({span_start, span_end});
        found_links.push_back({
            raw_bbcode.substr(start + 5, url_end - (start + 5)),
            strip_markup(raw_bbcode.substr(url_end + 1, close - (url_end + 1))),
            kBbcodeMethod,
            span_start,
            span_end,
        });
        index = close + 6;
    }

    index = 0;
    while (index < raw_bbcode.size()) {
        const size_t start = find_ci(raw_bbcode, "<a", index);
        if (start == std::string::npos) {
            break;
        }
        if (start + 2 < raw_bbcode.size()) {
            const char boundary = raw_bbcode[start + 2];
            if (!(std::isspace(static_cast<unsigned char>(boundary)) || boundary == '>')) {
                index = start + 2;
                continue;
            }
        }

        const size_t open_end = raw_bbcode.find('>', start + 2);
        if (open_end == std::string::npos) {
            break;
        }
        const size_t close = find_ci(raw_bbcode, "</a>", open_end + 1);
        if (close == std::string::npos) {
            index = open_end + 1;
            continue;
        }

        const int span_start = static_cast<int>(start);
        const int span_end = static_cast<int>(close + 4);
        if (span_overlaps(span_start, span_end, occupied_spans)) {
            index = close + 4;
            continue;
        }

        const std::string open_tag = raw_bbcode.substr(start, open_end - start + 1);
        std::string href_value;
        for (size_t tag_index = 0; tag_index < open_tag.size(); ++tag_index) {
            if (!starts_with_ci(open_tag, tag_index, "href")) {
                continue;
            }
            size_t cursor = tag_index + 4;
            while (cursor < open_tag.size() && std::isspace(static_cast<unsigned char>(open_tag[cursor]))) {
                ++cursor;
            }
            if (cursor >= open_tag.size() || open_tag[cursor] != '=') {
                continue;
            }
            ++cursor;
            while (cursor < open_tag.size() && std::isspace(static_cast<unsigned char>(open_tag[cursor]))) {
                ++cursor;
            }
            if (cursor >= open_tag.size() || (open_tag[cursor] != '"' && open_tag[cursor] != '\'')) {
                continue;
            }
            const char quote = open_tag[cursor];
            ++cursor;
            const size_t value_end = open_tag.find(quote, cursor);
            if (value_end == std::string::npos) {
                continue;
            }
            href_value = open_tag.substr(cursor, value_end - cursor);
            break;
        }

        if (!href_value.empty()) {
            occupied_spans.push_back({span_start, span_end});
            found_links.push_back({
                href_value,
                strip_markup(raw_bbcode.substr(open_end + 1, close - (open_end + 1))),
                kHtmlMethod,
                span_start,
                span_end,
            });
        }
        index = close + 4;
    }

    index = 0;
    while (index < raw_bbcode.size()) {
        bool is_http = starts_with_ci(raw_bbcode, index, "http://");
        bool is_https = starts_with_ci(raw_bbcode, index, "https://");
        if (!is_http && !is_https) {
            ++index;
            continue;
        }

        size_t end = index;
        while (end < raw_bbcode.size()) {
            const char ch = raw_bbcode[end];
            if (std::isspace(static_cast<unsigned char>(ch)) || ch == '[' || ch == ']' ||
                ch == '<' || ch == '>' || ch == '"' || ch == '\'') {
                break;
            }
            ++end;
        }

        const int span_start = static_cast<int>(index);
        const int span_end = static_cast<int>(end);
        if (!span_overlaps(span_start, span_end, occupied_spans)) {
            found_links.push_back({
                raw_bbcode.substr(index, end - index),
                "",
                kBareMethod,
                span_start,
                span_end,
            });
        }
        index = end;
    }

    std::sort(
        found_links.begin(),
        found_links.end(),
        [](const RawMatch& left, const RawMatch& right) {
            if (std::get<3>(left) != std::get<3>(right)) {
                return std::get<3>(left) < std::get<3>(right);
            }
            if (std::get<4>(left) != std::get<4>(right)) {
                return std::get<4>(left) < std::get<4>(right);
            }
            return std::get<2>(left) < std::get<2>(right);
        }
    );

    return found_links;
}

}  // namespace

std::vector<RawMatch> find_urls(const std::string& raw_bbcode) {
    if (raw_bbcode.empty()) {
        return {};
    }
    return find_urls_impl(raw_bbcode);
}

PYBIND11_MODULE(linkparse, m) {
    m.def(
        "find_urls",
        &find_urls,
        "Find BBCode anchors, HTML anchors, and bare URLs with overlap handling"
    );
}
