"""
Updates the CMT solutions dataset with the most recent data from GeoNet.
"""
import pandas as pd
import typer

from cmt_solutions.cmt_data import CMT_DATA_PATH
from qcore import cli

app = typer.Typer(pretty_exceptions_enable=False)

CMT_URL = "https://raw.githubusercontent.com/GeoNet/data/main/moment-tensor/GeoNet_CMT_solutions.csv"

@cli.from_docstring(app)
def update_cmt():
    """
    Update the CMT solutions dataset with the most recent data from GeoNet.
    """
    # Read the latest GeoNet CMT solutions
    geonet_cmt_df = pd.read_csv(CMT_URL, dtype={"PublicID": str})

    # Add the review columns to the GeoNet data with default values
    geonet_cmt_df["reviewed"] = False
    geonet_cmt_df["reviewer"] = ""
    geonet_cmt_df["source"] = "GeoNet"

    # Read the current CMT data
    current_cmt_df = pd.read_csv(CMT_DATA_PATH, dtype={"PublicID": str})

    # Remove duplicates based on 'PublicID', keeping the latest entry from GeoNet
    updated_cmt_df = pd.concat([current_cmt_df, geonet_cmt_df]).drop_duplicates(subset=["PublicID"], keep="first")

    # Save the updated DataFrame back to the CSV file
    updated_cmt_df.to_csv(CMT_DATA_PATH, index=False)


if __name__ == "__main__":
    app()
