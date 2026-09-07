"""
Run the 1-D CMT inversion (BayesISOLA) for a single GeoNet event.
"""

import time
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from BayesISOLA.gf_helpers import build_regular_velocity_grid
from BayesISOLA.workflows import get_mseed_stationxml, run_auto_cmt
from obspy.clients.fdsn import Client as FDSNClient

from qcore import cli

app = typer.Typer(pretty_exceptions_enable=False)

# GeoNet's near-real-time FDSN service. The standard "GEONET" client is not
# updated in near real time, so a just-happened event is not there yet -
# --real-time queries this service first, falling back to "GEONET" per
# station (e.g. once an event ages out of its short rolling buffer).
NRT_BASE_URL = "https://service-nrt.geonet.org.nz"

CHANNELS = ("HH?", "BH?", "LH?")
CHANNEL_PRIORITY = ("HH", "BH", "LH")
TIME_UNC_S = 3.0
MIN_DEPTH_KM = 3.0
MIN_DEPTH_MULTIPLIER = 0.3
MAX_DEPTH_MULTIPLIER = 3.0
RUPTURE_VELOCITY_M_S = 1000.0
VELOCITY_SLOWEST_M_S = 1000.0
DEFAULT_THREADS = 8

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
    threads: Annotated[int, typer.Option()] = DEFAULT_THREADS,
    min_radius_km: Annotated[float, typer.Option()] = 0.0,
    max_radius_km: Annotated[float | None, typer.Option()] = None,
) -> dict:
    """
    Run the 1-D CMT inversion for one GeoNet event.

    By default this queries GeoNet's standard "GEONET" FDSN client directly
    (``run_auto_cmt(waveform_source="fdsn", client="GEONET")``), which works
    for any event already in GeoNet's archive.

    Pass ``--real-time`` for a just-happened event that has not propagated to
    the standard archive yet. In that mode the acquisition step is done
    manually first:

    1. Build an obspy FDSN client pointed at GeoNet's near-real-time service
       (``service-nrt.geonet.org.nz``), tried before the standard "GEONET"
       client so a just-happened event is picked up before it reaches the
       standard archive.
    2. Call ``BayesISOLA.workflows.get_mseed_stationxml()`` directly with
       that client list. This is the exact same station-discovery/download
       routine that ``run_auto_cmt(waveform_source="fdsn")`` calls
       internally - calling it here lets us hand it the near-real-time
       client first. ``get_mseed_stationxml`` discovers candidates from
       every client in the list and, if a station's download fails under an
       earlier client (e.g. too old for the near-real-time service's short
       rolling buffer), retries it under the next one automatically. It
       downloads miniSEED + StationXML under ``<output_dir>/raw`` and writes
       station metadata under ``<output_dir>/metadata``, returning a station
       table with local file paths.
    3. Pass that station table into
       ``run_auto_cmt(waveform_source="local", station_df=...)``, which
       skips acquisition entirely and inverts the files already on disk.

    Parameters
    ----------
    event_id : str
        GeoNet event/public ID, e.g. "2026p576643".
    event_csv_path : Path
        CSV with the event row (evid, datetime, lat, lon, depth, mag, ...) -
        same schema as GeoNet's earthquake_source_table.csv.
    output_dir : Path
        Directory raw/, metadata/, input/, results/, figures/ get written
        under.
    real_time : bool, optional
        Use GeoNet's near-real-time FDSN service (falling back to the
        standard client) instead of querying the standard "GEONET" client
        directly. Use this for an event that has only just happened.
    nz_3dvm_path : Path, optional
        3-D NZ velocity model CSV, used to build the station/path-specific
        1-D Axitra models. Defaults to the copy bundled with this package
        (``nz3dvm_2p3.csv``); pass a different path to use another model.
    threads : int, optional
        Axitra thread count.
    min_radius_km : float, optional
        Inner radius (km) of the station search annulus.
    max_radius_km : float, optional
        Outer radius (km) of the station search annulus. Omit to resolve it
        automatically from the event magnitude.

    Returns
    -------
    dict
        The ``run_auto_cmt`` return value; ``run["results"]`` holds the
        curated centroid/summary/station-fit tables.
    """
    start_time = time.time()

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw"
    metadata_path = output_dir / "metadata"
    input_path = output_dir / "input"
    input_path.mkdir(parents=True, exist_ok=True)

    print("Event directory :", output_dir)
    print("Raw data        :", raw_path)
    print("Metadata        :", metadata_path)
    print("BayesISOLA input:", input_path)

    # -----------------------------------------------------------------
    # Event parameters
    # -----------------------------------------------------------------

    event_df = pd.read_csv(event_csv_path)

    if "evid" in event_df.columns and str(event_df["evid"].values[0]) != event_id:
        print(f"WARNING: event_id={event_id!r} does not match evid="
              f"{event_df['evid'].values[0]!r} in {event_csv_path}")

    event_time = event_df["datetime"].values[0]
    lon_event = event_df["lon"].values[0]
    lat_event = event_df["lat"].values[0]
    depth_km = event_df["depth"].values[0]
    mag_event = event_df["mag"].values[0]

    print(f"Event {event_id}: t={event_time}  lon={lon_event}  lat={lat_event}  "
          f"depth={depth_km} km  mag={mag_event}")

    # -----------------------------------------------------------------
    # Velocity model
    # -----------------------------------------------------------------

    nz_3dvm = pd.read_csv(nz_3dvm_path)

    nz_grid_ll = build_regular_velocity_grid(
        nz_3dvm,
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

    # -----------------------------------------------------------------
    # Waveform acquisition. --real-time discovers stations and downloads
    # waveforms/StationXML manually against the near-real-time client
    # (falling back to GEONET), then hands the resulting station table
    # straight to run_auto_cmt(waveform_source="local", ...). Otherwise
    # run_auto_cmt is left to do the acquisition itself against the
    # standard GEONET client - this is the path for any event already in
    # GeoNet's archive.
    # -----------------------------------------------------------------

    if real_time:
        client = [FDSNClient(base_url=NRT_BASE_URL), "GEONET"]

        print("\nDownloading waveforms + StationXML (NRT client, falling back to GEONET)...")

        _, station_df, download_log, _ = get_mseed_stationxml(
            event_id, event_time, lon_event, lat_event, depth_km,
            magnitude=mag_event,
            output_dir=output_dir,
            client=client,
            min_radius_km=min_radius_km,
            max_radius_km=max_radius_km,
            ground_level=True,
            channels=CHANNELS,
            channel_priority=CHANNEL_PRIORITY,
            time_unc_s=TIME_UNC_S,
            min_depth_km=MIN_DEPTH_KM,
            min_depth_multiplier=MIN_DEPTH_MULTIPLIER,
            max_depth_multiplier=MAX_DEPTH_MULTIPLIER,
            rupture_velocity_m_s=RUPTURE_VELOCITY_M_S,
            velocity_slowest_m_s=VELOCITY_SLOWEST_M_S,
            covariance="noise",
            overwrite=False,
            plot=True,
            show=False,
        )

        print(f"Downloaded {len(station_df)} station(s):")
        print(station_df[["station_id", "distance_km", "download_status"]].to_string(index=False))

        if not download_log.empty:
            failed = download_log[download_log["status"].isin(["download_failed", "client_failed"])]
            if not failed.empty:
                print(f"\n{len(failed)} station(s) failed to download - see "
                      f"{metadata_path / 'download_log.csv'} for details.")

        waveform_kwargs = {"waveform_source": "local", "station_df": station_df}
    else:
        waveform_kwargs = {"waveform_source": "fdsn", "client": "GEONET"}

    # -----------------------------------------------------------------
    # Run the inversion.
    # -----------------------------------------------------------------

    print("\nRunning CMT inversion...")
    step_x_km = 1.0 if mag_event < 6.0 else 2.0

    run = run_auto_cmt(
        event_id, event_time, lon_event, lat_event, depth_km, mag_event,
        output_dir=output_dir,
        velocity_model=nz_grid_ll,
        gf_source="axitra",
        **waveform_kwargs,
        min_radius_km=min_radius_km,
        max_radius_km=max_radius_km,
        ground_level=True,
        channels=CHANNELS,
        channel_priority=CHANNEL_PRIORITY,
        location_unc_km=1.0,
        time_unc_s=TIME_UNC_S,
        min_depth_km=MIN_DEPTH_KM,
        min_depth_multiplier=MIN_DEPTH_MULTIPLIER,
        max_depth_multiplier=MAX_DEPTH_MULTIPLIER,
        step_x_km=step_x_km,
        step_z_km=1.0,
        max_grid_points=5000,
        add_rupture_length=True,
        rupture_velocity_m_s=RUPTURE_VELOCITY_M_S,
        velocity_slowest_m_s=VELOCITY_SLOWEST_M_S,
        adaptive_grid_search={
            "adaptive_grid": True,
            "adaptive_refine_factor": 0,
        },
        freqmin=0.02,
        freqmax=0.05,
        threads=threads,
        use_precalculated_Green="auto",
        covariance="noise",
        crosscovariance=True,
        n_uncertainty=None,
        plot=True,
        plot_preset="summary",
        show=False,
        write_report=True,
    )

    print("Complete")
    print(f"Elapsed time: {time.time() - start_time:.2f} seconds")

    results = run["results"]
    print("\nCentroid:")
    print(results["centroid"])
    print("\nSummary:")
    print(results["summary"])

    # -----------------------------------------------------------------
    # Write a flat cmt_solution.csv summary, matching the GeoNet regional
    # CMT catalogue column layout: PublicID, Date, Latitude, Longitude,
    # strike1, dip1, rake1, strike2, dip2, rake2, ML, Mw, Mo, CD.
    # -----------------------------------------------------------------

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
