"""
Run the three production CMT variants for one event while sharing all repeated work.
"""

import multiprocessing as mp
import re
import time
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer

from auto_cmt.run_cmt import (
    CMT_SOLUTION_FILENAME,
    DEFAULT_NZ_3DVM_PATH,
    DEFAULT_THREADS,
    build_nz_velocity_grid,
    load_event_row,
    run_cmt_inversion,
)
from qcore import cli

app = typer.Typer(pretty_exceptions_enable=False)

# Run folder names, in selection tie-break order (as the NZGMDB pipeline)
RUN_ALL_STATIONS = "all_stations"
RUN_AZIMUTH = "azimuth"
RUN_DROP_OUTLIERS_DEV = "drop_outliers_dev"

# Outlier station rule of the NZGMDB pipeline (nzgmdb/scripts/run_auto_cmt.py)
DEFAULT_OUTLIER_Z = 5.0
DEFAULT_OUTLIER_VR_FLOOR = -1.0
MIN_STATIONS_AFTER_DROP = 5

GF_STORE_DIRNAME = "gf_store"
STATION_VR_FILENAME = "station_vr.csv"
EVENT_TIMINGS_FILENAME = "event_timings.csv"


def compute_station_vr(station_df: pd.DataFrame) -> pd.Series:
    """
    Compute the mean variance reduction per station over its used components.

    Parameters
    ----------
    station_df : pd.DataFrame
        BayesISOLA station_df.csv table, one row per station component.

    Returns
    -------
    pd.Series
        Station VR indexed by station ID (NET.STA.LOC, "--" for no location).
    """
    used_df = station_df[station_df["used"].astype(bool)].dropna(
        subset=["variance_reduction"]
    )
    location = used_df["location"].fillna("").astype(str).str.strip()
    station_id = (
        used_df["network"].astype(str).str.strip()
        + "."
        + used_df["station"].astype(str).str.strip()
        + "."
        + location.where(location != "", "--")
    )
    return used_df.groupby(station_id)["variance_reduction"].mean()


def robust_z_score(station_vr: pd.Series) -> pd.Series:
    """
    Compute the robust (median / MAD) z-score of each station's VR.

    Parameters
    ----------
    station_vr : pd.Series
        Station VR indexed by station ID.

    Returns
    -------
    pd.Series
        Robust z-score indexed by station ID.
    """
    median = station_vr.median()
    # Floor the MAD so identical VRs don't divide by zero
    mad = max(1.4826 * (station_vr - median).abs().median(), 1e-6)
    return (station_vr - median) / mad


def find_outlier_stations(
    station_vr_all: pd.Series,
    station_vr_azimuth: pd.Series,
    outlier_z: float = DEFAULT_OUTLIER_Z,
    outlier_vr_floor: float = DEFAULT_OUTLIER_VR_FLOOR,
) -> tuple[list[str], pd.DataFrame]:
    """
    Find stations that are VR outliers in both the all-stations and azimuth runs.

    Same rule as the NZGMDB pipeline: an outlier has a robust z-score below
    -outlier_z and a VR below outlier_vr_floor, in both runs, and stations are
    only dropped while at least MIN_STATIONS_AFTER_DROP remain.

    Parameters
    ----------
    station_vr_all : pd.Series
        Station VR from the all-stations run.
    station_vr_azimuth : pd.Series
        Station VR from the azimuth-control run.
    outlier_z : float, optional
        Robust z-score magnitude a station must fall below, by default 5.0.
    outlier_vr_floor : float, optional
        Station VR a station must fall below, by default -1.0.

    Returns
    -------
    dropped : list[str]
        Station IDs (NET.STA.LOC) to drop.
    station_vr_df : pd.DataFrame
        Per-station VR, z-score and outlier flags for both runs.
    """
    station_vr_df = pd.DataFrame(
        index=station_vr_all.index.union(station_vr_azimuth.index)
    )
    station_vr_df.index.name = "station_id"
    for name, station_vr in [
        (RUN_ALL_STATIONS, station_vr_all),
        (RUN_AZIMUTH, station_vr_azimuth),
    ]:
        z = robust_z_score(station_vr)
        outlier = (z < -outlier_z) & (station_vr < outlier_vr_floor)
        station_vr_df[f"vr_{name}"] = station_vr
        station_vr_df[f"z_{name}"] = z
        station_vr_df[f"outlier_{name}"] = outlier.reindex(
            station_vr_df.index, fill_value=False
        )
    outlier_cols = [f"outlier_{RUN_ALL_STATIONS}", f"outlier_{RUN_AZIMUTH}"]
    station_vr_df["dropped"] = station_vr_df[outlier_cols].all(axis=1)
    dropped = station_vr_df.index[station_vr_df["dropped"]].tolist()
    if dropped and len(station_vr_all) - len(dropped) < MIN_STATIONS_AFTER_DROP:
        station_vr_df["dropped"] = False
        dropped = []
    return dropped, station_vr_df.reset_index()


def read_station_df(run_dir: Path) -> pd.DataFrame:
    """
    Read a run's station_df.csv, keeping station codes as strings.

    Parameters
    ----------
    run_dir : Path
        CMT run folder.

    Returns
    -------
    pd.DataFrame
        Station/component fit table.
    """
    return pd.read_csv(
        run_dir / "results" / "station_df.csv",
        dtype={"network": str, "station": str, "location": str},
    )


def _run_variant(
    event_row: pd.Series, run_dir: Path, velocity_model: Any, kwargs: dict[str, Any]
) -> None:
    """
    Run one CMT variant (target of a child process).

    Parameters
    ----------
    event_row : pd.Series
        Event row.
    run_dir : Path
        Output folder of the run.
    velocity_model : Any
        Velocity grid from ``build_nz_velocity_grid``.
    kwargs : dict
        Passed to ``run_cmt_inversion``.
    """
    run_cmt_inversion(event_row, run_dir, velocity_model, **kwargs)


def _wait_for_solution(process: mp.Process, run_dir: Path) -> None:
    """
    Wait until a variant has written cmt_solution.csv (its figures may still be running).

    Parameters
    ----------
    process : mp.Process
        Process running the variant.
    run_dir : Path
        Output folder of the run.
    """
    solution = run_dir / CMT_SOLUTION_FILENAME
    while process.is_alive() and not solution.exists():
        time.sleep(0.5)
    if not solution.exists():
        raise RuntimeError(
            f"CMT run {run_dir.name} failed (exit code {process.exitcode})"
        )


@cli.from_docstring(app)
def run_cmt_event(
    event_id: Annotated[str, typer.Argument()],
    event_csv_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output_dir: Annotated[Path, typer.Argument(file_okay=False)],
    real_time: Annotated[bool, typer.Option(is_flag=True)] = False,
    nz_3dvm_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_NZ_3DVM_PATH,
    threads: Annotated[int, typer.Option()] = DEFAULT_THREADS,
    outlier_z: Annotated[float, typer.Option()] = DEFAULT_OUTLIER_Z,
    outlier_vr_floor: Annotated[float, typer.Option()] = DEFAULT_OUTLIER_VR_FLOOR,
    share_work: Annotated[bool, typer.Option()] = True,
    background_figures: Annotated[bool, typer.Option()] = True,
    shared_xl: Annotated[bool, typer.Option()] = False,
) -> pd.DataFrame:
    """
    Run the all_stations, azimuth and drop_outliers_dev CMT runs of one event.

    Same three runs and outlier rule as the NZGMDB pipeline, but run one after
    another, each with all ``threads`` (drop_outliers_dev needs the station
    fits of the first two anyway). With ``share_work`` the waveforms are
    downloaded once and all runs share one Green's function store (identical
    receivers are computed once), which does not change any result.

    With ``background_figures`` each run is its own process: as soon as it has
    written cmt_solution.csv the next run starts, while its figures and HTML
    report are drawn in the background. ``shared_xl`` (off by default) lets the
    station-subset runs reuse the all_stations Green's functions at the cost of
    a small numerical change.

    Parameters
    ----------
    event_id : str
        GeoNet event/public ID, e.g. "2026p576643".
    event_csv_path : Path
        CSV with the event row (evid, datetime, lat, lon, depth, mag, ...).
    output_dir : Path
        Event output directory; each run writes to a subfolder.
    real_time : bool, optional
        Query GeoNet's near-real-time FDSN client.
    nz_3dvm_path : Path, optional
        3-D NZ velocity model CSV.
    threads : int, optional
        Axitra thread count.
    outlier_z : float, optional
        Robust z-score magnitude a station must fall below to be an outlier.
    outlier_vr_floor : float, optional
        Station VR a station must fall below to be an outlier.
    share_work : bool, optional
        Download once and share the Green's function store between runs.
    background_figures : bool, optional
        Start the next run as soon as the previous one has written its
        solution, drawing its figures in the background.
    shared_xl : bool, optional
        Give the azimuth and drop_outliers_dev runs the all_stations run's
        Axitra ``xl`` so they reuse its Green's functions (small numerical
        change to those two runs).

    Returns
    -------
    pd.DataFrame
        Wall-clock seconds per run and for the whole event.
    """
    start = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    event_row = load_event_row(event_id, event_csv_path)
    velocity_model = build_nz_velocity_grid(nz_3dvm_path)
    gf_store_dir = output_dir / GF_STORE_DIRNAME if share_work else None
    timings = []
    background: list[tuple[str, float, mp.Process]] = []
    # forked children inherit the velocity grid instead of rebuilding it
    context = mp.get_context("fork")

    def run(name: str, station_df: Path | None, **kwargs: Any) -> Path:
        run_start = time.perf_counter()
        run_dir = output_dir / name
        print(f"\n=== {event_id}: {name} ===")
        kwargs = {
            "real_time": real_time,
            "threads": threads,
            "station_df": station_df,
            "gf_store_dir": gf_store_dir,
            **kwargs,
        }
        if background_figures:
            (run_dir / CMT_SOLUTION_FILENAME).unlink(missing_ok=True)
            process = context.Process(
                target=_run_variant, args=(event_row, run_dir, velocity_model, kwargs)
            )
            process.start()
            _wait_for_solution(process, run_dir)
            background.append((name, run_start, process))
        else:
            _run_variant(event_row, run_dir, velocity_model, kwargs)
        timings.append(
            {
                "run": name,
                "solution_s": time.perf_counter() - run_start,
                "solution_at_s": time.perf_counter() - start,
            }
        )
        return run_dir

    all_dir = run(RUN_ALL_STATIONS, None)
    downloaded = (
        all_dir / "metadata" / "stations_downloaded.csv" if share_work else None
    )
    subset_overrides = {}
    if shared_xl:
        grdat = (all_dir / "green" / "grdat.hed").read_text()
        subset_overrides["gf_xl_km"] = (
            float(re.search(r"xl=([0-9.]+)", grdat).group(1)) / 1e3
        )
    azimuth_dir = run(
        RUN_AZIMUTH, downloaded, azimuth_control=True, overrides=subset_overrides
    )

    dropped, station_vr_df = find_outlier_stations(
        compute_station_vr(read_station_df(all_dir)),
        compute_station_vr(read_station_df(azimuth_dir)),
        outlier_z,
        outlier_vr_floor,
    )
    station_vr_df.to_csv(output_dir / STATION_VR_FILENAME, index=False)
    print(f"Dropping stations: {dropped or 'none'}")
    run(
        RUN_DROP_OUTLIERS_DEV,
        downloaded,
        drop_stations=dropped,
        deviatoric=True,
        overrides=subset_overrides,
    )
    timings.append(
        {"run": "all solutions", "solution_at_s": time.perf_counter() - start}
    )

    # figures still being drawn in the background
    for name, run_start, process in background:
        process.join()
        if process.exitcode != 0:
            print(
                f"Warning: figures/report of {name} ended with exit code {process.exitcode}"
            )

    timings.append({"run": "event", "solution_at_s": time.perf_counter() - start})
    timings_df = pd.DataFrame(timings)
    timings_df.to_csv(output_dir / EVENT_TIMINGS_FILENAME, index=False)
    print(timings_df.to_string(index=False))
    return timings_df


if __name__ == "__main__":
    app()
