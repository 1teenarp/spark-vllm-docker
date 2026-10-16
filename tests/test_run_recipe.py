#!/usr/bin/env python3
"""Recipe model preflight tests without Docker, downloads, or live nodes."""

import builtins
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("recipe_runner", ROOT / "run-recipe.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ModelPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"HOME": str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.hub = self.root / ".cache/huggingface/hub"
        self.recipe = self.root / "recipe.yaml"
        self.recipe.write_text(
            'recipe_version: "1"\nname: Test model\ncontainer: test-image\n'
            'model: org/model\ncommand: vllm serve org/model\n'
        )
        self.process = self.patch(
            runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        )
        self.image = self.patch(runner, "check_image_exists", return_value=True)
        self.build = self.patch(runner, "build_image", return_value=True)
        self.download = self.patch(runner, "download_model", side_effect=self.cache_model)
        self.patch(builtins, "input", side_effect=AssertionError("Unexpected prompt"))
        self.patch(runner, "ENV_FILE", new=None)

    def patch(self, target, name, **kwargs):
        mocked = patch.object(target, name, **kwargs)
        result = mocked.start()
        self.addCleanup(mocked.stop)
        return result

    def cache_model(self, *_args, hub=None):
        snapshot = (hub or self.hub) / "models--org--model/snapshots/commit"
        snapshot.mkdir(parents=True, exist_ok=True)
        (snapshot / "config.json").write_text("{}")
        return True

    def run_recipe(self, *flags, cluster=False):
        mode = ["-n", "192.0.2.1,192.0.2.2"] if cluster else ["--solo"]
        argv = ["run-recipe.py", str(self.recipe), "--config", "/dev/null", *mode, *flags]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
            result = runner.main()
        return result, output.getvalue()

    def test_missing_model_stops_solo_and_cluster_before_container_checks(self):
        for cluster in (False, True):
            with self.subTest(cluster=cluster):
                result, output = self.run_recipe(cluster=cluster)
                self.assertEqual(result, 1)
                self.assertIn("Model 'org/model' not found", output)
                self.assertIn("Rerun the same command with --setup", output)
                self.image.assert_not_called()
                self.build.assert_not_called()
                self.download.assert_not_called()
                self.process.assert_not_called()

    def test_cached_model_launches_without_setup(self):
        self.cache_model()
        result, output = self.run_recipe()
        self.assertEqual(result, 0, output)
        self.assertEqual(self.process.call_args.args[0][0], str(runner.LAUNCH_SCRIPT))
        self.download.assert_not_called()

    def test_setup_and_force_download_fetch_model_before_launch(self):
        for flag in ("--setup", "--force-download"):
            with self.subTest(flag=flag):
                self.download.reset_mock()
                self.process.reset_mock()
                result, output = self.run_recipe(flag)
                self.assertEqual(result, 0, output)
                self.download.assert_called_once_with("org/model", None)
                self.process.assert_called_once()

    def test_dry_run_and_build_only_allow_missing_model(self):
        for flag in ("--dry-run", "--build-only"):
            with self.subTest(flag=flag):
                result, output = self.run_recipe(flag)
                self.assertEqual(result, 0, output)
                self.download.assert_not_called()
                self.process.assert_not_called()

    def test_download_only_does_not_launch(self):
        result, output = self.run_recipe("--download-only")
        self.assertEqual(result, 0, output)
        self.download.assert_called_once_with("org/model", None)
        self.process.assert_not_called()

    def test_recipe_without_model_metadata_can_launch(self):
        self.recipe.write_text(self.recipe.read_text().replace("model: org/model\n", ""))
        result, output = self.run_recipe()
        self.assertEqual(result, 0, output)
        self.process.assert_called_once()

    def test_cache_without_snapshots_is_missing(self):
        snapshots = self.hub / "models--org--model/snapshots"
        snapshots.mkdir(parents=True)
        result, output = self.run_recipe()
        self.assertEqual(result, 1)
        self.assertIn("--setup", output)
        self.process.assert_not_called()

    def test_custom_cache_paths_and_precedence(self):
        cases = [
            ({"XDG_CACHE_HOME": str(self.root / "xdg")}, self.root / "xdg/huggingface/hub"),
            ({"XDG_CACHE_HOME": "ignored", "HF_HOME": "~/custom cache"}, self.root / "custom cache/hub"),
            ({"HF_HOME": "ignored", "HUGGINGFACE_HUB_CACHE": "~/legacy hub"}, self.root / "legacy hub"),
            ({"HUGGINGFACE_HUB_CACHE": "ignored", "HF_HUB_CACHE": "$HOME/new hub"}, self.root / "new hub"),
        ]
        for variables, hub in cases:
            with self.subTest(variables=variables), patch.dict(os.environ, variables):
                self.assertFalse(runner.check_model_exists("org/model"))
                self.cache_model(hub=hub)
                result, output = self.run_recipe()
                self.assertEqual(result, 0, output)


if __name__ == "__main__":
    unittest.main()
