"""Run the offline suite and enforce the reviewed test count."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EXPECTED_TEST_COUNT = 30
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
assert suite.countTestCases() == EXPECTED_TEST_COUNT, (suite.countTestCases(), EXPECTED_TEST_COUNT)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
