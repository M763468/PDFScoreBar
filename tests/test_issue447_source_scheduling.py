"""GPU-free ordering/lifetime guards for the investigation-only source shim."""

import threading
import time
import unittest
from pathlib import Path

from tools.issue447.pipeline_poc import OrderedJobs, install_source_prefetch


class SourceSchedulingTests(unittest.TestCase):
    def test_parallel_completion_is_consumed_in_input_order(self):
        released = threading.Event()
        completed = []

        def execute(key):
            if key == "first":
                self.assertTrue(released.wait(2))
            else:
                completed.append(key)
                released.set()
            return key

        pool = OrderedJobs(["first", "second"], execute, 2)
        try:
            self.assertEqual([pool.result(k) for k in ("first", "second")], ["first", "second"])
            self.assertEqual(completed, ["second"])
        finally:
            pool.close()

    def test_worker_bound_and_same_input_contract_in_both_modes(self):
        for workers in (1, 2):
            with self.subTest(workers=workers):
                lock = threading.Lock()
                active, peak = [0], [0]

                class Detector:
                    def __init__(self):
                        self.images = [Path(f"page_{i:03}.png") for i in range(3)]
                        self._last_sr_batch_result = {
                            "status": "completed",
                            "outputs": [
                                {"image": str(p.resolve()), "identity": i}
                                for i, p in enumerate(self.images)
                            ],
                        }

                    def _source_page_worker(self, *, image, precomputed_sr, **kwargs):
                        with lock:
                            active[0] += 1
                            peak[0] = max(peak[0], active[0])
                        time.sleep(0.02)
                        with lock:
                            active[0] -= 1
                        return image, precomputed_sr["identity"]

                install_source_prefetch(workers, detector_class=Detector)
                detector = Detector()
                results = [
                    detector._source_page_worker(
                        image=p,
                        worker_output=Path("out"),
                        baseline_output=Path("base"),
                        support_output=Path("support"),
                        precomputed_sr={},
                    )
                    for p in detector.images
                ]
                self.assertEqual([r[1] for r in results], [0, 1, 2])
                self.assertEqual(peak[0], workers)
                self.assertEqual(active[0], 0)
                self.assertFalse(hasattr(detector, "_issue447_ordered_jobs"))

    def test_completed_sr_boundary_is_required(self):
        class Detector:
            images = [Path("page.png")]
            _last_sr_batch_result = {"status": "failed"}

            def _source_page_worker(self, **kwargs):
                raise AssertionError("must not start source work")

        install_source_prefetch(2, detector_class=Detector)
        with self.assertRaisesRegex(RuntimeError, "completed production SR"):
            Detector()._source_page_worker(
                image=Path("page.png"),
                worker_output=Path("out"),
                baseline_output=Path("base"),
                support_output=Path("support"),
                precomputed_sr={},
            )

    def test_worker_failure_propagates_without_serial_fallback(self):
        def execute(key):
            raise RuntimeError("source failure")

        pool = OrderedJobs(["bad"], execute, 2)
        try:
            with self.assertRaisesRegex(RuntimeError, "source failure"):
                pool.result("bad")
        finally:
            pool.close()


if __name__ == "__main__":
    unittest.main()
