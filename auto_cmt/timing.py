"""
Time the stages of a BayesISOLA run_auto_cmt call without modifying BayesISOLA.
"""

import functools
import importlib
import threading
import time
import types
import warnings
from collections.abc import Callable
from typing import Any

import pandas as pd

# (stage label, module, attribute path) of the BayesISOLA calls to time.
# Classes are timed through their __init__. Stages that no longer exist in
# the installed BayesISOLA are skipped with a warning.
BAYESISOLA_STAGES = [
    ("download", "BayesISOLA.workflows", "get_mseed_stationxml"),
    ("station_selection", "BayesISOLA.workflows", "_apply_station_controls"),
    ("load_waveforms", "BayesISOLA.workflows", "load_streams_local"),
    ("mouse_detection", "BayesISOLA", "load_data.detect_mouse"),
    (
        "station_velocity_models",
        "BayesISOLA.workflows",
        "_prepare_axitra_station_models",
    ),
    ("process_data", "BayesISOLA", "process_data.__init__"),
    ("trim_filter", "BayesISOLA", "process_data.trim_filter_data"),
    (
        "greens_functions",
        "BayesISOLA.workflows",
        "_calculate_or_verify_axitra_multimodel",
    ),
    ("adaptive_grid_stage", "BayesISOLA.workflows", "_run_adaptive_axitra_stage"),
    ("covariance", "BayesISOLA", "covariance_matrix.__init__"),
    ("mt_inversion", "BayesISOLA", "resolve_MT.__init__"),
    ("jackknife", "BayesISOLA.workflows", "compute_station_jackknife"),
    ("results_uncertainty", "BayesISOLA.workflows", "_build_results"),
    ("write_tables", "BayesISOLA.workflows", "_write_result_tables"),
    ("plots", "BayesISOLA.workflows", "_render_native_outputs"),
    ("html_report", "BayesISOLA.workflows", "write_html_report"),
]

TIMINGS_FILENAME = "timings.csv"
PROFILE_FILENAME = "profile.prof"


class StageTimer:
    """
    Context manager timing selected BayesISOLA calls by temporarily wrapping them.

    Records calls, inclusive time and exclusive time (inclusive minus nested
    timed stages) per stage, plus the total time inside the context. Not safe
    for two timers running in the same process at once.

    Parameters
    ----------
    stages : list[tuple[str, str, str]], optional
        (stage label, module, attribute path) to time, by default
        BAYESISOLA_STAGES.
    """

    def __init__(self, stages: list[tuple[str, str, str]] = BAYESISOLA_STAGES):  # noqa: D107
        self.stages = stages
        self.stats = {label: [0, 0.0, 0.0] for label, _, _ in stages}
        self.total_s = 0.0
        self._patched: list[tuple[Any, str, Any]] = []
        self._lock = threading.Lock()
        self._local = threading.local()
        self._start = 0.0

    def _wrap(self, label: str, func: Callable) -> Callable:
        """
        Wrap a function so its calls are recorded under a stage label.

        Parameters
        ----------
        label : str
            Stage label.
        func : Callable
            Function to wrap.

        Returns
        -------
        Callable
            The timing wrapper.
        """

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            stack = self._local.__dict__.setdefault("stack", [])
            start = time.perf_counter()
            # Accumulates time spent in nested timed stages
            stack.append(0.0)
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                nested = stack.pop()
                if stack:
                    stack[-1] += elapsed
                with self._lock:
                    stats = self.stats[label]
                    stats[0] += 1
                    stats[1] += elapsed
                    stats[2] += elapsed - nested

        return wrapper

    def __enter__(self) -> "StageTimer":  # noqa: D105, PYI034
        for label, module_name, attr_path in self.stages:
            try:
                owner = importlib.import_module(module_name)
                *owner_path, attr = attr_path.split(".")
                for name in owner_path:
                    owner = getattr(owner, name)
                # Read the raw attribute so it can be restored exactly
                original = vars(owner)[attr]
            except (ImportError, AttributeError, KeyError):
                warnings.warn(
                    f"Timing stage {label!r} skipped: {module_name}.{attr_path} not found",
                    stacklevel=2,
                )
                continue
            if not isinstance(original, types.FunctionType):
                warnings.warn(
                    f"Timing stage {label!r} skipped: {module_name}.{attr_path} is not a function",
                    stacklevel=2,
                )
                continue
            setattr(owner, attr, self._wrap(label, original))
            self._patched.append((owner, attr, original))
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:  # noqa: D105
        self.total_s = time.perf_counter() - self._start
        for owner, attr, original in reversed(self._patched):
            setattr(owner, attr, original)
        self._patched.clear()

    def to_dataframe(self) -> pd.DataFrame:
        """
        Summarise the recorded timings.

        Returns
        -------
        pd.DataFrame
            One row per stage plus "other" (untimed code) and "total", with
            calls, inclusive_s, exclusive_s and percent (exclusive share of
            the total).
        """
        rows = [
            {
                "stage": label,
                "calls": calls,
                "inclusive_s": inclusive,
                "exclusive_s": exclusive,
            }
            for label, (calls, inclusive, exclusive) in self.stats.items()
        ]
        timed = sum(row["exclusive_s"] for row in rows)
        rows.append(
            {
                "stage": "other",
                "calls": 1,
                "inclusive_s": self.total_s - timed,
                "exclusive_s": self.total_s - timed,
            }
        )
        rows.append(
            {
                "stage": "total",
                "calls": 1,
                "inclusive_s": self.total_s,
                "exclusive_s": self.total_s,
            }
        )
        timings_df = pd.DataFrame(rows)
        timings_df["percent"] = (
            100 * timings_df["exclusive_s"] / max(self.total_s, 1e-9)
        )
        return timings_df.round({"inclusive_s": 2, "exclusive_s": 2, "percent": 1})
