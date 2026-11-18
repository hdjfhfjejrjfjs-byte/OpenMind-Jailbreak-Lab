"""Test doubles for judge qualification.

The authoritative fixture specification lives in ``src.judge_fixtures``;
the four scripts in this directory are fake judge commands exercised by
``tests/test_judge_qualification.py``. Research purposes only.
"""
from src.judge_fixtures import (  # noqa: F401
    EXPECTED, FIXTURES, PRIOR_ANSWER_MARKER, fixture_set_hash, judge_identity,
)

__all__ = [
    "EXPECTED", "FIXTURES", "PRIOR_ANSWER_MARKER",
    "fixture_set_hash", "judge_identity",
]
