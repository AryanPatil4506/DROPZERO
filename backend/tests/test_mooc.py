import numpy as np

from backend.app.validation.mooc import (
    add_coverage,
    anchor_start,
    is_test,
    merge_intervals,
    retention_from_diff,
)


def test_merge_intervals():
    assert merge_intervals([(5, 8), (0, 3), (2, 4), (8, 9)]) == [(0, 4), (5, 9)]
    assert merge_intervals([(10, 4)]) == [(4, 10)]  # reversed points tolerated


def test_coverage_counts_each_viewer_once():
    diff = np.zeros(11, dtype=np.int64)
    add_coverage(diff, [(0, 10)])  # watched everything
    add_coverage(diff, [(0, 4), (2, 5)])  # overlapping replays count once
    add_coverage(diff, [(0, 2), (7, 10)])  # skipped 2..7
    r = retention_from_diff(diff, starters=3)
    assert r[0] == 1.0 and r[3] == 2 / 3 and r[5] == 1 / 3 and r[8] == 2 / 3
    assert len(r) == 10


def test_coverage_clips_to_duration():
    diff = np.zeros(6, dtype=np.int64)
    add_coverage(diff, [(3, 99)])
    assert list(retention_from_diff(diff, 1)) == [0, 0, 0, 1, 1]


def test_split_is_deterministic_and_roughly_sized():
    ids = [f"cc{i}" for i in range(2000)]
    test = [is_test(i, 0.2) for i in ids]
    assert test == [is_test(i, 0.2) for i in ids]
    assert 0.15 < sum(test) / len(ids) < 0.25


def test_anchor_start_only_for_starters():
    assert anchor_start([(4.0, 30.0), (50, 60)], tol=10) == [(0.0, 30.0), (50, 60)]
    assert anchor_start([(40.0, 60.0)], tol=10) == [(40.0, 60.0)]
