from tools.issue277.run_j2_mmr_full68_reference import J2ReferenceProcessor


def test_j2_reference_processor_exposes_decision_trace_contract():
    processor = object.__new__(J2ReferenceProcessor)
    processor.decision_trace = [{"stage": "stale"}]
    processor.reset_decision_trace()
    assert processor.decision_trace == []
