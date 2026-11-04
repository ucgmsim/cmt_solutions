# Auto CMT — 1-D CMT Inversion Guide

`auto_cmt/` runs [BayesISOLA](https://pypi.org/project/BayesISOLA/)'s automated 1-D centroid moment tensor (CMT) inversion for a single GeoNet event. It covers two situations with the same script:

- **Any event already in GeoNet's archive** — the default mode. Waveforms and station metadata are fetched straight from GeoNet's standard `GEONET` FDSN client.
- **A just-happened ("real-time") event** — pass `--real-time`. GeoNet's standard client is not updated in near real time, so this mode queries GeoNet's near-real-time service (`service-nrt.geonet.org.nz`) first, falling back to the standard client per station, before running the inversion against the downloaded files.

## 1. Prerequisites

- Python 3.10+ and the packages in `requirements.txt`, including `BayesISOLA==0.3.0` (0.3.0 is the release with the speed-ups below; older versions still run `run_cmt.py`, but `run_event.py` needs 0.3.0).
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
| Processes (`--threads`) | 16 |

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


## 2b. All three production runs for one event (`run_event.py`)

The NZGMDB pipeline makes three runs per event: `all_stations`, `azimuth` (azimuthal thinning) and `drop_outliers_dev` (deviatoric, without stations that are VR outliers in both earlier runs). `run_event.py` runs them with the same outlier rule (robust z-score < -5 and VR < -1 in both runs, at least 5 stations kept):

```bash
python -m auto_cmt.run_event 2026p576643 earthquake_source_table.csv ./2026p576643/cmt_1d --real-time
```

It runs them **one after another, not in parallel**. `drop_outliers_dev` needs the first two runs anyway, and each run is fast enough to use the whole machine (`--threads`, default 16). Running two at once on the same cores only made both slower.

- **Shared work (`--share-work`, default on).** Waveforms are downloaded once by `all_stations` and reused by the later runs. All runs share one Green's function store (`gf_store/`), so a receiver with identical inputs (crust model, Axitra parameters, depth, offset) is computed only once. This does not change any result.
- **Figures in the background (`--background-figures`, default on).** Each run is its own process. As soon as it writes `cmt_solution.csv` the next run starts, while its figures and HTML report are drawn in the background. The event finishes when all figures are done.
- **`--shared-xl` (off by default).** The azimuth subset usually has a closer farthest station, which gives Axitra a different `xl` and stops it reusing the all_stations Green's functions. This flag gives the subset runs the all_stations `xl`, so they reuse everything (about 1 min faster). It moved the azimuth solution by 0.11° (Kagan angle) on the test event.

Each run writes to `<output_dir>/<run>/`. The event folder also gets `station_vr.csv` (outlier decision), `event_timings.csv` (seconds until each run's solution and until the event finished) and `gf_store/` (about 1 GB per event, safe to delete afterwards).

From Python:

```python
from auto_cmt.run_event import run_cmt_event

timings = run_cmt_event("2026p576643", Path("earthquake_source_table.csv"), Path("cmt_1d"), real_time=True)
```

**Performance** (ML 4.1 event 2026p758320, 8 cores):
- The original three-run pipeline on BayesISOLA 0.2.2 took 128.9 min.
- With BayesISOLA 0.3.0 and `run_event.py`, all three solutions are written after 7.9 min, and the event (including figures) finishes after 10.3 min.
- The solutions are bit-identical to running the three variants separately with 0.3.0, and within float32 rounding of 0.2.2 (moment tensor < 5e-8 relative).

## 2c. Timing and profiling

Every `run_cmt_inversion` call writes `results/timings.csv`, even if the inversion fails. It has one row per BayesISOLA stage, with `calls`, `inclusive_s`, `exclusive_s` (inclusive minus nested stages) and `percent` of the total. It also has an `other` row for untimed code and a `total` row.

The stages are timed by temporarily wrapping BayesISOLA functions (`auto_cmt/timing.py`, `BAYESISOLA_STAGES`), so BayesISOLA itself is not modified. The stages are download, station selection, waveform loading, mouse detection, station velocity models, data processing, filtering, Green's functions, time-shifted data, adaptive grid reruns, covariance, MT inversion, jackknife, results/uncertainty, writing tables, plots and the HTML report. If a BayesISOLA upgrade renames one of these functions, that stage is skipped with a warning and the run continues.

Pass `--profile` (or `profile=True`) to also write a cProfile dump to `results/profile.prof`, which you can view with `snakeviz results/profile.prof`.

## 3. Notes

- `run_auto_cmt` and `get_mseed_stationxml` are BayesISOLA functions; see the [BayesISOLA documentation](https://geo.mff.cuni.cz/~vackar/BayesISOLA/) for details on the inversion itself.
- The station search annulus, frequency band, and grid-search step size are tuned for New Zealand shallow-to-moderate crustal events. Pass `--min-radius-km`/`--max-radius-km` to override the default search radius if a run finds too few or too many stations.
