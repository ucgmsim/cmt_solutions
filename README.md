# CMT Solutions

This repository contains the Centroid Moment Tensor (CMT) solutions and supporting tools used for the John Townend relocation / CMT study.

Contents
- `cmt_solutions/` — Python package with helpers for reading and working with CMT solution data (includes `cmt_data.py`, `nodal_plane.py`, etc.).
- `data/` — CSV datasets (e.g. `CMT_solutions.csv`) used by the code and reviewer app.
- `interfaces/` — Streamlit UI for reviewing nodal planes (`cmt_reviewer.py`).
- `scripts/` — utility scripts used to build or update datasets.
- `wiki/` — documentation pages including the CMT review guide and the John Townend study notes.

Quick links (wiki)
- CMT Review guide: `wiki/CMT Review.md`
- John Townend CMT study notes: `wiki/John Townend CMT Study.md`
- Home (scripts summary): open `wiki/Home.md` for descriptions of the scripts in `scripts/`.

---

## Install

We recommend using a new Python virtual environment. From the repository root (the directory containing `pyproject.toml` / `setup.py`) install editable mode so the package is importable during development and by the Streamlit app:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r requirements.txt
```

---

### Running the Streamlit reviewer

From the repo root:

```bash
cd interfaces
streamlit run cmt_reviewer.py
```

Open the URL printed by Streamlit (usually `http://localhost:8501`). The `wiki/CMT Review.md` file contains a user guide for the reviewer UI and describes the steps to perform and save reviews.

---

### Using the Python API

This repository exposes a small API for loading and working with the CMT data. The main helper for loading the data is `get_cmt_data()` in `cmt_solutions/cmt_data.py`.

Example: load all CMT solutions

```python
from cmt_solutions.cmt_data import get_cmt_data

df_all = get_cmt_data()  # returns a pandas.DataFrame with the full contents of data/CMT_solutions.csv
print(len(df_all), "rows loaded")
```

Example: load a single event by `PublicID`

```python
from cmt_solutions.cmt_data import get_cmt_data

df_event = get_cmt_data(event_id="2016p858000")
```

### Reviewed-plane convention

When reviewing a CMT solution using the Streamlit app, the selected (preferred) plane is stored in the first plane columns and the other (alternative) plane in the second plane columns. Concretely:

- Preferred (chosen) plane -> `strike1`, `dip1`, `rake1`
- Other (non-preferred) plane -> `strike2`, `dip2`, `rake2`
- The `PreferredPlane` column is set to the chosen value (`"1"` or `"2"`), and the reviewer name and `reviewed` flag are recorded.

This means consumers of `CMT_solutions.csv` can always treat the first plane as the preferred plane when `reviewed == True`.

Working with reviewed results

The Streamlit reviewer writes the full working table (including `reviewed`, `reviewer`) to the output CSV you specify in the UI. You can use this file directly or replace `data/CMT_solutions.csv` with your reviewed file to share results.

To contribute reviewed results back to the repository follow the steps in the `wiki/CMT Review.md` guide.
