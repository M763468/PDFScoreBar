from tools.issue277.rescore_targeted_mmr_positive_risk_slice import (
    classify_change,
    result_state,
)
from tools.issue277.run_targeted_mmr_positive_risk_slice import (
    TargetedRetryProcessor,
    retry_candidate_acceptable,
)


class Harness(TargetedRetryProcessor):
    def __init__(
        self,
        *,
        one_shot,
        normalized=(None, 0.0),
        shifted=(None, 0.0),
        j2=(None, 0.0, "j2", 0),
    ):
        self.decision_trace = []
        self.one_shot_result = one_shot
        self.normalized_result = normalized
        self.shifted_result = shifted
        self.j2_result = j2
        self.normalized_calls = 0
        self.shifted_calls = 0
        self.j2_calls = 0
        self.threshold = 0.5
        self.ONE_BAR_VETO_PROB_MAX = 0.7
        self.ONE_BAR_VETO_MIN_EVIDENCE = 2
        self.JITTER_SCORE_TRIGGER = 5.0

    def _production_once(self, *args):
        return self.one_shot_result

    def _production_j2(self, *args):
        self.j2_calls += 1
        return self.j2_result

    def _run_normalized_staff(self, *args):
        self.normalized_calls += 1
        return self.normalized_result

    def _run_shifted_staff(self, *args):
        self.shifted_calls += 1
        return self.shifted_result


def call(processor, *, prob=0.99):
    return processor._detect_number_with_evidence(
        None,
        {"staves": [{"bbox": [0, 0, 100, 20]}]},
        0,
        0,
        100,
        20,
        prob,
        1000,
        1000,
    )


def test_high_score_one_shot_is_authoritative_and_pays_no_retry():
    processor = Harness(
        one_shot=(9, 44.0, "one-shot", 0),
        normalized=(6, 50.0),
        shifted=(6, 50.0),
        j2=(6, 50.0, "j2", 0),
    )
    result = call(processor)
    assert result[0] == 9
    assert processor.normalized_calls == 0
    assert processor.shifted_calls == 0
    assert processor.j2_calls == 0
    assert processor.decision_trace[-1]["stage"] == "one_shot_high_score_passthrough"


def test_low_score_uses_positive_normalized_retry_before_j2():
    processor = Harness(
        one_shot=(97, -44.0, "one-shot", 0),
        normalized=(5, 24.0),
        shifted=(6, 20.0),
        j2=(5, 25.0, "j2", 0),
    )
    result = call(processor)
    assert result[0] == 5
    assert processor.normalized_calls == 1
    assert processor.shifted_calls == 0
    assert processor.j2_calls == 0
    assert processor.decision_trace[-1]["stage"] == "targeted_normalized_unmasked_heavy_dilate"


def test_none_one_shot_can_be_rescued_by_positive_scale_relative_retry():
    processor = Harness(
        one_shot=(None, 0.0, "one-shot", 0),
        normalized=(None, 0.0),
        shifted=(6, 24.0),
        j2=(None, 0.0, "j2", 0),
    )
    result = call(processor)
    assert result[0] == 6
    assert processor.normalized_calls == 1
    assert processor.shifted_calls == 1
    assert processor.j2_calls == 0
    assert processor.decision_trace[-1]["stage"] == "targeted_scale_relative_x1_retry"


def test_negative_retry_candidate_cannot_replace_low_score_baseline():
    processor = Harness(
        one_shot=(37, -10.0, "one-shot", 0),
        normalized=(None, 0.0),
        shifted=(111, -68.0),
        j2=(37, 29.0, "j2", 0),
    )
    result = call(processor)
    assert result[0] == 37
    assert processor.normalized_calls == 1
    assert processor.shifted_calls == 1
    assert processor.j2_calls == 1
    assert processor.decision_trace[-1]["stage"] == "merged_j2_low_score_fallback"


def test_unresolved_none_does_not_repeat_j2_one_shot():
    processor = Harness(
        one_shot=(None, 0.0, "one-shot", 0),
        normalized=(None, 0.0),
        shifted=(111, -68.0),
        j2=(7, 10.0, "should-not-run", 0),
    )
    result = call(processor)
    assert result[0] is None
    assert processor.j2_calls == 0
    assert processor.decision_trace[-1]["stage"] == "one_shot_none_passthrough"


def test_one_bar_sensitive_case_delegates_to_merged_j2():
    processor = Harness(
        one_shot=(11, -16.0, "one-shot", 2),
        normalized=(2, 40.0),
        shifted=(2, 40.0),
        j2=(None, 0.0, "j2-veto", 2),
    )
    result = call(processor, prob=0.52)
    assert result[0] is None
    assert processor.normalized_calls == 0
    assert processor.shifted_calls == 0
    assert processor.j2_calls == 1
    assert processor.decision_trace[-1]["stage"] == "merged_j2_contract_fallback"


def test_retry_candidate_requires_positive_spatial_score_and_span_value():
    assert retry_candidate_acceptable(3, 0.1)
    assert not retry_candidate_acceptable(3, 0.0)
    assert not retry_candidate_acceptable(3, -0.1)
    assert not retry_candidate_acceptable(1, 50.0)
    assert not retry_candidate_acceptable(None, 50.0)


def test_accepted_rescore_classification_distinguishes_improvement_and_regression():
    assert result_state(4, 4) == "exact"
    assert result_state(5, 4) == "mismatch"
    assert result_state(None, 4) == "absent"
    assert classify_change("mismatch", "exact", True) == "improvement"
    assert classify_change("exact", "mismatch", True) == "regression"
    assert classify_change("exact", "absent", True) == "regression"
    assert classify_change("mismatch", "mismatch", True) == "changed_nonexact"
    assert classify_change("exact", "exact", False) == "unchanged"
