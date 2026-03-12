"""Tests for plugins.py and progress.py — Sprint 30 coverage push."""

import io
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from powerbi_import.plugins import (
    PluginBase,
    PluginManager,
    get_plugin_manager,
    reset_plugin_manager,
)
from powerbi_import.progress import MigrationProgress, NullProgress


# ── PluginBase hook return values ──────────────────────────────────


class TestPluginBase(unittest.TestCase):
    """Cover every PluginBase hook default return value."""

    def setUp(self):
        self.plugin = PluginBase()

    def test_pre_extraction_returns_none(self):
        result = self.plugin.pre_extraction("file.twbx")
        self.assertIsNone(result)

    def test_post_extraction_returns_none(self):
        result = self.plugin.post_extraction({"worksheets": []})
        self.assertIsNone(result)

    def test_pre_generation_returns_none(self):
        result = self.plugin.pre_generation({"tables": []})
        self.assertIsNone(result)

    def test_post_generation_returns_none(self):
        result = self.plugin.post_generation("/path/to/project")
        self.assertIsNone(result)

    def test_transform_dax_identity(self):
        formula = "SUM('Sales'[Amount])"
        self.assertEqual(self.plugin.transform_dax(formula), formula)

    def test_transform_m_query_identity(self):
        query = 'let Source = #table({}, {}) in Source'
        self.assertEqual(self.plugin.transform_m_query(query), query)

    def test_custom_visual_mapping_returns_none(self):
        result = self.plugin.custom_visual_mapping("bar")
        self.assertIsNone(result)

    def test_name_attribute(self):
        self.assertEqual(self.plugin.name, "base_plugin")


# ── PluginManager ──────────────────────────────────────────────────


class TestPluginManager(unittest.TestCase):
    """Cover PluginManager registration, hook dispatch, and transforms."""

    def setUp(self):
        self.manager = PluginManager()

    def test_register(self):
        plugin = PluginBase()
        self.manager.register(plugin)
        self.assertTrue(self.manager.has_plugins())
        self.assertEqual(len(self.manager.plugins), 1)

    def test_register_unnamed_plugin(self):
        """Plugin without a name attribute gets class name used."""

        class NoName:
            pass

        self.manager.register(NoName())
        self.assertTrue(self.manager.has_plugins())

    def test_has_plugins_empty(self):
        self.assertFalse(self.manager.has_plugins())

    def test_plugins_returns_copy(self):
        plugin = PluginBase()
        self.manager.register(plugin)
        plugins = self.manager.plugins
        plugins.clear()
        # Internal list should be unaffected
        self.assertEqual(len(self.manager.plugins), 1)

    # ── call_hook ──

    def test_call_hook_no_plugins(self):
        result = self.manager.call_hook("pre_extraction", tableau_file="f.twbx")
        self.assertIsNone(result)

    def test_call_hook_returns_last_non_none(self):

        class P1:
            name = "p1"

            def post_extraction(self, extracted_data):
                return {"modified": True}

        class P2:
            name = "p2"

            def post_extraction(self, extracted_data):
                return {"modified_again": True}

        self.manager.register(P1())
        self.manager.register(P2())
        result = self.manager.call_hook("post_extraction", extracted_data={})
        self.assertEqual(result, {"modified_again": True})

    def test_call_hook_skips_missing_methods(self):

        class OnlyPre:
            name = "only_pre"

            def pre_extraction(self, tableau_file):
                pass

        self.manager.register(OnlyPre())
        # Calling a hook the plugin doesn't implement → None
        result = self.manager.call_hook(
            "post_extraction", extracted_data={}
        )
        self.assertIsNone(result)

    def test_call_hook_exception_logged_not_raised(self):

        class BadPlugin:
            name = "bad"

            def pre_extraction(self, tableau_file):
                raise RuntimeError("boom")

        self.manager.register(BadPlugin())
        # Should not raise
        result = self.manager.call_hook(
            "pre_extraction", tableau_file="x.twbx"
        )
        self.assertIsNone(result)

    # ── apply_transform ──

    def test_apply_transform_chain(self):
        """Each plugin receives output of previous in chain."""

        class Upper:
            name = "upper"

            def transform_dax(self, formula):
                return formula.upper()

        class Prefix:
            name = "prefix"

            def transform_dax(self, formula):
                return "-- modified\n" + formula

        self.manager.register(Upper())
        self.manager.register(Prefix())
        result = self.manager.apply_transform("transform_dax", "sum(x)")
        self.assertEqual(result, "-- modified\nSUM(X)")

    def test_apply_transform_none_return_keeps_value(self):

        class NoneTransform:
            name = "none_t"

            def transform_dax(self, formula):
                return None  # Should keep original

        self.manager.register(NoneTransform())
        result = self.manager.apply_transform("transform_dax", "SUM(x)")
        self.assertEqual(result, "SUM(x)")

    def test_apply_transform_exception_keeps_value(self):

        class Boom:
            name = "boom"

            def transform_dax(self, formula):
                raise ValueError("oops")

        self.manager.register(Boom())
        result = self.manager.apply_transform("transform_dax", "original")
        self.assertEqual(result, "original")

    def test_apply_transform_no_plugins(self):
        result = self.manager.apply_transform("transform_dax", "formula")
        self.assertEqual(result, "formula")

    # ── load_from_config ──

    def test_load_from_config_class_import(self):
        """Test "module.ClassName" pattern."""
        # Use a known importable module + class
        mod = types.ModuleType("_test_plugin_mod")
        mod.MyPlugin = type("MyPlugin", (), {"name": "loaded"})
        sys.modules["_test_plugin_mod"] = mod
        try:
            self.manager.load_from_config(["_test_plugin_mod.MyPlugin"])
            self.assertEqual(len(self.manager.plugins), 1)
            self.assertEqual(self.manager.plugins[0].name, "loaded")
        finally:
            del sys.modules["_test_plugin_mod"]

    def test_load_from_config_module_with_plugin_class(self):
        """Test "module" pattern with module-level Plugin class."""
        mod = types.ModuleType("_test_plugin_plain")
        mod.Plugin = type("Plugin", (), {"name": "from_module"})
        sys.modules["_test_plugin_plain"] = mod
        try:
            self.manager.load_from_config(["_test_plugin_plain"])
            self.assertEqual(len(self.manager.plugins), 1)
        finally:
            del sys.modules["_test_plugin_plain"]

    def test_load_from_config_module_without_plugin_class(self):
        """Module without Plugin class → warning, no crash."""
        mod = types.ModuleType("_test_plugin_nope")
        sys.modules["_test_plugin_nope"] = mod
        try:
            self.manager.load_from_config(["_test_plugin_nope"])
            self.assertEqual(len(self.manager.plugins), 0)
        finally:
            del sys.modules["_test_plugin_nope"]

    def test_load_from_config_dotted_module_no_class(self):
        """Dotted path where last segment is lowercase → treated as module path."""
        mod = types.ModuleType("_test_plugin_dotted.submod")
        mod.Plugin = type("Plugin", (), {"name": "dotted"})
        sys.modules["_test_plugin_dotted.submod"] = mod
        try:
            self.manager.load_from_config(["_test_plugin_dotted.submod"])
            self.assertEqual(len(self.manager.plugins), 1)
        finally:
            del sys.modules["_test_plugin_dotted.submod"]

    def test_load_from_config_dotted_module_no_plugin(self):
        """Dotted module without Plugin class → warning."""
        mod = types.ModuleType("_test_plugin_dotted2.submod")
        sys.modules["_test_plugin_dotted2.submod"] = mod
        try:
            self.manager.load_from_config(["_test_plugin_dotted2.submod"])
            self.assertEqual(len(self.manager.plugins), 0)
        finally:
            del sys.modules["_test_plugin_dotted2.submod"]

    def test_load_from_config_bad_spec(self):
        """Non-existent module → error logged, no crash."""
        self.manager.load_from_config(["nonexistent_module_xyz123"])
        self.assertEqual(len(self.manager.plugins), 0)

    def test_load_from_config_none_input(self):
        """None input → no-op."""
        self.manager.load_from_config(None)
        self.assertEqual(len(self.manager.plugins), 0)

    def test_load_from_config_empty_list(self):
        self.manager.load_from_config([])
        self.assertFalse(self.manager.has_plugins())


# ── Global manager ─────────────────────────────────────────────────


class TestGlobalPluginManager(unittest.TestCase):
    def test_get_plugin_manager(self):
        mgr = get_plugin_manager()
        self.assertIsInstance(mgr, PluginManager)

    def test_reset_plugin_manager(self):
        mgr1 = get_plugin_manager()
        mgr2 = reset_plugin_manager()
        self.assertIsNot(mgr1, mgr2)
        self.assertIsInstance(mgr2, PluginManager)


# ── MigrationProgress ─────────────────────────────────────────────


class TestMigrationProgress(unittest.TestCase):
    """Cover fail(), skip(), summary(), _print_bar(), and on_step callback."""

    def test_start_and_complete_basic(self):
        p = MigrationProgress(total_steps=3, show_bar=False)
        p.start("Step 1")
        p.complete("Done 1")
        self.assertEqual(len(p._steps), 1)
        self.assertEqual(p._steps[0]['status'], 'complete')

    def test_fail_records_status_and_error(self):
        p = MigrationProgress(total_steps=2, show_bar=False)
        p.start("Failing step")
        p.fail("Something went wrong")
        self.assertEqual(p._steps[0]['status'], 'failed')
        self.assertEqual(p._steps[0]['error'], 'Something went wrong')
        self.assertIn('elapsed', p._steps[0])

    def test_fail_no_steps_is_noop(self):
        p = MigrationProgress(total_steps=2, show_bar=False)
        # No start() called
        p.fail("nothing")
        self.assertEqual(len(p._steps), 0)

    def test_skip_records_status_and_reason(self):
        p = MigrationProgress(total_steps=3, show_bar=False)
        p.skip("Optional step", reason="Not needed")
        self.assertEqual(len(p._steps), 1)
        self.assertEqual(p._steps[0]['status'], 'skipped')
        self.assertEqual(p._steps[0]['message'], 'Not needed')
        self.assertEqual(p._steps[0]['name'], 'Optional step')

    def test_summary_counts(self):
        p = MigrationProgress(total_steps=4, show_bar=False)
        p.start("A")
        p.complete("ok")
        p.start("B")
        p.fail("err")
        p.skip("C", "not needed")
        p.start("D")
        p.complete()

        s = p.summary()
        self.assertEqual(s['completed'], 2)
        self.assertEqual(s['failed'], 1)
        self.assertEqual(s['skipped'], 1)
        self.assertEqual(len(s['steps']), 4)
        self.assertIn('total_elapsed', s)
        self.assertGreaterEqual(s['total_elapsed'], 0)

    def test_summary_empty(self):
        p = MigrationProgress(total_steps=1, show_bar=False)
        s = p.summary()
        self.assertEqual(s['completed'], 0)
        self.assertEqual(s['failed'], 0)
        self.assertEqual(s['skipped'], 0)

    def test_on_step_callback_start(self):
        calls = []
        cb = lambda idx, name, status, msg: calls.append((idx, name, status, msg))
        p = MigrationProgress(total_steps=2, on_step=cb, show_bar=False)
        p.start("Step A")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], (1, "Step A", "in_progress", ""))

    def test_on_step_callback_complete(self):
        calls = []
        cb = lambda idx, name, status, msg: calls.append((idx, name, status, msg))
        p = MigrationProgress(total_steps=2, on_step=cb, show_bar=False)
        p.start("S1")
        p.complete("done")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2], "complete")
        self.assertEqual(calls[1][3], "done")

    def test_on_step_callback_fail(self):
        calls = []
        cb = lambda idx, name, status, msg: calls.append((idx, name, status, msg))
        p = MigrationProgress(total_steps=2, on_step=cb, show_bar=False)
        p.start("S1")
        p.fail("oops")
        self.assertEqual(calls[-1][2], "failed")
        self.assertEqual(calls[-1][3], "oops")

    def test_on_step_callback_skip(self):
        calls = []
        cb = lambda idx, name, status, msg: calls.append((idx, name, status, msg))
        p = MigrationProgress(total_steps=2, on_step=cb, show_bar=False)
        p.skip("Skipped", "reason")
        self.assertEqual(calls[-1][2], "skipped")
        self.assertEqual(calls[-1][3], "reason")

    def test_print_bar_in_progress(self):
        """Test that _print_bar writes to stderr with correct icon."""
        p = MigrationProgress(total_steps=2, show_bar=False, bar_width=10)
        buf = io.StringIO()
        with patch('sys.stderr', buf):
            p._current = 1
            p._print_bar("Testing", "in_progress")
        output = buf.getvalue()
        self.assertIn("⏳", output)
        self.assertIn("Testing", output)
        # No newline for in_progress
        self.assertFalse(output.endswith("\n"))

    def test_print_bar_complete(self):
        p = MigrationProgress(total_steps=2, show_bar=False, bar_width=10)
        buf = io.StringIO()
        with patch('sys.stderr', buf):
            p._current = 1
            p._print_bar("Done", "complete", "finished")
        output = buf.getvalue()
        self.assertIn("✅", output)
        self.assertIn("finished", output)
        self.assertTrue(output.endswith("\n"))

    def test_print_bar_failed(self):
        p = MigrationProgress(total_steps=2, show_bar=False, bar_width=10)
        buf = io.StringIO()
        with patch('sys.stderr', buf):
            p._current = 1
            p._print_bar("Err", "failed", "error msg")
        output = buf.getvalue()
        self.assertIn("❌", output)
        self.assertTrue(output.endswith("\n"))

    def test_print_bar_skipped(self):
        p = MigrationProgress(total_steps=2, show_bar=False, bar_width=10)
        buf = io.StringIO()
        with patch('sys.stderr', buf):
            p._current = 1
            p._print_bar("Skip", "skipped")
        output = buf.getvalue()
        self.assertIn("⏭", output)
        self.assertTrue(output.endswith("\n"))

    def test_print_bar_percentage(self):
        """Bar fill should reflect progress percentage."""
        p = MigrationProgress(total_steps=4, show_bar=False, bar_width=20)
        buf = io.StringIO()
        with patch('sys.stderr', buf):
            p._current = 2  # 50%
            p._print_bar("Half", "complete")
        output = buf.getvalue()
        # 50% of 20 = 10 filled chars
        self.assertIn("█" * 10, output)

    def test_show_bar_true_writes_on_start(self):
        """When show_bar=True, start() writes to stderr."""
        buf = io.StringIO()
        with patch('sys.stderr', buf):
            p = MigrationProgress(total_steps=2, show_bar=True, bar_width=10)
            p.start("X")
        self.assertIn("X", buf.getvalue())

    def test_complete_no_steps_is_safe(self):
        p = MigrationProgress(total_steps=1, show_bar=False)
        # No start() called — complete() should be a no-op
        p.complete("msg")
        self.assertEqual(len(p._steps), 0)


# ── NullProgress ───────────────────────────────────────────────────


class TestNullProgress(unittest.TestCase):
    def test_all_methods_are_noop(self):
        p = NullProgress()
        p.start("A")
        p.complete("B")
        p.fail("C")
        p.skip("D", "E")

    def test_summary_returns_empty(self):
        p = NullProgress()
        s = p.summary()
        self.assertEqual(s['completed'], 0)
        self.assertEqual(s['failed'], 0)
        self.assertEqual(s['skipped'], 0)
        self.assertEqual(s['steps'], [])
        self.assertEqual(s['total_elapsed'], 0)


if __name__ == '__main__':
    unittest.main()
