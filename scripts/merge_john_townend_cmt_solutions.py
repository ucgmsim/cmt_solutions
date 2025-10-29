"""
This script merges the John Townend CMT solutions into the main CMT Solutions.
"""

import io
from datetime import datetime

import pandas as pd
import requests
import typer

from cmt_solutions import cmt_data
from qcore import cli

app = typer.Typer(pretty_exceptions_enable=False)


def download_earthquake_data(
    start_date: datetime,
    end_date: datetime,
):
    """
    Download the earthquake data files from the geonet website
    and creates a dataframe with the data.

    Extracted into smaller requests to avoid the 20,000 event limit
    to stop their system crashing.

    Parameters
    ----------
    start_date : datetime
        The start date for the data extraction from the earthquake data
    end_date : datetime
        The end date for the data extraction from the earthquake data

    Returns
    -------
    pd.DataFrame
        The dataframe with the earthquake data from the geonet website
    """
    # Define bbox for New Zealand
    # config = cfg.Config()
    # bbox = ",".join([str(coord) for coord in config.get_value("bbox")])

    # Send API request for the date ranges required
    endpoint = (
        f"https://quakesearch.geonet.org.nz/count?startdate={start_date}&enddate={end_date}"
    )
    response = requests.get(endpoint)

    # Check if the response is valid
    if response.status_code != 200:
        raise ValueError("Could not get the earthquake data")

    # Get the response dates
    response_json = response.json()
    # Check that the response has the "dates" key
    if "dates" not in response_json:
        response_dates = [end_date, start_date]
    else:
        response_dates = response_json["dates"]

    # Loop over the dates to extract the csv data to a dataframe
    dfs = []
    for index, first_date in enumerate(response_dates[1:]):
        second_date = response_dates[index]
        endpoint = (
            f"https://quakesearch.geonet.org.nz/csv?startdate={first_date}&enddate={second_date}"
        )
        response = requests.get(endpoint)

        # Check if the response is valid
        if response.status_code != 200:
            raise ValueError("Could not get the earthquake data")

        # Read the response into a dataframe
        df = pd.read_csv(io.StringIO(response.text))

        dfs.append(df)

    # Concatenate the dataframes and sort by origintime
    geonet = (
        pd.concat(dfs, ignore_index=True)
        .sort_values("origintime")
        .reset_index(drop=True)
    )
    # Convert the origintime to datetime and remove the timezone
    geonet["origintime"] = pd.to_datetime(geonet["origintime"]).dt.tz_localize(None)

    return geonet


@cli.from_docstring(app)
def merge_john_townend_cmt_solutions(time_difference: int = 20, depth_difference: int = 0.1, lat_lon_difference: float = 1.0):
    """
    Merges the John Townend CMT solutions into the main CMT Solutions dataset.
    First we must get a matching event ID from GeoNet based on date, location and depth.

    Parameters
    ----------
    time_difference : int
        Maximum time difference in seconds to consider a match.
    depth_difference : int
        Maximum depth difference in km to consider a match.
    lat_lon_difference : float
        Maximum latitude/longitude difference in degrees to consider a match.
    """
    # Load the main CMT solutions dataset
    cmt_df = cmt_data.get_cmt_data()

    # Load the John Townend CMT solutions dataset
    john_townend_df = pd.read_csv(
        cmt_data.JOHN_TOWNEND_CMT_DATA_PATH,
    )

    # Help match the datetimes
    john_townend_df["date_dt"] = pd.to_datetime(john_townend_df["t.nll"], format="(%Y-%b-%d %H:%M:%S)")

    # Read the GeoNet earthquake data
    start_time = john_townend_df["date_dt"].min() - pd.Timedelta(days=1)
    end_time = john_townend_df["date_dt"].max() + pd.Timedelta(days=1)
    geonet_cmt_df = download_earthquake_data(start_time, end_time)

    john_townend_df["PublicID"] = None
    for jt_idx, john_townend_row in john_townend_df.iterrows():
        # Find matching GeoNet entry by datetime
        date = john_townend_row["date_dt"]
        # Calculate time differences in seconds
        time_diffs = abs((geonet_cmt_df["origintime"] - date).dt.total_seconds())
        # Sort geonet rows by time difference
        sorted_indices = time_diffs.argsort()
        for idx in sorted_indices:
            if time_diffs[idx] > time_difference:
                break
            geo_row = geonet_cmt_df.loc[idx]
            lat_diff = abs(geo_row["latitude"] - john_townend_row["lat.geo"])
            lon_diff = abs(geo_row["longitude"] - john_townend_row["lon.geo"])
            depth_diff = abs(geo_row["depth"] - john_townend_row["z.geo"])
            if lat_diff <= lat_lon_difference and lon_diff <= lat_lon_difference and depth_diff <= depth_difference:
                john_townend_df.at[jt_idx, "PublicID"] = geo_row["publicid"]
                break

    # remove any rows that did not get a match
    john_townend_df = john_townend_df[john_townend_df["PublicID"].notnull()]

    # Rename the columns in john_townend_df to match cmt_df
    # PublicID,Date,Latitude,Longitude,strike1,dip1,rake1,strike2,dip2,rake2,Mw,CD
    john_townend_df = john_townend_df.rename(columns={
        "mag": "Mw",
        "lat.nll": "Latitude",
        "lon.nll": "Longitude",
        "date_dt": "Date",
        "strike.nll": "strike1",
        "dip.nll": "dip1",
        "rake.nll": "rake1",
        "strike2.nll": "strike2",
        "dip2.nll": "dip2",
        "rake2.nll": "rake2",
        "z.nll": "CD",
    })

    # Select just these columns for merging
    john_townend_df = john_townend_df[[
        "PublicID", "Date", "Latitude", "Longitude",
        "strike1", "dip1", "rake1",
        "strike2", "dip2", "rake2",
        "Mw", "CD"
    ]]

    # Add columns to reference the source of the data
    john_townend_df["source"] = "John Townend"
    cmt_df["source"] = "GeoNet"

    # Adjust the Date format in john_townend_df to match cmt_df
    john_townend_df["Date"] = john_townend_df["Date"].dt.strftime("%Y%m%d%H%M%S")
    john_townend_df["reviewed"] = False

    # Merge the two datasets, avoiding duplicates based on 'PublicID'
    merged_df = pd.concat([cmt_df, john_townend_df]).drop_duplicates(subset=["PublicID"]).reset_index(drop=True)

    # Save the merged dataset
    merged_df.to_csv(cmt_data.CMT_DATA_PATH, index=False)

if __name__ == "__main__":
    app()
