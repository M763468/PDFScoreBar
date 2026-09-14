#!/usr/bin/env python3
"""Compatibility entrypoint for the Issue #277 visual geometry probe.

The v1 probe assumed ``probe_hbar_anchored_roi._sensitive_keys`` returned a flat
sequence of mapping objects. That helper actually returns ``page_id -> set[(system,
measure)]``. Keep the original experiment implementation unchanged and adapt the
helper result to the flat shape expected by its ``run`` function.
"""

from __future__ import annotations

import probe_hbar_anchored_roi as hbar_probe
import probe_visual_geometry_canonicalization as original


_raw_sensitive_keys = hbar_probe._sensitive_keys


def _flat_sensitive_keys(payload):
    by_page = _raw_sensitive_keys(payload)
    return [
        {
            "page_id": page_id,
            "system": system_idx,
            "measure": measure_idx,
            "key": f"{page_id} s{system_idx} m{measure_idx}",
        }
        for page_id in sorted(by_page)
        for system_idx, measure_idx in sorted(by_page[page_id])
    ]


def main() -> int:
    hbar_probe._sensitive_keys = _flat_sensitive_keys
    return original.main()


if __name__ == "__main__":
    raise SystemExit(main())
