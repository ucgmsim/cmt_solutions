"""
Run the 1-D CMT inversion (BayesISOLA) for a single GeoNet event.
"""

import time
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from BayesISOLA.gf_helpers import build_regular_velocity_grid
from BayesISOLA.workflows import run_auto_cmt
from obspy.clients.fdsn import Client as FDSNClient

from qcore import cli

app = typer.Typer(pretty_exceptions_enable=False)

# GeoNet's near-real-time FDSN service. The standard "GEONET" client is not
# updated in near real time, so a just-happened event is not there yet -
# --real-time queries this service instead
NRT_BASE_URL = "https://service-nrt.geonet.org.nz"

# 3-D NZ velocity model bundled with this package, used by default to build
# station/path-specific 1-D Axitra models.
DEFAULT_NZ_3DVM_PATH = Path(__file__).resolve().parent / "nz3dvm_2p3.csv"


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
    threads: Annotated[int, typer.Option()] = 8,
    min_radius_km: Annotated[float, typer.Option()] = 0.0,
    max_radius_km: Annotated[float | None, typer.Option()] = None,
    deviatoric: Annotated[bool, typer.Option(is_flag=True)] = False,
) -> dict:
    """
    Run the 1-D CMT inversion for one GeoNet event.

    By default this queries GeoNet's standard "GEONET" FDSN client
    (``run_auto_cmt(client="GEONET")``), which works for any event already
    in GeoNet's archive.

    Pass ``--real-time`` for a just-happened event that has not propagated
    to the standard archive yet. This swaps in a client pointed at GeoNet's
    near-real-time service (``service-nrt.geonet.org.nz``) instead, since
    that service only holds a short rolling buffer of recent data.

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
    deviatoric : bool, optional
        Invert for a deviatoric moment tensor only (no isotropic component).

    Returns
    -------
    dict
        The ``run_auto_cmt`` return value; ``run["results"]`` holds the
        curated centroid/summary/station-fit tables.
    """
    start_time = time.time()

    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "input"
    input_path.mkdir(parents=True, exist_ok=True)

    event_df = pd.read_csv(event_csv_path)
    assert(event_id == str(event_df["evid"].values[0])), f"event_id={event_id!r} does not match evid={event_df['evid'].values[0]!r} in {event_csv_path}"

    # Build the velocity model grid from the 3-D NZ velocity model CSV.
    print("\nBuilding velocity model grid")
    nz_grid_ll = build_regular_velocity_grid(
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

    print("\nRunning CMT inversion")
    mag_event = event_df["mag"].values[0]
    step_x_km = 1.0 if mag_event < 6.0 else 2.0
    client = FDSNClient(base_url=NRT_BASE_URL) if real_time else "GEONET"

    run = run_auto_cmt(
        event_id,
        event_df["datetime"].values[0],
        event_df["lon"].values[0],
        event_df["lat"].values[0],
        event_df["depth"].values[0],
        mag_event,
        output_dir=output_dir,
        velocity_model=nz_grid_ll,
        client=client,
        min_radius_km=min_radius_km,
        max_radius_km=max_radius_km,
        location_unc_km=1.0,
        time_unc_s=3.0,
        min_depth_km=3.0,
        min_depth_multiplier=0.3,
        step_x_km=step_x_km,
        adaptive_grid_search={
            "adaptive_grid": True,
            "adaptive_refine_factor": 0,
        },
        threads=threads,
        crosscovariance=True,
        n_uncertainty=1000,
        deviatoric=deviatoric,
        plot=True,
        plot_preset="summary",
        show=False,
        html_output=True,
        write_report=True,
    )

    print(f"Elapsed time: {time.time() - start_time:.2f} seconds")

    # Write a flat cmt_solution.csv summary, matching the GeoNet regional
    # CMT catalogue column layout: PublicID, Date, Latitude, Longitude,
    # strike1, dip1, rake1, strike2, dip2, rake2, ML, Mw, Mo, CD.

    results = run["results"]
    centroid_row = results["centroid"].iloc[0]
    summary_row = results["summary"].iloc[0]

    # ML is GeoNet's own catalogue magnitude, carried over only when the
    # event was actually reported with local magnitude - BayesISOLA itself
    # only produces Mw (moment magnitude), never ML.
    mag_type = str(event_df["mag_type"].values[0]) if "mag_type" in event_df.columns else ""
    ml_value = round(float(mag_event), 1) if mag_type.strip().upper() == "ML" else None

    cmt_solution_df = pd.DataFrame([{
        "PublicID": event_id,
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
    }])

    cmt_solution_path = output_dir / "cmt_solution.csv"
    cmt_solution_df.to_csv(cmt_solution_path, index=False)
    print(f"\nWrote CMT solution summary to {cmt_solution_path}")

    return run


if __name__ == "__main__":
    app()
