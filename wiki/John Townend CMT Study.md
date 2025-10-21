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
, and the predicted polarity from mechanism parameters (𝜑,𝛿,𝜆) be 𝑝𝑖(𝜑,𝛿,𝜆)∈{+1,−1}. Then the misfit to minimize is

𝑀(𝜑,𝛿,𝜆)=∑𝑖𝑤𝑖1[𝑜𝑖≠𝑝𝑖(𝜑,𝛿,𝜆)]

or alternatively a weighted sum of angular deviations if uncertainties in take-off angle are considered. Here 𝑤𝑖 are weights (often unity or based on data quality).

Once the best solution (𝜑∗,𝛿∗,𝜆∗) is found, the algorithm can also estimate uncertainties by exploring nearby parameter space and mapping misfit increases.

---

Reasenberg & Oppenheimer (1985) provide additional refinements, including:

- Handling ambiguity in nodal planes: since polarity data only constrain which plane is active indirectly, the solution includes both nodal-plane orientations.
- Implementing local search refinements around promising grid solutions.
- Applying quality controls and weighting to stations to avoid bias from poorly constrained observations.

You can express the relation between the misfit function and confidence regions by e.g. defining:

Δ𝑀=𝑀(𝜑,𝛿,𝜆)−𝑀min

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

```python
from cmt_solutions.nodal_plane import conjugate_nodal_plane, add_conjugate_nodal_planes
import pandas as pd

# Example 1: single mechanism
s1, d1, r1 = 120.0, 30.0, -90.0
s2, d2, r2 = conjugate_nodal_plane(s1, d1, r1)
# s2, d2, r2 now contain the conjugate plane angles (degrees)

# Example 2: batch on a DataFrame
df = pd.read_csv("path/to/your/mechanisms.csv")  # expects columns like `strike1`, `dip1`, `rake1`
df = add_conjugate_nodal_planes(df, strike_col="strike1", dip_col="dip1", rake_col="rake1")
# df now contains `strike2`, `dip2`, `rake2` columns with the conjugate plane values
```

---

## Pairing with NZ GMDB events

One of the challenges in using this dataset is to correctly pair the focal mechanism solutions with the events in the NZ GMDB. The study does not provide the event IDs used in the NZ GMDB, so matching must be done based on event metadata such as origin time, latitude, longitude, and depth.

To achieve this the following algorithm is used:

1. For each event in the NZ GMDB, obtain the origin time, latitude, longitude, and depth from the earthquake source table.
2. For each focal mechanism solution from the Townend et al. (2012) study, extract the same metadata.
