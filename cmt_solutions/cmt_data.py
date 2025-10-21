from pathlib import Path

import pandas as pd

CMT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "CMT_solutions.csv"
JOHN_TOWNEND_CMT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "John_Townend_CMT_solutions.csv"


def get_cmt_data(event_id: str = None) -> pd.DataFrame:
    """
    Load the CMT solutions dataset from the local CSV file.

    Parameters
    ----------
        event_id : str, optional
            If provided, filter the DataFrame to only include the row with this event ID.

    Returns
    -------
        pd.DataFrame: DataFrame containing the CMT solutions data / filtered by event ID if provided.
    """
    cmt_df = pd.read_csv(CMT_DATA_PATH, dtype={"PublicID": str})
    if event_id is not None:
        cmt_df = cmt_df[cmt_df["PublicID"] == event_id]
        # Check that the event_id exists in the dataframe
        if cmt_df.empty:
            raise ValueError(f"Event ID {event_id} not found in CMT solutions dataset.")
    return cmt_df