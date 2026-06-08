//! Detector catalog contract tests.

#[test]
fn test_when_catalog_loads_then_all_35_static_detectors_exist() {
    let rows = speccheck_detectors::detector_catalog();

    assert_eq!(rows.len(), 35);
    assert!(rows.iter().any(|row| row.id == "RUSTBUG-PERF-001"));
    assert!(rows.iter().any(|row| row.id == "RUSTBUG-SEC-005"));
}

#[test]
fn test_when_pickle_loads_request_body_then_security_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "def view(request):\n    return pickle.loads(request.body)\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-SEC-002");
    assert_eq!(findings[0].category, "security");
    assert_eq!(findings[0].severity, "critical");
    assert_eq!(findings[0].priority_score, 100);
    assert_eq!(findings[0].line_number, 2);
    assert!(findings[0].suggested_fix.contains("safe parser"));
    assert_eq!(findings[0].fingerprint.len(), 64);
    assert!(findings[0]
        .fingerprint
        .chars()
        .all(|character| character.is_ascii_hexdigit() && !character.is_ascii_uppercase()));
}

#[test]
fn test_when_pickle_loads_has_no_request_input_then_no_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "def view(payload):\n    return pickle.loads(payload)\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_bug_pattern_words_appear_only_in_comments_then_no_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "# go worker() is documentation only\n// eval(user_input) is commented out\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_bug_pattern_words_appear_in_block_comment_then_no_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "services/speccheck/src/main.rs",
        "/* pickle.loads(request.body) is documentation only */\nfn main() {}\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_bug_pattern_words_define_the_detector_catalog_then_no_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "services/speccheck/crates/detectors/src/lib.rs",
        "            &[\"pickle.loads(\", \"request.body\"],\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_detector_source_has_real_bug_shape_then_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "services/speccheck/crates/detectors/src/lib.rs",
        "let payload = pickle.loads(request.body);\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-SEC-002");
}

#[test]
fn test_when_go_keyword_appears_in_python_doc_text_then_no_goroutine_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/channel.py",
        "\"\"\"Let requests go through the shared channel.\"\"\"\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_goroutine_is_in_go_source_then_resource_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "services/worker/main.go",
        "func main() {\n    go worker()\n}\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-RES-003");
}

#[test]
fn test_when_python_ternary_uses_if_then_assignment_finding_is_not_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/services.py",
        "lift = p_ab / (p_a * p_b) if (p_a * p_b) > 0 else 1.0\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_cursor_is_already_context_managed_then_no_resource_finding_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/services.py",
        "with connection.cursor() as cursor:\n    cursor.execute(sql)\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_loop_body_queries_first_row_then_n_plus_one_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "def view():\n    for parent in parents:\n        Child.objects.filter(parent=parent).first()\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-PERF-001");
    assert_eq!(findings[0].line_number, 3);
    assert!(findings[0].suggested_fix.contains("prefetch_related"));
}

#[test]
fn test_when_first_row_query_is_outside_loop_then_n_plus_one_is_not_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "def view():\n    return Child.objects.filter(parent=parent).first()\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_async_block_uses_blocking_http_then_sync_io_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "async def view():\n    response = requests.get(url)\n    return response\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-PERF-004");
    assert_eq!(findings[0].line_number, 2);
}

#[test]
fn test_when_async_block_uses_tab_indentation_then_sync_io_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "async def view():\n\tresponse = requests.get(url)\n\treturn response\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-PERF-004");
    assert_eq!(findings[0].line_number, 2);
}

#[test]
fn test_when_sync_view_uses_requests_then_async_blocking_http_is_not_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "def view():\n    response = requests.get(url)\n    return response\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_async_signature_and_body_share_one_line_then_context_is_not_started() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "async def view(): response = requests.get(url)\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_unindented_request_follows_async_block_then_context_is_cleared() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "async def view():\n    return ok\nrequests.get(url)\n",
    );

    assert!(findings.is_empty());
}

#[test]
fn test_when_one_line_has_two_distinct_risks_then_both_findings_are_kept() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "def view(request): return pickle.loads(request.body) or eval(user_input)\n",
    );
    let ids: Vec<&str> = findings
        .iter()
        .map(|finding| finding.bug_pattern_id)
        .collect();

    assert_eq!(findings.len(), 2);
    assert!(ids.contains(&"RUSTBUG-SEC-002"));
    assert!(ids.contains(&"RUSTBUG-SEC-003"));
}

#[test]
fn test_when_same_bug_pattern_appears_on_two_lines_then_both_findings_are_kept() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/tasks.py",
        "while True: pass\nwhile True: keep_waiting()\n",
    );

    assert_eq!(findings.len(), 2);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-PERF-002");
    assert_eq!(findings[0].line_number, 1);
    assert_eq!(findings[1].bug_pattern_id, "RUSTBUG-PERF-002");
    assert_eq!(findings[1].line_number, 2);
}

#[test]
fn test_when_loop_body_saves_row_then_unbatched_write_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/tasks.py",
        "def run():\n    for item in items:\n        item.save()\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-PERF-008");
    assert_eq!(findings[0].line_number, 3);
}

#[test]
fn test_when_async_block_uses_sync_orm_then_async_orm_is_reported() {
    let findings = speccheck_detectors::find_bugs_in_source(
        "backend/apps/foo/views.py",
        "async def view():\n    user = User.objects.get(id=user_id)\n    return user\n",
    );

    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].bug_pattern_id, "RUSTBUG-CONC-005");
    assert_eq!(findings[0].line_number, 2);
}

#[test]
fn test_when_all_static_pattern_fixtures_are_scanned_then_35_findings_are_reported() {
    let text = [
        "def view():",
        "    for parent in parents:",
        "        Child.objects.filter(parent=parent).first()",
        "while True: pass",
        "ForeignKey(User) filter(user=user)",
        "async def fetch_view():",
        "    requests.get(url)",
        "for item in items: rows.append(item)",
        "for row in rows: json.loads(big_blob)",
        "for line in lines: re.compile(pattern)",
        "for item in batch:",
        "    item.save()",
        "class View(ListAPIView): queryset = Model.objects.all()",
        "def view(request): from heavy_module import thing",
        "for i in range(len(xs)): xs[i+1]",
        "if score == 0.1:",
        "def f(items=[]): pass",
        "except: pass",
        "handle = open(path)",
        "subprocess.run(user_input, shell=True)",
        "except Exception: pass",
        "if (x = y) { return x; }",
        "return value\nunreachable_call()",
        "if flag: return same else: return same",
        "obj = Model.objects.get(id=id); obj.count += 1; obj.save()",
        "lock_a.acquire(); lock_b.acquire()",
        "first.save(); second.save()",
        "asyncio.create_task(do_work())",
        "async def sync_orm_view():",
        "    User.objects.get(id=id)",
        "cursor = connection.cursor()",
        "if bad: return open(path)",
        "go worker()",
        "CACHE = {}; CACHE[key] = value",
        "this.sub = observable.subscribe(value => value)",
        "cursor.execute(f\"select * from t where id={user_id}\")",
        "pickle.loads(request.body)",
        "eval(user_input)",
        "requests.get(user_input)",
        "HttpResponseRedirect(request.GET.get(\"next\"))",
    ]
    .join("\n");

    let findings = speccheck_detectors::find_bugs_in_source("fixture/all.go", &text);
    let ids: Vec<&str> = findings
        .iter()
        .map(|finding| finding.bug_pattern_id)
        .collect();

    assert_eq!(findings.len(), 35);
    assert_eq!(ids.first().copied(), Some("RUSTBUG-PERF-001"));
    assert_eq!(ids.last().copied(), Some("RUSTBUG-SEC-005"));
    assert_eq!(findings[0].priority_score, 80);
    assert_eq!(findings[10].priority_score, 50);
    assert_eq!(findings[30].priority_score, 100);
    for descriptor in speccheck_detectors::detector_catalog() {
        assert!(
            ids.contains(&descriptor.id.as_str()),
            "missing {}",
            descriptor.id
        );
    }
}
