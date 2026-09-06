from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_health_check.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("knowledge_health_skill_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def test_embedded_engine_matches_manifest(self) -> None:
        manifest = ROOT / "references" / "engine-sha256.txt"
        entries = [line.split("  ", 1) for line in manifest.read_text(encoding="utf-8").splitlines() if "  " in line]
        self.assertTrue(entries)
        for expected, relative in entries:
            with self.subTest(relative=relative):
                actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(expected, actual)

    def test_default_output_is_a_sanitized_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = (Path(temporary) / "待体检 资料").resolve()
            source.mkdir()
            output = self.runner.next_default_output(source, '某公司:/?*')
            self.assertEqual(source.parent, output.parent)
            self.assertFalse(self.runner.is_inside(output, source))
            self.assertNotRegex(output.name, r'[:/\\?*]')

    def test_output_inside_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = (Path(temporary) / "source").resolve()
            source.mkdir()
            unsafe = source / "results"
            with self.assertRaises(self.runner.SkillRunError) as caught:
                self.runner.choose_output(source, str(unsafe), None, False)
            self.assertEqual(3, caught.exception.exit_code)
            self.assertFalse(unsafe.exists())


if __name__ == "__main__":
    unittest.main()
