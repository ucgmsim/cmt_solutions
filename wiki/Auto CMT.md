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

Run `python auto_cmt/run_cmt.py --help` for the full list of options (thread count, station search radius, etc.).

### Outputs

`run_cmt.py` creates `<output_dir>` and writes:

- `raw/`, `metadata/` — downloaded miniSEED/StationXML and station metadata (only written in `--real-time` mode, or by BayesISOLA itself otherwise).
- `input/`, `results/`, `figures/` — BayesISOLA's inversion inputs, curated result tables, and diagnostic plots.
- `cmt_solution.csv` — a flat one-row summary matching the GeoNet regional CMT catalogue column layout (`PublicID`, `Date`, `Latitude`, `Longitude`, `strike1/dip1/rake1`, `strike2/dip2/rake2`, `ML`, `Mw`, `Mo`, `CD`).


## 3. Notes

- `run_auto_cmt` and `get_mseed_stationxml` are BayesISOLA functions; see the [BayesISOLA documentation](https://geo.mff.cuni.cz/~vackar/BayesISOLA/) for details on the inversion itself.
- The station search annulus, frequency band, and grid-search step size are tuned for New Zealand shallow-to-moderate crustal events. Pass `--min-radius-km`/`--max-radius-km` to override the default search radius if a run finds too few or too many stations.
