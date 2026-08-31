import os
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent
from midi_generator.evaluation import (
    CandidateScore,
    derive_seeds,
    evaluate_request,
    generate_candidates,
    plan_to_clip,
    rank_candidates,
    score_plan,
    score_profile,
)
from midi_generator.evaluation.scoring import _normalised_entropy
from midi_generator.analysis import analyze_clip
from midi_generator.generation import generate_contextual_plan, generate_plan
from midi_generator.transformations import EditableMidiClip


def _request(seed: int = 2026) -> MelodyRequest:
    return MelodyRequest(120, "C", "minor", 4, seed)


# --- derive_seeds -----------------------------------------------------------


def test_derive_seeds_is_deterministic_and_distinct():
    first = derive_seeds(2026, 8)
    second = derive_seeds(2026, 8)
    assert first == second
    assert len(set(first)) == 8
    assert all(seed >= 0 for seed in first)


def test_derive_seeds_prefix_is_stable_as_count_grows():
    assert derive_seeds(7, 3) == derive_seeds(7, 5)[:3]


def test_derive_seeds_changes_with_base_seed():
    assert derive_seeds(1, 5) != derive_seeds(2, 5)


def test_derive_seeds_ignores_global_random_state():
    random.seed(0)
    baseline = derive_seeds(99, 6)
    random.seed(0)
    for _ in range(1000):
        random.random()
    assert derive_seeds(99, 6) == baseline


def test_derive_seeds_rejects_non_positive_count():
    with pytest.raises(ValueError):
        derive_seeds(1, 0)


# --- scoring --------------------------------------------------------------


def test_normalised_entropy_bounds():
    assert _normalised_entropy((0, 0, 0)) == 0.0
    assert _normalised_entropy((5, 0, 0)) == 0.0
    assert _normalised_entropy((3, 3, 3)) == pytest.approx(1.0)


def test_score_profile_matches_hand_computed_values():
    clip = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 80),
            NoteEvent(62, 480, 480, 80),
            NoteEvent(64, 960, 480, 80),
            NoteEvent(62, 1440, 480, 80),
        ),
    )
    score = score_profile(analyze_clip(clip))
    assert score == CandidateScore(
        motion_entropy=0.579,
        pitch_class_diversity=0.429,
        rhythmic_activity=0.5,
        leap_control=0.833,
        aggregate=0.585,
    )


def test_score_components_stay_within_unit_range():
    for seed in range(12):
        score = score_plan(generate_plan(_request(seed)))
        for value in (
            score.motion_entropy,
            score.pitch_class_diversity,
            score.rhythmic_activity,
            score.leap_control,
            score.aggregate,
        ):
            assert 0.0 <= value <= 1.0


def test_score_plan_is_deterministic():
    plan = generate_plan(_request(5))
    assert score_plan(plan) == score_plan(plan)


def test_plan_to_clip_preserves_notes_and_length():
    plan = generate_plan(_request(5))
    clip = plan_to_clip(plan)
    assert clip.notes == plan.notes
    assert clip.length_ticks == plan.total_duration_ticks


# --- harness ------------------------------------------------------------


def test_generate_candidates_uses_derived_seeds():
    request = _request(2026)
    plans = generate_candidates(request, 5)
    seeds = derive_seeds(2026, 5)
    assert [plan.seed for plan in plans] == list(seeds)
    assert [plan.request.seed for plan in plans] == list(seeds)
    for plan, seed in zip(plans, seeds):
        assert plan == generate_plan(replace(request, seed=seed))


def test_generate_candidates_accepts_alternate_backend():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 90),
            NoteEvent(64, 480, 480, 90),
            NoteEvent(67, 960, 480, 90),
            NoteEvent(64, 1440, 480, 90),
        ),
    )
    request = _request(11)
    plans = generate_candidates(
        request, 3, backend=lambda req: generate_contextual_plan(req, reference)
    )
    assert len(plans) == 3
    assert all(
        plan.metadata.get("generation_mode") == "contextual" for plan in plans
    )


def test_rank_candidates_orders_by_score_then_seed():
    ranked = evaluate_request(_request(2026), 6)
    assert [candidate.rank for candidate in ranked] == [1, 2, 3, 4, 5, 6]
    aggregates = [candidate.score.aggregate for candidate in ranked]
    assert aggregates == sorted(aggregates, reverse=True)
    for earlier, later in zip(ranked, ranked[1:]):
        if earlier.score.aggregate == later.score.aggregate:
            assert earlier.seed < later.seed


def test_evaluate_request_is_deterministic():
    assert evaluate_request(_request(2026), 4) == evaluate_request(
        _request(2026), 4
    )


def test_rank_candidates_carries_matching_plan_and_score():
    plans = generate_candidates(_request(3), 4)
    ranked = rank_candidates(plans)
    assert {candidate.seed for candidate in ranked} == {
        plan.seed for plan in plans
    }
    for candidate in ranked:
        assert candidate.score == score_plan(candidate.plan)


# --- CLI --------------------------------------------------------------


def test_cli_candidates_writes_one_ranked_file_each(tmp_path):
    output = tmp_path / "cli.mid"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "midi_generator",
            "--bpm",
            "120",
            "--root",
            "C",
            "--scale",
            "minor",
            "--bars",
            "4",
            "--seed",
            "2026",
            "--candidates",
            "3",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    written = sorted(tmp_path.glob("cli_rank*_seed*.mid"))
    assert len(written) == 3
    assert result.stdout.count("rank ") == 3


def test_cli_rejects_zero_candidates(tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "midi_generator",
            "--bpm",
            "120",
            "--root",
            "C",
            "--scale",
            "minor",
            "--bars",
            "4",
            "--seed",
            "1",
            "--candidates",
            "0",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode != 0
    assert "--candidates" in result.stderr
