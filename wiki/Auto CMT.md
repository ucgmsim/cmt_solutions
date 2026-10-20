# Auto CMT — 1-D CMT Inversion Guide

`auto_cmt/` runs [BayesISOLA](https://pypi.org/project/BayesISOLA/)'s automated 1-D centroid moment tensor (CMT) inversion for a single GeoNet event. It covers two situations with the same script:

- **Any event already in GeoNet's archive** — the default mode. Waveforms and station metadata are fetched straight from GeoNet's standard `GEONET` FDSN client.
- **A just-happened ("real-time") event** — pass `--real-time`. GeoNet's standard client is not updated in near real time, so this mode queries GeoNet's near-real-time service (`service-nrt.geonet.org.nz`) first, falling back to the standard client per station, before running the inversion against the downloaded files.

## 1. Prerequisites

- Python 3.10+ and the packages in `requirements.txt`, including `BayesISOLA==0.2.0`.
- An event CSV with a single row for the event, using the same columns as GeoNet's `earthquake_source_table.csv` (`evid`, `datetime`, `lat`, `lon`, `depth`, `mag`, and optionally `mag_type`).
- A 3-D NZ velocity model CSV, used to build the station/path-specific 1-D Axitra models. `auto_cmt/nz3dvm_2p3.csv` is bundled with the repository and used by default — pass `--nz-3dvm-path` to use a different copy.

## 2. Run the inversion for one event

From the repository root:

```bash
python auto_cmt/run_cmt.py <event_id> <event_csv_path> <output_dir>
```

For example:

```bash
python auto_cmt/run_cmt.py 2026p576643 earthquake_source_table.csv ./2026p576643/cmt_1d
```

For a just-happened event that may not have reached GeoNet's standard archive yet, add `--real-time`:

```bash
python auto_cmt/run_cmt.py 2026p576643 earthquake_source_table.csv ./2026p576643/cmt_1d --real-time
```

To use a velocity model other than the bundled `nz3dvm_2p3.csv`, pass `--nz-3dvm-path`:

```bash
python auto_cmt/run_cmt.py 2026p576643 earthquake_source_table.csv ./2026p576643/cmt_1d --nz-3dvm-path other_model.csv
```

To apply azimuthal station thinning (min 3 occupied 45-degree sectors, max 2 stations per sector, min 5 stations), drop specific stations, or invert for a deviatoric moment tensor:

```bash
python auto_cmt/run_cmt.py 2026p576643 earthquake_source_table.csv ./2026p576643/cmt_1d --azimuth-control
python auto_cmt/run_cmt.py 2026p576643 earthquake_source_table.csv ./2026p576643/cmt_1d --drop-stations NZ.TON8.10 --drop-stations HIZ --deviatoric
```

Run `python auto_cmt/run_cmt.py --help` for the full list of options (thread count, station search radius, etc.).

### Inversion settings

| Setting | Value |
|---|---|
| Frequency band | 0.02–0.06 Hz |
| Location / time uncertainty | 3.0 km / 3.0 s |
| Horizontal grid step | 1 km for M ≤ 5.0, otherwise 2 km |
| Depth search | min 3 km, 0.3–3.0 × catalogue depth, 1 km step |
| Adaptive grid | expansion/recentering on, no refinement |
| Station jackknife | on, min 4 stations |
| Uncertainty samples | 1000 |
| Threads | 12 |

## 2a. Use from Python

The same steps are importable, so a caller (e.g. NZGMDB) can run several inversions for one event without importing BayesISOLA itself, and build the velocity grid only once:

```python
from auto_cmt.run_cmt import build_nz_velocity_grid, load_event_row, run_cmt_inversion

event_row = load_event_row("2026p576643", Path("earthquake_source_table.csv"))
nz_grid = build_nz_velocity_grid()

run_cmt_inversion(event_row, Path("cmt_1d/all_stations"), nz_grid)
run_cmt_inversion(event_row, Path("cmt_1d/azimuth"), nz_grid, azimuth_control=True)
run_cmt_inversion(
    event_row, Path("cmt_1d/drop_dev"), nz_grid, drop_stations=["NZ.TON8.10"], deviatoric=True
)
```

Each call writes the full BayesISOLA output plus `cmt_solution.csv` into its output directory and returns the `run_auto_cmt` result dict (`run["results"]` holds the centroid, summary and station-fit tables).

### Outputs

`run_cmt.py` creates `<output_dir>` and writes:

- `raw/`, `metadata/` — downloaded miniSEED/StationXML and station metadata (only written in `--real-time` mode, or by BayesISOLA itself otherwise).
- `input/`, `results/`, `figures/` — BayesISOLA's inversion inputs, curated result tables, and diagnostic plots.
- `cmt_solution.csv` — a flat one-row summary matching the GeoNet regional CMT catalogue column layout (`PublicID`, `Date`, `Latitude`, `Longitude`, `strike1/dip1/rake1`, `strike2/dip2/rake2`, `ML`, `Mw`, `Mo`, `CD`).


## 3. Notes

- `run_auto_cmt` and `get_mseed_stationxml` are BayesISOLA functions; see the [BayesISOLA documentation](https://geo.mff.cuni.cz/~vackar/BayesISOLA/) for details on the inversion itself.
- The station search annulus, frequency band, and grid-search step size are tuned for New Zealand shallow-to-moderate crustal events. Pass `--min-radius-km`/`--max-radius-km` to override the default search radius if a run finds too few or too many stations.
