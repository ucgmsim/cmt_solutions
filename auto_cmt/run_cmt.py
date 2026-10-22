"""
Run the 1-D CMT inversion (BayesISOLA) for a single GeoNet event.
"""

import cProfile
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated, Any

import matplotlib
import pandas as pd
import typer
from BayesISOLA.gf_helpers import build_regular_velocity_grid
from BayesISOLA.workflows import run_auto_cmt
from obspy.clients.fdsn import Client as FDSNClient

from auto_cmt.timing import PROFILE_FILENAME, TIMINGS_FILENAME, StageTimer
from qcore import cli

app = typer.Typer(pretty_exceptions_enable=False)

# GeoNet's near-real-time FDSN service. The standard "GEONET" client is not
# updated in near real time, so a just-happened event is not there yet -
# --real-time queries this service instead
NRT_BASE_URL = "https://service-nrt.geonet.org.nz"

# 3-D NZ velocity model bundled with this package, used by default to build
# station/path-specific 1-D Axitra models.
DEFAULT_NZ_3DVM_PATH = Path(__file__).resolve().parent / "nz3dvm_2p3.csv"

DEFAULT_THREADS = 12

# Columns the event CSV must provide
REQUIRED_EVENT_COLUMNS = ["evid", "datetime", "lat", "lon", "depth", "mag"]

# GISOLA-style azimuthal station thinning, used when azimuth_control=True
AZIMUTH_CONTROL = {
    "azimuth_selection": True,
    "azimuth_min_sectors": 3,
    "azimuth_max_stations_per_sector": 2,
    "minimum_stations": 5,
}

# Leave-one-station-out robustness check on the final grid
STATION_JACKKNIFE = {
    "jackknife_min_stations": 4,
}

CMT_SOLUTION_FILENAME = "cmt_solution.csv"


def build_nz_velocity_grid(nz_3dvm_path: Path = DEFAULT_NZ_3DVM_PATH) -> Any:
    """
    Build the regular velocity grid used to create the 1-D Axitra models.

    Split out from the inversion so callers running several inversions for
    the same event can build it once and reuse it.

    Parameters
    ----------
    nz_3dvm_path : Path, optional
        3-D NZ velocity model CSV, by default the bundled ``nz3dvm_2p3.csv``.

    Returns
    -------
    Any
        BayesISOLA ``gf_helpers`` velocity grid, passed to
        ``run_cmt_inversion`` as ``velocity_model``.
    """
    return build_regular_velocity_grid(
        pd.read_csv(nz_3dvm_path),
        x_col="Longitude",
        y_col="Latitude",
        depth_col="Depth(km_BSL)",
        vp_col="Vp",
        vs_col="Vs",
        density_col="Density",
        qs_col="Qs",
        qp_col="Qp",
        coordinate_crs="EPSG:4326",
        interpolation_crs="EPSG:2193",
    )


def load_event_row(event_id: str, event_csv_path: Path) -> pd.Series:
    """
    Load and check the event row from an event CSV.

    Parameters
    ----------
    event_id : str
        GeoNet event/public ID, must match the CSV's ``evid``.
    event_csv_path : Path
        CSV with the event row (evid, datetime, lat, lon, depth, mag, ...) -
        same schema as GeoNet's earthquake_source_table.csv.

    Returns
    -------
    pd.Series
        The first (event) row of the CSV.
    """
    event_df = pd.read_csv(event_csv_path)
    missing = [c for c in REQUIRED_EVENT_COLUMNS if c not in event_df.columns]
    if missing:
        raise ValueError(f"Missing column(s) {missing} in {event_csv_path}")

    event_row = event_df.iloc[0]
    csv_evid = str(event_row["evid"])
    if event_id != csv_evid:
        raise ValueError(
            f"event_id={event_id!r} does not match evid={csv_evid!r} in {event_csv_path}"
        )
    return event_row


def write_cmt_solution_csv(run: dict, event_row: pd.Series, output_dir: Path) -> Path:
    """
    Write a flat cmt_solution.csv summary of a completed run.

    Matches the GeoNet regional CMT catalogue column layout: PublicID, Date,
    Latitude, Longitude, strike1, dip1, rake1, strike2, dip2, rake2, ML, Mw,
    Mo, CD.

    Parameters
    ----------
    run : dict
        The ``run_auto_cmt`` return value.
    event_row : pd.Series
        The event row used for the run.
    output_dir : Path
        Run output directory to write the CSV into.

    Returns
    -------
    Path
        Path to the written cmt_solution.csv.
    """
    results = run["results"]
    centroid_row = results["centroid"].iloc[0]
    summary_row = results["summary"].iloc[0]

    # ML is GeoNet's own catalogue magnitude, carried over only when the
    # event was actually reported with local magnitude - BayesISOLA itself
    # only produces Mw (moment magnitude), never ML.
    mag_type = str(event_row.get("mag_type", ""))
    ml_value = (
        round(float(event_row["mag"]), 1) if mag_type.strip().upper() == "ML" else None
    )

    cmt_solution_df = pd.DataFrame(
        [
            {
                "PublicID": str(event_row["evid"]),
                "Date": str(centroid_row["origin_time"]),
                "Latitude": round(float(centroid_row["centroid_lat"]), 3),
                "Longitude": round(float(centroid_row["centroid_lon"]), 3),
                "strike1": round(float(summary_row["NP1_strike_deg"])),
                "dip1": round(float(summary_row["NP1_dip_deg"])),
                "rake1": round(float(summary_row["NP1_rake_deg"])),
                "strike2": round(float(summary_row["NP2_strike_deg"])),
                "dip2": round(float(summary_row["NP2_dip_deg"])),
                "rake2": round(float(summary_row["NP2_rake_deg"])),
                "ML": ml_value,
                "Mw": round(float(summary_row["Mw"]), 2),
                # BayesISOLA reports M0_Nm in Newton-metres; the GeoNet CMT
                # catalogue format expects dyne-cm (1 Nm = 1e7 dyne-cm).
                "Mo": float(summary_row["M0_Nm"]) * 1e7,
                "CD": round(float(centroid_row["centroid_depth_km"]), 1),
            }
        ]
    )

    cmt_solution_path = output_dir / CMT_SOLUTION_FILENAME
    cmt_solution_df.to_csv(cmt_solution_path, index=False)
    return cmt_solution_path


def run_cmt_inversion(
    event_row: pd.Series,
    output_dir: Path,
    velocity_model: Any,
    real_time: bool = False,
    threads: int = DEFAULT_THREADS,
    min_radius_km: float = 0.0,
    max_radius_km: float | None = None,
    azimuth_control: bool = False,
    drop_stations: list[str] | None = None,
    deviatoric: bool = False,
    profile: bool = False,
) -> dict:
    """
    Run a single BayesISOLA CMT inversion and write cmt_solution.csv.

    Stage timings are always written to results/timings.csv, even if the
    inversion fails.

    Parameters
    ----------
    event_row : pd.Series
        Event row from ``load_event_row``.
    output_dir : Path
        Output directory for the inversion results (created if missing).
    velocity_model : Any
        Velocity grid from ``build_nz_velocity_grid``.
    real_time : bool, optional
        Query GeoNet's near-real-time FDSN client instead of the standard
        "GEONET" client, by default False.
    threads : int, optional
        Axitra thread count, by default 12.
    min_radius_km : float, optional
        Inner radius (km) of the station search annulus, by default 0.0.
    max_radius_km : float, optional
        Outer radius (km) of the station search annulus, by default None
        (magnitude-scaled).
    azimuth_control : bool, optional
        Apply azimuthal station thinning (``AZIMUTH_CONTROL``), by default False.
    drop_stations : list[str], optional
        Stations to exclude, as ``STA``, ``NET.STA`` or ``NET.STA.LOC``,
        by default None.
    deviatoric : bool, optional
        Invert for a deviatoric moment tensor only (no isotropic component),
        by default False.
    profile : bool, optional
        Also write a cProfile dump of the inversion to results/profile.prof,
        by default False.

    Returns
    -------
    dict
        The ``run_auto_cmt`` return value; ``run["results"]`` holds the
        curated centroid/summary/station-fit tables and ``run["timings"]``
        the stage timings.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input").mkdir(parents=True, exist_ok=True)

    # BayesISOLA plots with pyplot and forks inversion workers. An interactive
    # backend (TkAgg when a display is available) is not fork-safe and aborts
    # the run with "Tcl_AsyncDelete: async handler deleted by the wrong thread"
    matplotlib.use("Agg")

    mag_event = float(event_row["mag"])
    step_x_km = 1.0 if mag_event <= 5.0 else 2.0
    client = FDSNClient(base_url=NRT_BASE_URL) if real_time else "GEONET"

    timer = StageTimer()
    profiler = cProfile.Profile() if profile else nullcontext()
    try:
        with timer, profiler:
            run = run_auto_cmt(
                str(event_row["evid"]),
                event_row["datetime"],
                float(event_row["lon"]),
                float(event_row["lat"]),
                float(event_row["depth"]),
                mag_event,
                output_dir=output_dir,
                velocity_model=velocity_model,
                client=client,
                min_radius_km=min_radius_km,
                max_radius_km=max_radius_km,
                location_unc_km=3.0,
                time_unc_s=3.0,
                min_depth_km=3.0,
                min_depth_multiplier=0.3,
                max_depth_multiplier=3.0,
                step_x_km=step_x_km,
                step_z_km=1.0,
                adaptive_grid_search={
                    "adaptive_grid": True,
                    "adaptive_refine_factor": 0,
                },
                drop_stations=drop_stations or None,
                azimuth_control=AZIMUTH_CONTROL if azimuth_control else None,
                station_jackknife=STATION_JACKKNIFE,
                freqmin=0.02,
                freqmax=0.06,
                threads=threads,
                covariance="noise",
                crosscovariance=True,
                deviatoric=deviatoric,
                n_uncertainty=1000,
                plot=True,
                plot_preset="summary",
                show=False,
                html_output=True,
                write_report=True,
            )
    finally:
        # Keep timings for failed runs too
        results_dir = output_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        timings_df = timer.to_dataframe()
        timings_df.to_csv(results_dir / TIMINGS_FILENAME, index=False)
        if profile:
            profiler.dump_stats(results_dir / PROFILE_FILENAME)
        print(f"\nCMT stage timings:\n{timings_df.to_string(index=False)}")
    run["timings"] = timings_df

    cmt_solution_path = write_cmt_solution_csv(run, event_row, output_dir)
    print(f"\nWrote CMT solution summary to {cmt_solution_path}")

    return run


@cli.from_docstring(app)
def run_cmt(
    event_id: Annotated[str, typer.Argument()],
    event_csv_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Argument(
            file_okay=False,
        ),
    ],
    real_time: Annotated[bool, typer.Option(is_flag=True)] = False,
    nz_3dvm_path: Annotated[
        Path,
        typer.Option(
            exists=True,
            dir_okay=False,
        ),
    ] = DEFAULT_NZ_3DVM_PATH,
    threads: Annotated[int, typer.Option()] = DEFAULT_THREADS,
    min_radius_km: Annotated[float, typer.Option()] = 0.0,
    max_radius_km: Annotated[float | None, typer.Option()] = None,
    azimuth_control: Annotated[bool, typer.Option(is_flag=True)] = False,
    drop_stations: Annotated[list[str] | None, typer.Option()] = None,
    deviatoric: Annotated[bool, typer.Option(is_flag=True)] = False,
    profile: Annotated[bool, typer.Option(is_flag=True)] = False,
) -> dict:
    """
    Run the 1-D CMT inversion for one GeoNet event.

    By default this queries GeoNet's standard "GEONET" FDSN client, which
    works for any event already in GeoNet's archive. Pass ``--real-time``
    for a just-happened event that has not propagated to the standard
    archive yet, which queries GeoNet's near-real-time service
    (``service-nrt.geonet.org.nz``) instead.

    Parameters
    ----------
    event_id : str
        GeoNet event/public ID, e.g. "2026p576643".
    event_csv_path : Path
        CSV with the event row (evid, datetime, lat, lon, depth, mag, ...) -
        same schema as GeoNet's earthquake_source_table.csv.
    output_dir : Path
        Output directory for the CMT inversion results.
    real_time : bool, optional
        Query GeoNet's near-real-time FDSN client instead of the standard
        "GEONET" client. Use this for an event that has only just happened.
    nz_3dvm_path : Path, optional
        3-D NZ velocity model CSV, used to build the station/path-specific
        1-D Axitra models. Defaults to the copy bundled with this package
        (``nz3dvm_2p3.csv``); pass a different path to use another model.
    threads : int, optional
        Axitra thread count.
    min_radius_km : float, optional
        Inner radius (km) of the station search annulus.
    max_radius_km : float, optional
        Outer radius (km) of the station search annulus.
    azimuth_control : bool, optional
        Apply azimuthal station thinning (min 3 occupied 45-degree sectors,
        max 2 stations per sector, min 5 stations).
    drop_stations : list[str], optional
        Stations to exclude (repeatable), as STA, NET.STA or NET.STA.LOC.
    deviatoric : bool, optional
        Invert for a deviatoric moment tensor only (no isotropic component).
    profile : bool, optional
        Also write a cProfile dump of the inversion to results/profile.prof.

    Returns
    -------
    dict
        The ``run_auto_cmt`` return value; ``run["results"]`` holds the
        curated centroid/summary/station-fit tables.
    """
    start_time = time.time()

    event_row = load_event_row(event_id, event_csv_path)

    print("\nBuilding velocity model grid")
    nz_grid_ll = build_nz_velocity_grid(nz_3dvm_path)

    print("\nRunning CMT inversion")
    run = run_cmt_inversion(
        event_row,
        output_dir,
        nz_grid_ll,
        real_time=real_time,
        threads=threads,
        min_radius_km=min_radius_km,
        max_radius_km=max_radius_km,
        azimuth_control=azimuth_control,
        drop_stations=drop_stations,
        deviatoric=deviatoric,
        profile=profile,
    )

    print(f"Elapsed time: {time.time() - start_time:.2f} seconds")
    return run


if __name__ == "__main__":
    app()
