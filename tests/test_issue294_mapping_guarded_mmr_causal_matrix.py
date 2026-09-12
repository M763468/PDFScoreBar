from copy import deepcopy

from tools.issue294.run_mapping_guarded_mmr_causal_matrix import _condition_systems


def _support(prefix: str):
    return {
        "views": {
            "primary": {
                "pages": [
                    {
                        "systems": [
                            {
                                "staves": [{"bbox": [1, 10 if prefix == "F" else 20, 100, 30]}],
                                "measures": [
                                    {"bbox": [5 if prefix == "F" else 7, 10, 50, 30]},
                                    {"bbox": [50, 10, 90, 30]},
                                ],
                            }
                        ]
                    }
                ]
            },
            "implicit_start_alternate": {
                "pages": [
                    {
                        "systems": [
                            {
                                "staves": [{"bbox": [2, 11 if prefix == "F" else 21, 100, 31]}],
                                "measures": [
                                    {"bbox": [4 if prefix == "F" else 6, 11, 50, 31]},
                                    {"bbox": [50, 11, 90, 31]},
                                ],
                            }
                        ]
                    }
                ]
            },
            "fallback": {
                "pages": [
                    {
                        "systems": [
                            {
                                "staves": [{"bbox": [3, 12 if prefix == "F" else 22, 100, 32]}],
                                "measures": [
                                    {"bbox": [3 if prefix == "F" else 8, 12, 50, 32]},
                                    {"bbox": [50, 12, 90, 32]},
                                ],
                            }
                        ]
                    }
                ]
            },
        }
    }


def test_view_source_conditions_are_isolated():
    frozen = _support("F")
    native = _support("N")

    primary = _condition_systems(
        frozen, native, system_index=0, measure_index=0, condition="primary_native_only"
    )
    assert primary["primary"] == native["views"]["primary"]["pages"][0]["systems"][0]
    assert (
        primary["implicit_start_alternate"]
        == frozen["views"]["implicit_start_alternate"]["pages"][0]["systems"][0]
    )
    assert primary["fallback"] == frozen["views"]["fallback"]["pages"][0]["systems"][0]

    alternate = _condition_systems(
        frozen, native, system_index=0, measure_index=0, condition="alternate_native_only"
    )
    assert alternate["primary"] == frozen["views"]["primary"]["pages"][0]["systems"][0]
    assert (
        alternate["implicit_start_alternate"]
        == native["views"]["implicit_start_alternate"]["pages"][0]["systems"][0]
    )

    fallback = _condition_systems(
        frozen, native, system_index=0, measure_index=0, condition="fallback_native_only"
    )
    assert fallback["fallback"] == native["views"]["fallback"]["pages"][0]["systems"][0]


def test_primary_component_conditions_change_only_requested_component():
    frozen = _support("F")
    native = _support("N")
    frozen_primary = frozen["views"]["primary"]["pages"][0]["systems"][0]
    native_primary = native["views"]["primary"]["pages"][0]["systems"][0]

    measure = _condition_systems(
        frozen,
        native,
        system_index=0,
        measure_index=0,
        condition="primary_measure_native_only",
    )
    assert measure["primary"]["measures"][0]["bbox"] == native_primary["measures"][0]["bbox"]
    assert measure["primary"]["measures"][1] == frozen_primary["measures"][1]
    assert measure["primary"]["staves"] == frozen_primary["staves"]

    staff = _condition_systems(
        frozen,
        native,
        system_index=0,
        measure_index=0,
        condition="primary_staff_native_only",
    )
    assert staff["primary"]["measures"] == frozen_primary["measures"]
    assert staff["primary"]["staves"] == native_primary["staves"]

    reverted_measure = _condition_systems(
        frozen,
        native,
        system_index=0,
        measure_index=0,
        condition="native_revert_primary_measure",
    )
    assert (
        reverted_measure["primary"]["measures"][0]["bbox"] == frozen_primary["measures"][0]["bbox"]
    )
    assert reverted_measure["primary"]["staves"] == native_primary["staves"]

    reverted_staff = _condition_systems(
        frozen,
        native,
        system_index=0,
        measure_index=0,
        condition="native_revert_primary_staff",
    )
    assert reverted_staff["primary"]["measures"] == native_primary["measures"]
    assert reverted_staff["primary"]["staves"] == frozen_primary["staves"]


def test_condition_builder_does_not_mutate_inputs():
    frozen = _support("F")
    native = _support("N")
    before_frozen = deepcopy(frozen)
    before_native = deepcopy(native)
    _condition_systems(
        frozen,
        native,
        system_index=0,
        measure_index=0,
        condition="native_revert_primary_staff",
    )
    assert frozen == before_frozen
    assert native == before_native
