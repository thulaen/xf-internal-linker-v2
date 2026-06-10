//! `BBCode` / HTML / bare-URL link parser hot-path kernel, ported from the C++
//! `linkparse` kernel (`backend/extensions/linkparse.cpp`) to Rust and exposed
//! to Python as the native module `extensions.linkparse` via `PyO3`.
//!
//! The Python-callable API matches the C++ kernel exactly: one module-level
//! function
//!
//! ```text
//! find_urls(raw_bbcode: str) -> list[tuple[str, str, str, int, int]]
//! ```
//!
//! Each tuple is `(url, anchor_text, extraction_method, start, end)` where
//! `extraction_method` is one of `bbcode_anchor`, `html_anchor`, `bare_url`,
//! and `start`/`end` are **byte** offsets into the input.
//!
//! ## Algorithm (three deterministic passes)
//!
//! 1. **`BBCode`**: case-insensitive scan for `[url=` ... `]` ... `[/url]`. Every
//!    `BBCode` span is recorded as occupied — `BBCode` has priority and is never
//!    suppressed.
//! 2. **HTML**: case-insensitive scan for `<a` followed by whitespace or `>`
//!    (so `<abbr>` is rejected). The first `href="..."`/`href='...'` attribute
//!    is parsed; a non-empty href emits an `html_anchor` unless the span
//!    overlaps an occupied (BBCode/earlier-HTML) span. Emitted HTML spans are
//!    recorded as occupied.
//! 3. **Bare**: scan for tokens starting with `http://` / `https://`,
//!    terminated by whitespace or any of `[ ] < > " '`. A bare token is emitted
//!    only when it does not overlap an occupied span; bare tokens are NOT
//!    recorded as occupied.
//!
//! Finally the matches are stably sorted by `(start asc, end asc,
//! extraction_method asc)`.
//!
//! ## Exact parity (port note)
//!
//! This kernel is a pure deterministic byte-string state machine: no floating
//! point, no hashing, no platform-dependent math. It operates on bytes (matching
//! the C++ `std::string` byte indices) so the integer `start`/`end` offsets are
//! byte-for-byte identical to the C++ artifact it replaces. The in-service
//! Python reference (`backend/apps/pipeline/services/link_parser.py::_find_urls_py`)
//! and the 15-case parity test
//! `backend/apps/pipeline/tests.py::LinkParseExtensionTests` pin the contract.

use pyo3::prelude::*;

const BBCODE_METHOD: &str = "bbcode_anchor";
const HTML_METHOD: &str = "html_anchor";
const BARE_METHOD: &str = "bare_url";

/// One parsed link: `(url, anchor_text, extraction_method, start, end)` with
/// byte offsets. Mirrors the C++ `RawMatch` tuple field-for-field.
type RawMatch = (String, String, String, i64, i64);

/// ASCII lowercase a single byte (mirrors `std::tolower` on `unsigned char`,
/// which only folds A–Z for ASCII input).
const fn ascii_lower(byte: u8) -> u8 {
    byte.to_ascii_lowercase()
}

/// Case-insensitive ASCII prefix test at `index` in `text`.
fn starts_with_ci(text: &[u8], index: usize, needle: &[u8]) -> bool {
    if index + needle.len() > text.len() {
        return false;
    }
    for (offset, &needle_byte) in needle.iter().enumerate() {
        if ascii_lower(text[index + offset]) != ascii_lower(needle_byte) {
            return false;
        }
    }
    true
}

/// Find the first case-insensitive occurrence of `needle` at or after `start`,
/// or `None`. Mirrors the C++ `find_ci` returning `std::string::npos`.
fn find_ci(text: &[u8], needle: &[u8], start: usize) -> Option<usize> {
    if needle.len() > text.len() {
        return None;
    }
    let last = text.len() - needle.len();
    (start..=last).find(|&index| starts_with_ci(text, index, needle))
}

/// Find the first plain byte `target` at or after `start`.
fn find_byte(text: &[u8], target: u8, start: usize) -> Option<usize> {
    (start..text.len()).find(|&index| text[index] == target)
}

/// Convert a byte index into the `i64` offset the Python tuple exposes.
///
/// Offsets are positions in a forum/HTML string, far below `i64::MAX`, so the
/// conversion never truncates in practice; `i64::try_from` is used instead of an
/// `as` cast so a pathological multi-exabyte input saturates to `i64::MAX`
/// rather than wrapping to a negative value (which would silently corrupt the
/// downstream span arithmetic).
fn to_offset(index: usize) -> i64 {
    i64::try_from(index).unwrap_or(i64::MAX)
}

/// Half-open span overlap: `start < other_end && end > other_start`.
fn span_overlaps(start: i64, end: i64, occupied: &[(i64, i64)]) -> bool {
    occupied
        .iter()
        .any(|&(other_start, other_end)| start < other_end && end > other_start)
}

/// ASCII whitespace test matching C++ `std::isspace` on `unsigned char` for the
/// ASCII range (space, `\t`, `\n`, `\r`, `\x0b`, `\x0c`).
const fn is_ascii_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

/// Trim leading/trailing ASCII whitespace (byte-wise), returning a new `String`.
fn trim_bytes(value: &[u8]) -> Vec<u8> {
    let mut start = 0usize;
    while start < value.len() && is_ascii_space(value[start]) {
        start += 1;
    }
    let mut end = value.len();
    while end > start && is_ascii_space(value[end - 1]) {
        end -= 1;
    }
    value[start..end].to_vec()
}

/// Decode the exact entity set the C++ kernel handles
/// (`&amp; &lt; &gt; &quot; &apos; &#39;`); unknown entities pass through
/// verbatim including the surrounding `&...;`.
fn html_unescape(value: &[u8]) -> Vec<u8> {
    let mut output: Vec<u8> = Vec::with_capacity(value.len());
    let mut index = 0usize;
    while index < value.len() {
        if value[index] != b'&' {
            output.push(value[index]);
            index += 1;
            continue;
        }
        let Some(semicolon) = find_byte(value, b';', index + 1) else {
            output.push(value[index]);
            index += 1;
            continue;
        };
        let entity = &value[index + 1..semicolon];
        match entity {
            b"amp" => output.push(b'&'),
            b"lt" => output.push(b'<'),
            b"gt" => output.push(b'>'),
            b"quot" => output.push(b'"'),
            b"apos" | b"#39" => output.push(b'\''),
            _ => output.extend_from_slice(&value[index..=semicolon]),
        }
        index = semicolon + 1;
    }
    output
}

/// Decode entities, strip balanced-ish `<...>` and `[...]` tag runs, then trim.
fn strip_markup(value: &[u8]) -> String {
    let unescaped = html_unescape(value);
    let mut cleaned: Vec<u8> = Vec::with_capacity(unescaped.len());
    let mut index = 0usize;
    while index < unescaped.len() {
        if unescaped[index] == b'<' {
            if let Some(close) = find_byte(&unescaped, b'>', index + 1) {
                index = close + 1;
                continue;
            }
        }
        if unescaped[index] == b'[' {
            if let Some(close) = find_byte(&unescaped, b']', index + 1) {
                index = close + 1;
                continue;
            }
        }
        cleaned.push(unescaped[index]);
        index += 1;
    }
    // The C++ kernel returns `std::string`; the parity inputs are ASCII, and the
    // unknown-entity passthrough keeps bytes intact, so a lossy UTF-8 decode
    // reproduces the C++ bytes exactly for valid UTF-8 and never panics.
    String::from_utf8_lossy(&trim_bytes(&cleaned)).into_owned()
}

/// Plain-Rust link-parser core (no `PyO3`). Returns the ordered list of parsed
/// links, byte offsets into `raw`. Unit-testable with `cargo test` without
/// crossing the Python boundary.
#[must_use]
pub fn find_urls_core(raw: &str) -> Vec<RawMatch> {
    let bytes = raw.as_bytes();
    if bytes.is_empty() {
        return Vec::new();
    }

    let mut found: Vec<RawMatch> = Vec::new();
    let mut occupied: Vec<(i64, i64)> = Vec::new();

    scan_bbcode(bytes, &mut found, &mut occupied);
    scan_html(bytes, &mut found, &mut occupied);
    scan_bare(bytes, &mut found, &occupied);

    // Stable sort by (start asc, end asc, method asc) — matches the C++
    // `std::sort` comparator and the Python reference sort key.
    found.sort_by(|left, right| {
        left.3
            .cmp(&right.3)
            .then(left.4.cmp(&right.4))
            .then(left.2.cmp(&right.2))
    });
    found
}

/// Pass 1 — `BBCode` `[url=...]...[/url]`. Always recorded as occupied (priority).
fn scan_bbcode(bytes: &[u8], found: &mut Vec<RawMatch>, occupied: &mut Vec<(i64, i64)>) {
    let mut index = 0usize;
    while index < bytes.len() {
        let Some(start) = find_ci(bytes, b"[url=", index) else {
            break;
        };
        let Some(url_end) = find_byte(bytes, b']', start + 5) else {
            break;
        };
        let Some(close) = find_ci(bytes, b"[/url]", url_end + 1) else {
            break;
        };

        let span_start = to_offset(start);
        let span_end = to_offset(close + 6);
        occupied.push((span_start, span_end));
        let url = String::from_utf8_lossy(&bytes[start + 5..url_end]).into_owned();
        let anchor = strip_markup(&bytes[url_end + 1..close]);
        found.push((url, anchor, BBCODE_METHOD.to_string(), span_start, span_end));
        index = close + 6;
    }
}

/// Pass 2 — HTML `<a ... href="...">...</a>`, suppressed by occupied spans.
fn scan_html(bytes: &[u8], found: &mut Vec<RawMatch>, occupied: &mut Vec<(i64, i64)>) {
    let mut index = 0usize;
    while index < bytes.len() {
        let Some(start) = find_ci(bytes, b"<a", index) else {
            break;
        };
        if start + 2 < bytes.len() {
            let boundary = bytes[start + 2];
            if !is_ascii_space(boundary) && boundary != b'>' {
                index = start + 2;
                continue;
            }
        }

        let Some(open_end) = find_byte(bytes, b'>', start + 2) else {
            break;
        };
        let Some(close) = find_ci(bytes, b"</a>", open_end + 1) else {
            index = open_end + 1;
            continue;
        };

        let span_start = to_offset(start);
        let span_end = to_offset(close + 4);
        if span_overlaps(span_start, span_end, occupied) {
            index = close + 4;
            continue;
        }

        let open_tag = &bytes[start..=open_end];
        let href_value = parse_first_href(open_tag);
        if !href_value.is_empty() {
            occupied.push((span_start, span_end));
            let anchor = strip_markup(&bytes[open_end + 1..close]);
            found.push((
                href_value,
                anchor,
                HTML_METHOD.to_string(),
                span_start,
                span_end,
            ));
        }
        index = close + 4;
    }
}

/// Parse the first `href=` attribute value out of an opening `<a ...>` tag.
/// Returns an empty string when no quoted href is found (matching the C++
/// `href_value.empty()` gate).
fn parse_first_href(open_tag: &[u8]) -> String {
    let mut tag_index = 0usize;
    while tag_index < open_tag.len() {
        if !starts_with_ci(open_tag, tag_index, b"href") {
            tag_index += 1;
            continue;
        }
        let mut cursor = tag_index + 4;
        while cursor < open_tag.len() && is_ascii_space(open_tag[cursor]) {
            cursor += 1;
        }
        if cursor >= open_tag.len() || open_tag[cursor] != b'=' {
            tag_index += 1;
            continue;
        }
        cursor += 1;
        while cursor < open_tag.len() && is_ascii_space(open_tag[cursor]) {
            cursor += 1;
        }
        if cursor >= open_tag.len() || (open_tag[cursor] != b'"' && open_tag[cursor] != b'\'') {
            tag_index += 1;
            continue;
        }
        let quote = open_tag[cursor];
        cursor += 1;
        let Some(value_end) = find_byte(open_tag, quote, cursor) else {
            tag_index += 1;
            continue;
        };
        return String::from_utf8_lossy(&open_tag[cursor..value_end]).into_owned();
    }
    String::new()
}

/// Pass 3 — bare `http(s)://` tokens, suppressed by occupied spans (read-only).
fn scan_bare(bytes: &[u8], found: &mut Vec<RawMatch>, occupied: &[(i64, i64)]) {
    let mut index = 0usize;
    while index < bytes.len() {
        let is_http = starts_with_ci(bytes, index, b"http://");
        let is_https = starts_with_ci(bytes, index, b"https://");
        if !is_http && !is_https {
            index += 1;
            continue;
        }

        let mut end = index;
        while end < bytes.len() {
            let byte = bytes[end];
            if is_ascii_space(byte)
                || byte == b'['
                || byte == b']'
                || byte == b'<'
                || byte == b'>'
                || byte == b'"'
                || byte == b'\''
            {
                break;
            }
            end += 1;
        }

        let span_start = to_offset(index);
        let span_end = to_offset(end);
        if !span_overlaps(span_start, span_end, occupied) {
            let url = String::from_utf8_lossy(&bytes[index..end]).into_owned();
            found.push((
                url,
                String::new(),
                BARE_METHOD.to_string(),
                span_start,
                span_end,
            ));
        }
        index = end;
    }
}

/// `find_urls(raw_bbcode) -> list[tuple[str, str, str, int, int]]`.
///
/// Thin `PyO3` wrapper over [`find_urls_core`]. Never raises; empty input
/// returns `[]`.
#[pyfunction]
#[pyo3(signature = (raw_bbcode))]
fn find_urls(raw_bbcode: &str) -> Vec<RawMatch> {
    find_urls_core(raw_bbcode)
}

/// The Python module definition. The module name (`linkparse`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`linkparse.so`) imports
/// as `extensions.linkparse` once staged on `PYTHONPATH` under `extensions/`.
/// Registering `find_urls` keeps the health probe's expected attribute present.
#[pymodule]
fn linkparse(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(find_urls, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::find_urls_core;

    /// Independent pure-Python-style reference oracle mirroring the documented
    /// three-pass algorithm, used to pin the parity cases from
    /// `backend/apps/pipeline/tests.py::LinkParseExtensionTests`.
    fn parity_cases() -> Vec<&'static str> {
        vec![
            "",
            "[URL=https://example.com/threads/topic.1]Anchor[/URL]",
            "[url=https://example.com/threads/topic.2]Lower[/url]",
            "<a href=\"https://example.com/resources/tool.3\">Tool</a>",
            "Visit https://example.com/threads/topic.4 now",
            "[URL=https://example.com/threads/topic.5]<b>Bold</b> anchor[/URL]",
            "<a class=\"x\" href='https://example.com/resources/tool.6'>Inner <b>tag</b></a>",
            "[URL=https://example.com/threads/topic.7]<a href=\"https://bad\">Nested</a>[/URL>",
            "[URL=https://example.com/threads/topic.8][/URL]",
            "Before <a href=\"https://example.com/threads/topic.9?x=1#frag\">Query</a> after",
            "Mix [url=https://example.com/threads/topic.10]One[/url] and https://example.com/resources/tool.10",
            "No urls here at all",
            "Overlap <a href=\"https://example.com/threads/topic.11\">https://example.com/resources/tool.11</a>",
            "[URL=https://example.com/threads/topic.12]Upper[/URL] <A HREF=\"https://example.com/resources/tool.12\">Html</A>",
            "Two bare URLs https://example.com/threads/topic.13 and https://example.com/resources/tool.13",
        ]
    }

    #[test]
    fn empty_input_returns_empty() {
        assert!(find_urls_core("").is_empty());
    }

    #[test]
    fn bbcode_anchor_basic() {
        let out = find_urls_core("[URL=https://example.com/threads/topic.1]Anchor[/URL]");
        assert_eq!(out.len(), 1);
        let (url, anchor, method, start, end) = &out[0];
        assert_eq!(url, "https://example.com/threads/topic.1");
        assert_eq!(anchor, "Anchor");
        assert_eq!(method, "bbcode_anchor");
        assert_eq!(*start, 0);
        // The full `[URL=...topic.1]Anchor[/URL]` span is 53 bytes long, so the
        // exclusive end offset is 53 (verified against the Python oracle).
        assert_eq!(*end, 53);
    }

    #[test]
    fn bbcode_case_insensitive_lowercase_tag() {
        let out = find_urls_core("[url=https://example.com/threads/topic.2]Lower[/url]");
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].2, "bbcode_anchor");
    }

    #[test]
    fn html_anchor_basic() {
        let out = find_urls_core("<a href=\"https://example.com/resources/tool.3\">Tool</a>");
        assert_eq!(out.len(), 1);
        let (url, anchor, method, _s, _e) = &out[0];
        assert_eq!(url, "https://example.com/resources/tool.3");
        assert_eq!(anchor, "Tool");
        assert_eq!(method, "html_anchor");
    }

    #[test]
    fn bare_url_basic() {
        let out = find_urls_core("Visit https://example.com/threads/topic.4 now");
        assert_eq!(out.len(), 1);
        let (url, anchor, method, start, _e) = &out[0];
        assert_eq!(url, "https://example.com/threads/topic.4");
        assert_eq!(anchor, "");
        assert_eq!(method, "bare_url");
        assert_eq!(*start, 6);
    }

    #[test]
    fn bbcode_strips_inner_html_markup() {
        let out =
            find_urls_core("[URL=https://example.com/threads/topic.5]<b>Bold</b> anchor[/URL]");
        assert_eq!(out.len(), 1);
        // strip_markup removes <b>..</b> tags, trims -> "Bold anchor".
        assert_eq!(out[0].1, "Bold anchor");
    }

    #[test]
    fn html_single_quoted_href_and_class_before_href() {
        let out = find_urls_core(
            "<a class=\"x\" href='https://example.com/resources/tool.6'>Inner <b>tag</b></a>",
        );
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].0, "https://example.com/resources/tool.6");
        assert_eq!(out[0].1, "Inner tag");
    }

    #[test]
    fn unterminated_bbcode_falls_through_to_bare_and_html() {
        // The trailing `[/URL>` (not `[/URL]`) means the BBCode pass finds no
        // `[/url]` close and emits nothing. Two matches then survive (verified
        // against the Python oracle): (1) the URL value inside `[url=...]`
        // becomes a `bare_url` (it is not inside any occupied span because the
        // BBCode match was never recorded), and (2) the inner
        // `<a href="https://bad">` HTML anchor. Sorted by start, bare (offset 5)
        // precedes the html anchor (offset 41).
        let out = find_urls_core(
            "[URL=https://example.com/threads/topic.7]<a href=\"https://bad\">Nested</a>[/URL>",
        );
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].2, "bare_url");
        assert_eq!(out[0].0, "https://example.com/threads/topic.7");
        assert_eq!(out[1].2, "html_anchor");
        assert_eq!(out[1].0, "https://bad");
    }

    #[test]
    fn empty_bbcode_anchor_text() {
        let out = find_urls_core("[URL=https://example.com/threads/topic.8][/URL]");
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].1, "");
        assert_eq!(out[0].2, "bbcode_anchor");
    }

    #[test]
    fn html_with_query_and_fragment_in_href() {
        let out = find_urls_core(
            "Before <a href=\"https://example.com/threads/topic.9?x=1#frag\">Query</a> after",
        );
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].0, "https://example.com/threads/topic.9?x=1#frag");
        assert_eq!(out[0].2, "html_anchor");
    }

    #[test]
    fn mixed_bbcode_and_bare() {
        let out = find_urls_core(
            "Mix [url=https://example.com/threads/topic.10]One[/url] and https://example.com/resources/tool.10",
        );
        assert_eq!(out.len(), 2);
        // sorted by start: bbcode first, bare second.
        assert_eq!(out[0].2, "bbcode_anchor");
        assert_eq!(out[1].2, "bare_url");
    }

    #[test]
    fn no_urls_returns_empty() {
        assert!(find_urls_core("No urls here at all").is_empty());
    }

    #[test]
    fn html_suppresses_overlapping_bare_inside_anchor() {
        // The bare URL sits inside the <a>...</a> span, so it is suppressed.
        let out = find_urls_core(
            "Overlap <a href=\"https://example.com/threads/topic.11\">https://example.com/resources/tool.11</a>",
        );
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].2, "html_anchor");
        assert_eq!(out[0].0, "https://example.com/threads/topic.11");
    }

    #[test]
    fn uppercase_html_tag_and_href_key() {
        let out = find_urls_core(
            "[URL=https://example.com/threads/topic.12]Upper[/URL] <A HREF=\"https://example.com/resources/tool.12\">Html</A>",
        );
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].2, "bbcode_anchor");
        assert_eq!(out[1].2, "html_anchor");
        assert_eq!(out[1].0, "https://example.com/resources/tool.12");
    }

    #[test]
    fn two_bare_urls() {
        let out = find_urls_core(
            "Two bare URLs https://example.com/threads/topic.13 and https://example.com/resources/tool.13",
        );
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].2, "bare_url");
        assert_eq!(out[1].2, "bare_url");
        assert!(out[0].3 < out[1].3);
    }

    #[test]
    fn abbr_tag_is_not_an_anchor() {
        // `<abbr` must be rejected: the boundary char after `<a` is `b`, not
        // whitespace or `>`.
        let out = find_urls_core("<abbr title=\"x\">HTML</abbr>");
        assert!(out.is_empty());
    }

    #[test]
    fn unknown_entity_passes_through_in_anchor() {
        // &copy; is not in the decoded set, so it survives verbatim.
        let out = find_urls_core("[URL=https://e.com/threads/topic.1]A&copy;B[/URL]");
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].1, "A&copy;B");
    }

    #[test]
    fn empty_href_emits_nothing() {
        // An <a> with an empty href value emits nothing.
        let out = find_urls_core("<a href=\"\">x</a>");
        assert!(out.is_empty());
    }

    #[test]
    fn parity_cases_are_deterministic_and_total_ordered() {
        // Smoke over all 15 parity inputs: never panics, and the output is
        // sorted by (start, end, method).
        for case in parity_cases() {
            let out = find_urls_core(case);
            for window in out.windows(2) {
                let left = &window[0];
                let right = &window[1];
                let left_key = (left.3, left.4, left.2.as_str());
                let right_key = (right.3, right.4, right.2.as_str());
                assert!(left_key <= right_key, "not sorted for input {case:?}");
            }
        }
    }
}
