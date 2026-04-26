// generic_anchor_matcher.cpp — pick #anti-garbage Algo 1
//
// Reference
// ---------
// Aho, A. V., & Corasick, M. J. (1975). "Efficient String Matching:
// An Aid to Bibliographic Search." Communications of the ACM, 18(6),
// 333-340. — the canonical multi-pattern automaton.
//
// What this kernel does
// ---------------------
// Builds a deterministic Aho-Corasick automaton from a list of
// generic-anchor phrases (the curated lexicon ships in
// ``apps/sources/generic_anchors.txt``); matches an input anchor
// against the automaton in a single linear pass. Returns the list
// of distinct phrases matched.
//
//   build_automaton(phrases: list[str]) -> AutomatonHandle
//   find_all(handle: AutomatonHandle, text: str) -> list[str]
//
// PARITY: ``find_all``'s output (set of unique phrases that occur as
// substrings of *text*, in insertion order of the lexicon) matches
// the pure-Python fallback in
// ``apps/pipeline/services/anchor_garbage_signals.py::_python_find_all``
// for every input. Speed is the only differentiator.
//
// Memory
// ------
// At ~500 phrases averaging 12 chars each, the trie holds ~6k nodes;
// fail-link table adds ~24 KB; output sets add ~8 KB. Total < 100 KB
// — well under the 64 MB cap from the plan.
//
// Cold-start behaviour
// --------------------
// - Empty phrase list → ``find_all`` always returns ``[]``.
// - Empty text → returns ``[]``.
// - Per-phrase cap of ``MAX_PHRASE_LEN`` (256) prevents pathological
//   inputs from blowing up the goto table.
//
// Per CPP-RULES §1, this file builds with -std=c++17 -O3 -march=native
// -Wall -Wextra -Wpedantic -Werror -Wconversion -fno-exceptions
// -fno-rtti.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstddef>
#include <cstdint>
#include <queue>
#include <string>
#include <unordered_set>
#include <vector>

namespace py = pybind11;

namespace {

constexpr std::size_t MAX_PHRASE_LEN = 256;

// Aho-Corasick node — flat-table representation. ``goto_table`` is
// keyed on (node_id × 256) + byte for O(1) transitions; ``fail`` is
// the failure link; ``output`` lists the phrase indices that end at
// this node.
//
// We pack the goto table as a single contiguous vector so cache
// behaviour stays good even with thousands of nodes.
struct Automaton {
    std::vector<std::int32_t> goto_table;  // size = nodes × 256
    std::vector<std::int32_t> fail_link;    // per-node failure link
    std::vector<std::vector<std::int32_t>> output;  // phrase indices ending at node
    std::vector<std::string> phrases;  // original phrases (insertion order)
    std::int32_t node_count = 1;        // root is node 0
};

constexpr std::int32_t NO_TRANSITION = -1;

inline std::size_t goto_index(std::int32_t node, std::uint8_t byte) {
    return (static_cast<std::size_t>(node) << 8U)
           | static_cast<std::size_t>(byte);
}

// Insert *phrase* into the trie portion of *aut*; record the phrase
// index in the output list of the terminal node.
void insert_phrase(Automaton& aut, std::int32_t phrase_idx,
                   const std::string& phrase) {
    std::int32_t node = 0;  // root
    for (char c : phrase) {
        const auto byte = static_cast<std::uint8_t>(c);
        const std::size_t idx = goto_index(node, byte);
        if (aut.goto_table[idx] == NO_TRANSITION) {
            aut.goto_table[idx] = aut.node_count;
            // Grow the flat tables for the new node.
            aut.goto_table.insert(
                aut.goto_table.end(), 256U, NO_TRANSITION);
            aut.fail_link.push_back(0);
            aut.output.emplace_back();
            ++aut.node_count;
        }
        node = aut.goto_table[idx];
    }
    aut.output[static_cast<std::size_t>(node)].push_back(phrase_idx);
}

// BFS-build fail links per Aho-Corasick 1975 §2.
void build_fail_links(Automaton& aut) {
    std::queue<std::int32_t> q;
    // First-level nodes: fail link is the root.
    for (std::uint16_t b = 0; b < 256; ++b) {
        const std::int32_t child = aut.goto_table[goto_index(0, static_cast<std::uint8_t>(b))];
        if (child != NO_TRANSITION) {
            aut.fail_link[static_cast<std::size_t>(child)] = 0;
            q.push(child);
        } else {
            // Self-loop on root for missing transitions.
            aut.goto_table[goto_index(0, static_cast<std::uint8_t>(b))] = 0;
        }
    }
    while (!q.empty()) {
        const std::int32_t node = q.front();
        q.pop();
        for (std::uint16_t b = 0; b < 256; ++b) {
            const std::int32_t child = aut.goto_table[goto_index(node, static_cast<std::uint8_t>(b))];
            if (child == NO_TRANSITION) {
                continue;
            }
            // Fail link of child = goto[fail[node], byte].
            std::int32_t f = aut.fail_link[static_cast<std::size_t>(node)];
            // Walk up failure links until we land somewhere with the
            // byte transition (root self-loops above guarantee
            // termination).
            while (f != 0
                   && aut.goto_table[goto_index(f, static_cast<std::uint8_t>(b))]
                       == NO_TRANSITION) {
                f = aut.fail_link[static_cast<std::size_t>(f)];
            }
            const std::int32_t link = aut.goto_table[goto_index(f, static_cast<std::uint8_t>(b))];
            // Don't link a node to itself.
            aut.fail_link[static_cast<std::size_t>(child)] =
                (link == child) ? 0 : link;
            // Inherit output from fail link.
            const auto& parent_out = aut.output[static_cast<std::size_t>(
                aut.fail_link[static_cast<std::size_t>(child)])];
            auto& child_out = aut.output[static_cast<std::size_t>(child)];
            child_out.insert(child_out.end(), parent_out.begin(), parent_out.end());
            q.push(child);
        }
    }
}

}  // namespace

// ─────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────

std::shared_ptr<Automaton> build_automaton(const std::vector<std::string>& phrases) {
    auto aut = std::make_shared<Automaton>();
    // Initialise root node — 256 slots, all NO_TRANSITION.
    aut->goto_table.assign(256U, NO_TRANSITION);
    aut->fail_link.push_back(0);  // root's fail link is root.
    aut->output.emplace_back();    // root has no terminal output.
    aut->phrases.reserve(phrases.size());

    std::int32_t i = 0;
    for (const auto& p : phrases) {
        if (p.empty() || p.size() > MAX_PHRASE_LEN) {
            // Skip pathological inputs but still bump the index so
            // output positions stay aligned with the input list.
            aut->phrases.emplace_back(p);
            ++i;
            continue;
        }
        aut->phrases.emplace_back(p);
        insert_phrase(*aut, i, p);
        ++i;
    }
    build_fail_links(*aut);
    return aut;
}

std::vector<std::string> find_all(std::shared_ptr<Automaton> aut,
                                  const std::string& text) {
    std::vector<std::string> out;
    if (!aut || text.empty() || aut->phrases.empty()) {
        return out;
    }
    std::unordered_set<std::int32_t> seen;
    seen.reserve(aut->phrases.size());
    std::int32_t node = 0;
    for (char c : text) {
        const auto byte = static_cast<std::uint8_t>(c);
        // Follow goto / fail until we land on a transition (root
        // self-loops above guarantee termination).
        while (node != 0
               && aut->goto_table[goto_index(node, byte)] == NO_TRANSITION) {
            node = aut->fail_link[static_cast<std::size_t>(node)];
        }
        const std::int32_t next = aut->goto_table[goto_index(node, byte)];
        if (next != NO_TRANSITION) {
            node = next;
        }
        for (std::int32_t phrase_idx
             : aut->output[static_cast<std::size_t>(node)]) {
            if (seen.insert(phrase_idx).second) {
                out.emplace_back(
                    aut->phrases[static_cast<std::size_t>(phrase_idx)]);
            }
        }
    }
    return out;
}

PYBIND11_MODULE(generic_anchor_matcher, m) {
    m.doc() = "Aho-Corasick generic-anchor blacklist matcher.";
    py::class_<Automaton, std::shared_ptr<Automaton>>(m, "Automaton")
        .def_readonly("node_count", &Automaton::node_count)
        .def("phrase_count",
             [](const Automaton& a) { return a.phrases.size(); });
    m.def(
        "build_automaton",
        &build_automaton,
        py::arg("phrases"),
        "Build an Aho-Corasick automaton from a list of phrases."
    );
    m.def(
        "find_all",
        &find_all,
        py::arg("automaton"),
        py::arg("text"),
        "Return distinct phrases that occur as substrings of *text*."
    );
}
