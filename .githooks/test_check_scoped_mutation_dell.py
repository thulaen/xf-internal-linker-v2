"""Unit tests for check-scoped-mutation.py remote-runner helpers (no real Docker, no SSH).

All subprocess / tar / Docker boundaries are mocked. These tests cover:
- manifest/snapshot verification (host_hashes, verify_snapshot)
- parse_live completion and survivor extraction
- Mint/Dell docker_context runner: sync-failure short-circuit, verify-failure
  short-circuit, happy-path survivor parsing
- _run_slice_on_machine routing by transport type
- _run_mutmut_split union, recovery, fail-open, and crashed-thread handling
- backward-compat: default local run vs XF_MUTATION_SPLIT=1 fan-out
"""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

_HOOK = Path(__file__).resolve().parent / "check-scoped-mutation.py"
_spec = importlib.util.spec_from_file_location("check_scoped_mutation", _HOOK)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)



class ParseLiveTests(unittest.TestCase):
    def test_returns_none_when_not_complete(self):
        self.assertIsNone(mod._parse_live("LIVE apps/x.py:1 (mutant 2)\n"))

    def test_returns_live_lines_when_done(self):
        raw = "LIVE apps/x.py:1 (mutant 2)\nLIVE apps/y.py:5 (mutant 7)\nDONE"
        live = mod._parse_live(raw)
        self.assertEqual(live, ["apps/x.py:1 (mutant 2)", "apps/y.py:5 (mutant 7)"])


# ── manifest / snapshot verification ───────────────────────────────────────────

class HostHashesTests(unittest.TestCase):
    def test_host_hashes_reads_each_relative_file(self):
        captured = {}

        def fake_read_bytes(self):
            captured[self.as_posix()] = True
            return b"abc"

        with patch.object(mod.Path, "read_bytes", fake_read_bytes):
            hashes = mod._host_hashes(["apps/x.py", "apps/y.py"])
        # both files hashed, both to the sha256 of b"abc"
        self.assertEqual(set(hashes), {"apps/x.py", "apps/y.py"})
        self.assertTrue(all(len(h) == 64 for h in hashes.values()))

    def test_manifest_digest_is_stable_and_order_independent(self):
        a = mod._manifest_digest({"apps/x.py": "11", "apps/y.py": "22"})
        b = mod._manifest_digest({"apps/y.py": "22", "apps/x.py": "11"})
        self.assertEqual(a, b)


class VerifySnapshotTests(unittest.TestCase):
    def _host(self):
        return {"apps/x.py": "a" * 64, "apps/y.py": "b" * 64}

    def test_true_when_every_remote_hash_matches(self):
        host = self._host()
        remote_out = f"{'a' * 64}  apps/x.py\n{'b' * 64}  apps/y.py\n"
        ok = mod._verify_snapshot(lambda paths: (0, remote_out), list(host), host)
        self.assertTrue(ok)

    def test_false_on_single_mismatch(self):
        host = self._host()
        remote_out = f"{'a' * 64}  apps/x.py\n{'9' * 64}  apps/y.py\n"
        ok = mod._verify_snapshot(lambda paths: (0, remote_out), list(host), host)
        self.assertFalse(ok)

    def test_false_when_a_file_is_missing_from_remote(self):
        host = self._host()
        remote_out = f"{'a' * 64}  apps/x.py\n"  # y.py absent
        ok = mod._verify_snapshot(lambda paths: (0, remote_out), list(host), host)
        self.assertFalse(ok)

    def test_false_when_remote_command_fails(self):
        host = self._host()
        ok = mod._verify_snapshot(lambda paths: (1, "boom"), list(host), host)
        self.assertFalse(ok)


# ── Mint runner ────────────────────────────────────────────────────────────────

class RunMutmutOnMintTests(unittest.TestCase):
    def test_sync_failure_returns_none_and_skips_docker_run(self):
        with (
            patch.object(mod, "_sync_source_to_mint", return_value="mint sync boom"),
            patch.object(mod.subprocess, "run") as mock_run,
        ):
            live, raw = mod._run_mutmut_on_mint(["helper", "arg"], ["apps/x.py"])
        self.assertIsNone(live)
        self.assertIn("mint sync boom", raw)
        mock_run.assert_not_called()

    def test_sync_runs_before_docker_run(self):
        order = []

        def fake_sync(*a, **k):
            order.append("sync")
            return None

        fake = subprocess.CompletedProcess(
            args=["docker"], returncode=0,
            stdout="LIVE apps/x.py:1 (mutant 2)\nDONE", stderr="",
        )

        def fake_run(*a, **k):
            order.append("run")
            return fake

        with (
            patch.object(mod, "_sync_source_to_mint", side_effect=fake_sync),
            patch.object(mod, "_verify_snapshot", return_value=True),
            patch.object(mod.subprocess, "run", side_effect=fake_run),
        ):
            live, raw = mod._run_mutmut_on_mint(["helper", "arg"], ["apps/x.py"])
        self.assertEqual(order[0], "sync")
        self.assertIn("apps/x.py:1 (mutant 2)", live)

    def test_verify_failure_returns_none(self):
        fake = subprocess.CompletedProcess(args=["d"], returncode=0, stdout="", stderr="")
        with (
            patch.object(mod, "_sync_source_to_mint", return_value=None),
            patch.object(mod, "_verify_snapshot", return_value=False),
            patch.object(mod.subprocess, "run", return_value=fake) as mock_run,
        ):
            live, raw = mod._run_mutmut_on_mint(["helper", "arg"], ["apps/x.py"])
        self.assertIsNone(live)
        mock_run.assert_not_called()  # never run the helper on an unverified copy

    def test_sync_source_uses_alpine_not_compose_run(self):
        """_sync_source_to_mint must use bare docker run + alpine, never compose run."""
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "gate", Path(__file__).resolve().parents[1] / ".githooks" / "check-scoped-mutation.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import inspect
        src = inspect.getsource(mod._sync_source_to_mint)
        self.assertIn("alpine", src, "_sync_source_to_mint must use alpine image")
        self.assertNotIn("compose run", src, "_sync_source_to_mint must NOT use compose run")
        self.assertIn("xf_mutation_repo", src, "must use named volume xf_mutation_repo")

    def test_mutation_run_uses_named_volume_and_network(self):
        """_run_mutmut_on_mint must use named volume + compose network, not compose run."""
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "gate", Path(__file__).resolve().parents[1] / ".githooks" / "check-scoped-mutation.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import inspect
        src = inspect.getsource(mod._run_mutmut_on_mint)
        self.assertIn("xf_mutation_repo", src, "must use named volume")
        self.assertIn("xf-internal-linker-v2_default", src, "must connect to compose network")
        self.assertNotIn("compose run", src, "must NOT use compose run")

    def test_sync_source_to_mint_real_body_builds_alpine_extractor(self):
        """Call the real _sync_source_to_mint (not mocked) to cover its body.

        Mock _pipe_tar_into so no actual Docker call is made; verify the extractor
        list that gets passed contains alpine and the named volume.
        """
        captured = {}

        def fake_pipe(extractor, env, who):
            captured["extractor"] = extractor
            return None  # success

        with patch.object(mod, "_pipe_tar_into", side_effect=fake_pipe):
            result = mod._sync_source_to_mint("testctx", {})

        self.assertIsNone(result)
        ext = " ".join(captured.get("extractor", []))
        self.assertIn("testctx", ext)
        self.assertIn("alpine:latest", ext)
        self.assertIn("xf_mutation_repo:/repo", ext)
        self.assertNotIn("compose", ext)

    def test_context_run_remote_closure_uses_alpine_sha256sum(self):
        """Call the real _mint_run_remote closure to cover lines 314-329.

        Mock subprocess.run; verify the command uses alpine + named volume.
        """
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="abc123  apps/x.py\n", stderr="",
        )
        with patch.object(mod.subprocess, "run", return_value=fake_proc) as mr:
            runner = mod._mint_run_remote("testctx", {})
            rc, out = runner(["apps/x.py"])

        self.assertEqual(rc, 0)
        self.assertIn("abc123", out)
        cmd = mr.call_args[0][0]
        self.assertIn("testctx", cmd)
        self.assertIn("alpine:latest", cmd)
        self.assertIn("xf_mutation_repo:/repo", " ".join(cmd))
        self.assertNotIn("compose", cmd)


# ── per-slice dispatch by transport ────────────────────────────────────────────

class RunSliceOnMachineTests(unittest.TestCase):
    def _ctx(self):
        return ({"apps/x.py": "apps/x.py:1"}, {"apps/x.py": ["tests_x.py"]})

    def test_docker_local_calls_local_run(self):
        token_by_rel, tests_map = self._ctx()
        with (
            patch.object(mod, "_local_run", return_value=(["L"], "DONE")) as ml,
            patch.object(mod, "_run_mutmut_on_mint") as mm,
        ):
            machine = {"name": "windows", "transport": "docker_local"}
            live, raw = mod._run_slice_on_machine(machine, ["apps/x.py"], token_by_rel, tests_map)
        ml.assert_called_once()
        mm.assert_not_called()
        self.assertEqual(live, ["L"])

    def test_docker_context_dell_routes_through_mint_runner(self):
        # Dell is now docker_context, so _run_slice_on_machine calls _run_mutmut_on_mint
        # (the shared docker_context runner) — not a separate Dell-specific function.
        token_by_rel, tests_map = self._ctx()
        with (
            patch.object(mod, "_local_run") as ml,
            patch.object(mod, "_run_mutmut_on_mint", return_value=(["D"], "DONE")) as mm,
        ):
            machine = {"name": "dell", "transport": "docker_context", "context": "dell"}
            live, raw = mod._run_slice_on_machine(machine, ["apps/x.py"], token_by_rel, tests_map)
        mm.assert_called_once()
        ml.assert_not_called()
        self.assertEqual(live, ["D"])

    def test_docker_context_mint_calls_mint_runner(self):
        token_by_rel, tests_map = self._ctx()
        with (
            patch.object(mod, "_local_run") as ml,
            patch.object(mod, "_run_mutmut_on_mint", return_value=(["M"], "DONE")) as mm,
        ):
            machine = {"name": "mint", "transport": "docker_context", "context": "mint"}
            live, raw = mod._run_slice_on_machine(machine, ["apps/x.py"], token_by_rel, tests_map)
        mm.assert_called_once()
        ml.assert_not_called()


# ── split orchestration: union, recovery, fail-open ────────────────────────────

def _machine(name, transport, **extra):
    m = {"name": name, "transport": transport, "weight": 1.0, "max_weight": 1.0,
         "share": 1.0}
    m.update(extra)
    return m


class RunMutmutSplitUnionTests(unittest.TestCase):
    def test_union_of_live_across_three_machines_fails(self):
        machines = [
            _machine("dell", "docker_context", context="dell"),
            _machine("windows", "docker_local"),
            _machine("mint", "docker_context", context="mint"),
        ]
        rel_paths = ["apps/a.py", "apps/b.py", "apps/c.py"]
        token_by_rel = {r: f"{r}:1" for r in rel_paths}
        tests_map = {r: [f"tests_{Path(r).stem}.py"] for r in rel_paths}

        plan = {"dell": ["apps/a.py"], "windows": ["apps/b.py"], "mint": ["apps/c.py"]}

        def fake_select(cfg, probe=None):
            return machines

        def fake_partition(items, ms):
            return plan

        result_by_name = {
            "dell": (["apps/a.py:1 (m1)"], "DONE"),
            "windows": (["apps/b.py:1 (m2)"], "DONE"),
            "mint": (["apps/c.py:1 (m3)"], "DONE"),
        }

        def fake_run_one(machine, files, tbr, tm):
            return result_by_name[machine["name"]]

        live, raw = mod._run_mutmut_split(
            rel_paths, token_by_rel, tests_map,
            run_one=fake_run_one, select=fake_select, partition=fake_partition,
        )
        self.assertEqual(
            sorted(live),
            ["apps/a.py:1 (m1)", "apps/b.py:1 (m2)", "apps/c.py:1 (m3)"],
        )

    def test_all_empty_live_passes(self):
        machines = [_machine("windows", "docker_local")]
        rel_paths = ["apps/a.py"]
        token_by_rel = {"apps/a.py": "apps/a.py:1"}
        tests_map = {"apps/a.py": ["tests_a.py"]}
        live, raw = mod._run_mutmut_split(
            rel_paths, token_by_rel, tests_map,
            run_one=lambda *a: ([], "DONE"),
            select=lambda cfg, probe=None: machines,
            partition=lambda items, ms: {"windows": ["apps/a.py"]},
        )
        self.assertEqual(live, [])


class MergeRecoveryTests(unittest.TestCase):
    def _setup(self):
        rel_paths = ["apps/a.py", "apps/b.py"]
        token_by_rel = {r: f"{r}:1" for r in rel_paths}
        tests_map = {r: [f"tests_{Path(r).stem}.py"] for r in rel_paths}
        machines = [
            _machine("dell", "docker_context", context="dell"),
            _machine("windows", "docker_local"),
        ]
        plan = {"dell": ["apps/a.py"], "windows": ["apps/b.py"]}
        return rel_paths, token_by_rel, tests_map, machines, plan

    def test_remote_none_result_is_rerun_locally_and_can_pass(self):
        rel_paths, token_by_rel, tests_map, machines, plan = self._setup()
        local_calls = []

        def fake_run_one(machine, files, tbr, tm):
            if machine["name"] == "dell":
                return (None, "TIMEOUT")          # broken-but-reachable remote
            return ([], "DONE")                    # windows fine

        def fake_local(files, tokens, tm):
            local_calls.append(list(files))
            return ([], "DONE")                    # local re-run says clean

        with patch.object(mod, "_local_run", side_effect=fake_local):
            live, raw = mod._run_mutmut_split(
                rel_paths, token_by_rel, tests_map,
                run_one=fake_run_one,
                select=lambda cfg, probe=None: machines,
                partition=lambda items, ms: plan,
            )
        self.assertEqual(local_calls, [["apps/a.py"]])  # only the failed slice re-ran
        self.assertEqual(live, [])                       # local judge: clean → pass

    def test_remote_none_then_local_none_hard_fails(self):
        rel_paths, token_by_rel, tests_map, machines, plan = self._setup()

        def fake_run_one(machine, files, tbr, tm):
            if machine["name"] == "dell":
                return (None, "TIMEOUT")
            return ([], "DONE")

        with patch.object(mod, "_local_run", return_value=(None, "docker down")):
            live, raw = mod._run_mutmut_split(
                rel_paths, token_by_rel, tests_map,
                run_one=fake_run_one,
                select=lambda cfg, probe=None: machines,
                partition=lambda items, ms: plan,
            )
        self.assertIsNone(live)  # nothing could judge apps/a.py anywhere → hard fail

    def test_crashed_thread_is_rerun_locally_not_silently_passed(self):
        # A machine thread that RAISES (not a clean None) must not vanish: its
        # files re-run on the trusted local runner, never a silent 0-survivor.
        rel_paths, token_by_rel, tests_map, machines, plan = self._setup()
        local_calls = []

        def fake_run_one(machine, files, tbr, tm):
            if machine["name"] == "dell":
                raise RuntimeError("SSH socket blew up")  # thread crash
            return ([], "DONE")

        def fake_local(files, tokens, tm):
            local_calls.append(list(files))
            return ([], "DONE")

        with patch.object(mod, "_local_run", side_effect=fake_local):
            live, raw = mod._run_mutmut_split(
                rel_paths, token_by_rel, tests_map,
                run_one=fake_run_one,
                select=lambda cfg, probe=None: machines,
                partition=lambda items, ms: plan,
            )
        self.assertEqual(local_calls, [["apps/a.py"]])  # crashed slice re-judged
        self.assertEqual(live, [])

    def test_unjudged_file_hard_fails_never_false_passes(self):
        # Coverage backstop: if a result vanishes entirely, an assigned file that
        # was never judged forces a hard fail (None), never a 0-survivor pass.
        results = {"windows": ([], "DONE", ["apps/b.py"])}  # apps/a.py missing
        token_by_rel = {"apps/a.py": "apps/a.py:1", "apps/b.py": "apps/b.py:1"}
        tests_map = {"apps/a.py": ["tests_a.py"], "apps/b.py": ["tests_b.py"]}
        live, raw = mod._merge_machine_results(
            results, token_by_rel, tests_map, {"apps/a.py", "apps/b.py"},
        )
        self.assertIsNone(live)
        self.assertIn("apps/a.py", raw)

    def test_remote_live_survivor_is_kept_without_local_rerun(self):
        rel_paths, token_by_rel, tests_map, machines, plan = self._setup()
        local_calls = []

        def fake_run_one(machine, files, tbr, tm):
            if machine["name"] == "dell":
                return (["apps/a.py:1 (m1)"], "DONE")  # completed WITH a survivor
            return ([], "DONE")

        with patch.object(mod, "_local_run",
                          side_effect=lambda *a: local_calls.append(a)):
            live, raw = mod._run_mutmut_split(
                rel_paths, token_by_rel, tests_map,
                run_one=fake_run_one,
                select=lambda cfg, probe=None: machines,
                partition=lambda items, ms: plan,
            )
        self.assertEqual(local_calls, [])  # completed remote → no re-run
        self.assertEqual(live, ["apps/a.py:1 (m1)"])


class SplitFailOpenTests(unittest.TestCase):
    def test_dropped_machine_owns_no_files(self):
        # dell dropped at probe → only windows+mint own files
        rel_paths = ["apps/a.py", "apps/b.py"]
        token_by_rel = {r: f"{r}:1" for r in rel_paths}
        tests_map = {r: [f"tests_{Path(r).stem}.py"] for r in rel_paths}
        machines = [
            _machine("windows", "docker_local", share=0.75),
            _machine("mint", "docker_context", context="mint", share=0.25),
        ]
        owned = {}

        def fake_run_one(machine, files, tbr, tm):
            owned[machine["name"]] = list(files)
            return ([], "DONE")

        live, raw = mod._run_mutmut_split(
            rel_paths, token_by_rel, tests_map,
            run_one=fake_run_one,
            select=lambda cfg, probe=None: machines,
            partition=lambda items, ms: {"windows": ["apps/a.py"], "mint": ["apps/b.py"]},
        )
        self.assertNotIn("dell", owned)
        self.assertEqual(live, [])


# ── backward compatibility ─────────────────────────────────────────────────────

class BackwardCompatTests(unittest.TestCase):
    def _common(self):
        rel_paths = ["apps/x.py"]
        tokens = ["apps/x.py:1"]
        return rel_paths, tokens

    def test_no_flag_uses_local_docker_branch(self):
        rel_paths, tokens = self._common()
        with (
            patch.dict(mod.os.environ, {"XF_MUTATION_SPLIT": ""}, clear=False),
            patch.object(mod, "_tests_map", return_value={"apps/x.py": ["tests_x.py"]}),
            patch.object(mod, "_flatten_tests", return_value=["tests_x.py"]),
            patch.object(mod, "_run_mutmut_split") as msplit,
            patch.object(mod, "_local_run", return_value=([], "DONE")) as ml,
        ):
            live, raw = mod._run_mutmut(rel_paths, tokens)
        msplit.assert_not_called()
        ml.assert_called_once()

    def test_dell_host_env_is_ignored_falls_to_local(self):
        # XF_MUTATION_HOST=dell branch was removed when Dell became docker_context.
        # Setting the env var now makes no difference — the gate falls through to local.
        rel_paths, tokens = self._common()
        with (
            patch.dict(mod.os.environ, {"XF_MUTATION_HOST": "dell", "XF_MUTATION_SPLIT": ""}, clear=False),
            patch.object(mod, "_tests_map", return_value={"apps/x.py": ["tests_x.py"]}),
            patch.object(mod, "_flatten_tests", return_value=["tests_x.py"]),
            patch.object(mod, "_run_mutmut_split") as msplit,
            patch.object(mod, "_local_run", return_value=([], "DONE")) as ml,
        ):
            live, raw = mod._run_mutmut(rel_paths, tokens)
        # Dell is now just another docker_context in the split; XF_MUTATION_HOST
        # is no longer a bypass — local run is used when SPLIT is not set.
        msplit.assert_not_called()
        ml.assert_called_once()

    def test_split_flag_routes_to_split(self):
        rel_paths, tokens = self._common()
        with (
            patch.dict(mod.os.environ, {"XF_MUTATION_SPLIT": "1"}, clear=False),
            patch.object(mod, "_tests_map", return_value={"apps/x.py": ["tests_x.py"]}),
            patch.object(mod, "_flatten_tests", return_value=["tests_x.py"]),
            patch.object(mod, "_run_mutmut_split", return_value=([], "DONE")) as msplit,
        ):
            live, raw = mod._run_mutmut(rel_paths, tokens)
        msplit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
