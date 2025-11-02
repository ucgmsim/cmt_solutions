# The New Zealand Ground-motion Database (NZ GMDB): John Townend Relocation/CMT Study

The study done by Jown Townend et al., (2012) was performed on events between 2002 - 2011 which include relocations and recomputed focal mechanisms. In particular only one nodal plane solution was provided and thus the second is needed as both are equally probable solutions until otherwise informed by domain knowledge. Nodel plane solutions were obtained divided into two (2) categories as follows:

- NonLinLoc Hypocenter Relocations with Walsh et al., (2009) focal mechanism algorithm 
- NonLinLoc Hypocenter Relocations with Fpfit Algorithm (Reasenberg and Oppenheimer, 1985)

---

The Fpfit algorithm (Reasenberg & Oppenheimer, 1985) is a method for estimating focal mechanism parameters by minimizing the misfit between observed P-wave polarities and predicted polarities from a trial mechanism. The method operates under the assumption of a double-couple source and uses an iterative fitting approach.

Key points:

- The algorithm takes as input a set of P-wave first motions (polarity: positive or negative) recorded at multiple stations. 
- For a candidate focal mechanism (strike, dip, rake), it predicts whether each station should see a positive or negative first motion, based on take-off angles and ray paths.
- It defines a misfit function, typically the number (or weight) of mismatches (i.e. observed polarity vs predicted polarity), possibly incorporating weights or angular uncertainty of each observation.
- The algorithm iteratively searches (often via a grid search or downhill search) over the space of (strike, dip, rake) to find the mechanism that minimizes the misfit.

Let the observed polarity at station i be 𝑜𝑖∈{+1,−1}
, and the predicted polarity from mechanism parameters (𝜑,𝜹,𝜆) be 𝑝𝑖(𝜑,𝜹,𝜆)∈{+1,−1}. Then the misfit to minimize is

𝑀(𝜑,𝜹,𝜆)=∑𝑖𝑤𝑖1[𝑜𝑖≠𝑝𝑖(𝜑,𝜹,𝜆)]

or alternatively a weighted sum of angular deviations if uncertainties in take-off angle are considered. Here 𝑤𝑖 are weights (often unity or based on data quality).

Once the best solution (𝜑∗,𝜹∗,𝜆∗) is found, the algorithm can also estimate uncertainties by exploring nearby parameter space and mapping misfit increases.

---

Reasenberg & Oppenheimer (1985) provide additional refinements, including:

- Handling ambiguity in nodal planes: since polarity data only constrain which plane is active indirectly, the solution includes both nodal-plane orientations.
- Implementing local search refinements around promising grid solutions.
- Applying quality controls and weighting to stations to avoid bias from poorly constrained observations.

You can express the relation between the misfit function and confidence regions by e.g. defining:

Δ𝑀=𝑀(𝜑,𝜹,𝜆)−𝑀min

and then associating contours of Δ𝑀=const with confidence levels under an approximate binomial or chi-square interpretation.

The Walsh et al. (2009) method of estimating focal-mechanism parameters uses the output from NonLinLoc and treats each hypocenter probabilistically. This means that the take-off angle and azimuth of a P-wave recorded at a particular seismograph, and the ultimate focal-mechanism parameters of interest, are also estimated probabilistically. This approach to estimating focal mechanisms has two particular advantages in the present study:

- It enables us to take account of real observational uncertainties in each earthquake’s hypocenter.
- It enables us to compute robust estimates of the a posteriori uncertainties in each focal mechanism—either in terms of a three-dimensional PDF describing strike, dip, and rake, or via more complex (symmetrized matrix-Fisher) descriptions of the matrix

𝑅(𝑌)=[𝑏̂ 𝑢𝑏̂ 𝑎𝑏̂ 𝑛]

formed by the slip vector 𝑏̂ 𝑢
, the null vector 𝑏̂ 𝑎, and the normal vector 𝑏̂ 𝑛 (see Walsh et al., 2009 for full details). These focal-mechanism uncertainties propagate into the stress-parameter estimation and hence constitute an important source of error in mapping tectonic stress.

---

## Second Nodal Plane Computation

The repository provides a ready-made implementation in cmt_solutions/nodal_plane.py. Use the function conjugate_nodal_plane(strike, dip, rake) to compute the auxiliary (conjugate) nodal plane for a single mechanism, or add_conjugate_nodal_planes(df, strike_col='strike1', dip_col='dip1', rake_col='rake1') to add the conjugate plane columns to a pandas.DataFrame.

### Notes:
- Inputs and outputs are in degrees.
- Returned angles are normalised (strike in [0,360], rake in [-180,180]).

### Example usage is shown below.
Brief explanation of the code: the snippet shows (1) how to import the functions from cmt_solutions/nodal_plane.py, (2) how to compute the conjugate plane for a single row, and (3) how to add conjugate plane columns to an existing DataFrame in batch.

```text
from cmt_solutions.nodal_plane import conjugate_nodal_plane, add_conjugate_nodal_planes
# Example 1: single mechanism
s1, d1, r1 = 120.0, 30.0, -90.0
s2, d2, r2 = conjugate_nodal_plane(s1, d1, r1)
# s2, d2, r2 now contain the conjugate plane angles (degrees)

# Example 2: batch on a DataFrame
# (read your CSV into a DataFrame using your preferred method; e.g. pandas.read_csv)
# df = <read CSV into DataFrame>  # expects columns like `strike1`, `dip1`, `rake1`
# then call the helper to add conjugate planes:
# df = add_conjugate_nodal_planes(df, strike_col="strike1", dip_col="dip1", rake_col="rake1")
# df now contains `strike2`, `dip2`, `rake2` columns with the conjugate plane values
```

---

## Pairing with NZ GMDB events

One of the challenges in using this dataset is to correctly pair the focal mechanism solutions with the events in the NZ GMDB. The study does not provide the event IDs used in the NZ GMDB, so matching must be done based on event metadata such as origin time, latitude, longitude, and depth.

To achieve this the following algorithm is used in the repository (implemented in `scripts/merge_john_townend_cmt_solutions.py`):

1. Read the John Townend CMT table (expects the original Townend columns such as `t.nll`, `lat.geo`, `lon.geo`, `z.geo`, `strike.nll`, etc.). The Townend date/time string (`t.nll`) is parsed with the format `("%Y-%b-%d %H:%M:%S")` into a pandas.Timestamp.
2. Download GeoNet event CSVs covering the Townend date range (the script requests data from GeoNet from `min(date) - 1 day` to `max(date) + 1 day`) and concatenates the responses to produce a GeoNet event table with `origintime`, `latitude`, `longitude`, `depth`, and `publicid`.
3. For each Townend solution row, compute absolute time differences (in seconds) between the Townend parsed date and the GeoNet `origintime`. Sort GeoNet rows by increasing time difference and scan them until the time difference exceeds the allowed threshold.
4. For each candidate GeoNet row within the time threshold, compute absolute latitude, longitude and depth differences with the Townend row. If all three differences are within the allowed thresholds, select that GeoNet `publicid` as the match for the Townend row and stop searching for that row.
5. Rows that do not find any GeoNet match are dropped (the script only keeps Townend rows where a `PublicID` was assigned).
6. The Townend table columns are renamed to match the project's CMT table (for example `strike.nll` → `strike1`, `dip.nll` → `dip1`, `rake.nll` → `rake1`, etc.), the Townend `Date` column is formatted as `%Y%m%d%H%M%S`, and `reviewed` is set to `False`.
7. The script concatenates the existing CMT solutions (`cmt_solutions.data/CMT_solutions.csv`) and the Townend table, then deduplicates by `PublicID` (keeping the first occurrence) and writes the resulting merged table back to the canonical CMT data path.

Default matching thresholds (script defaults):

- `time_difference`: 20  (seconds)
- `depth_difference`: 0.1  (km)
- `lat_lon_difference`: 1.0  (degrees)
