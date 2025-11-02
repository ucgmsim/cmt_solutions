# CMT Reviewer — User Guide

This guide explains how to install and run the Streamlit CMT reviewer app and how to review nodal planes.

## 1. Prerequisites

- Python 3.9+ (use the same Python environment when running Streamlit as when you install the package).
- A virtual environment is recommended.
- Install development requirements listed in `requirements.txt` (or adjust to your environment).

## 2. Run the app

Change into the `interfaces` directory and run Streamlit:

```bash
cd interfaces
streamlit run cmt_reviewer.py
```

Open the URL printed by Streamlit (typically `http://localhost:8501`)

The application window should appear in your web browser and look similar to the screenshot below after you have entered your username:
![CMT Reviewer Screenshot](./images/cmt_review_interface.png)

## 3. App walkthrough — left column (filters & settings)

1. Enter your username in the "User Settings" box — this will be recorded in the review results so we know who performed each review. (e.g. Joel or Jake).
2. Choose a magnitude (Mw) range using the slider. By default the lower bound is set to Mw = 5.0 to focus on larger events.
3. Toggle "Show reviewed CMT solutions" to include events that have already been reviewed (useful for re-checking).
4. Click "Apply filters" to apply the magnitude/feedback filters. Note: Will reset your current position to the first event in the filtered list.

## 4. App walkthrough — right column (review panel)

1. Use the dropdown at the top to jump to a particular event or use the `Previous`/`Next` buttons to step through the filtered list.
2. The map shows:
   - Two nodal planes: one in green and one in blue (these are the two possible fault planes for the seismic mechanism).
   - A yellow circle at the epicenter/hypocenter.
   - Red lines showing Community Fault Model traces; hover over a trace to see its name, dip ranges, dip direction and rake ranges.
3. The two panels on the right show the numeric strike/dip/rake for each nodal plane. Choose the plane you believe is the correct fault plane by clicking "Select Plane 1" or "Select Plane 2".
4. After selecting a plane:
   - The selected plane is written into `strike1`/`dip1`/`rake1` in the working table, and the other plane is written into `strike2`/`dip2`/`rake2`.
   - The row gets marked `reviewed = True` and `reviewer` is set to the username you entered.
   - The full working table is saved to the `CMT_solutions.csv` file.
   - The app automatically advances to the next event in the filtered list (unless you were already at the last event).
5. You can still navigate with the `Previous` and `Next` buttons at any time to re-check earlier events.
6. A progress bar at the bottom shows how far you are through the current filtered list.


## 5. After reviewing

When you've finished reviewing the events you wanted to check, the reviewed results are saved in the `CMT_solutions.csv` file in the `data` directory.

To contribute your reviewed results back into the repository:

1. Create a branch to hold your changes
2. Commit  the updated `CMT_solutions.csv` file
3. Push the branch to your new branch on GitHub
4. Go to GitHub
5. Open a pull request from your branch to the main branch and add a description describing the review (who, when, filters used).