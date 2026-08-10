"""Behavioral tests for personal system-impact baselines."""

from resource_baselines import assess_personal_baseline


def test_marks_current_value_normal_when_it_is_inside_personal_range():
    result = assess_personal_baseline(
        current=3_100,
        historical=[2_800, 3_000, 3_200, 3_100, 2_900, 3_050],
        minimum_samples=5,
    )

    assert result["state"] == "normal"
    assert result["sample_count"] == 6
    assert result["range_low"] < 3_100 < result["range_high"]


def test_marks_extreme_when_current_value_is_far_above_personal_history():
    result = assess_personal_baseline(
        current=9_000,
        historical=[2_800, 3_000, 3_200, 3_100, 2_900, 3_050],
        minimum_samples=5,
    )

    assert result["state"] == "extreme"
    assert result["ratio_to_typical"] > 2


def test_stays_in_learning_until_enough_comparable_observations_exist():
    result = assess_personal_baseline(
        current=9_000,
        historical=[2_800, 3_000],
        minimum_samples=5,
    )

    assert result["state"] == "learning"
    assert result["sample_count"] == 2
