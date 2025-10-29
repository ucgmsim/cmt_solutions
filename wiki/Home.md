# CMT Solutions — Home

This repository stores centroid moment tensors (CMT) solutions and tools to review, merge, and update the canonical dataset.

What you can do here

- Review and edit CMT solutions using the Streamlit reviewer app. See the user guide: [CMT Reviewer — User Guide](CMT%20Review.md).

  Example (from the repository root):
  ```bash
  cd interfaces
  streamlit run cmt_reviewer.py
  ```

- Merge the John Townend CMT study into the canonical table. See the details: [John Townend CMT Study](John%20Townend%20CMT%20Study.md) and the merge script: `scripts/merge_john_townend_cmt_solutions.py`.

  Default matching thresholds used by the merge script:
  - time_difference = 20 seconds
  - depth_difference = 0.1 km
  - lat_lon_difference = 1.0 degree

  Quick check / run:
  ```bash
  python scripts/merge_john_townend_cmt_solutions.py --help
  python scripts/merge_john_townend_cmt_solutions.py data/john_townend_np2.csv
  ```

- Update the canonical CMT solutions from GeoNet (writes `data/CMT_solutions.csv`):

  ```bash
  python scripts/update_cmt_solutions.py
  ```
