import numpy as np

from backend.app.validation.llm_baseline import parse_seconds, score_points, top_k_points

LEC = {
    "hazard": np.array([0.3, 0.01, 0.08, 0.02, 0.06]),
    "starts": np.array([0.0, 12.0, 24.0, 36.0, 48.0]),
    "ends": np.array([12.0, 24.0, 36.0, 48.0, 60.0]),
}


def test_parse_seconds_json_and_fallback():
    assert parse_seconds('{"drop_seconds": [30, 50, 999]}', 5, 60) == [30.0, 50.0]
    assert parse_seconds("I think 30 and 55", 5, 60) == [30.0, 55.0]
    assert parse_seconds("no idea", 5, 60) == []


def test_score_points_counts_hits_and_found_drops():
    # real major drops (>= 0.05, first segment excluded): segments 2 (24-36) and 4 (48-60)
    hits, found, total = score_points([30.0, 5.0], LEC, 0.05, 0.0)
    assert (hits, found, total) == (1, 1, 2)
    hits, found, total = score_points([30.0, 50.0, 31.0], LEC, 0.05, 0.0)
    assert (hits, found, total) == (3, 2, 2)


def test_top_k_points_skips_first_segment():
    pts = top_k_points(np.array([0.9, 0.1, 0.8, 0.2, 0.7]), LEC, 2)
    assert pts == [30.0, 54.0]
