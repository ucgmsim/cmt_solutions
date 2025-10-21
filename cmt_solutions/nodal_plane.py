"""
Contains code to calculate the other nodal plane for earthquake focal mechanisms.
Useful as the John Townend dataset originally had only a single nodal plane provided.
"""

import pandas as pd
from obspy.imaging import beachball

def conjugate_nodal_plane(strike: float, dip: float, rake: float):
    """
    Compute the conjugate/auxiliary nodal plane from input strike, dip, rake.

    Parameters
    ----------
    strike : float
        Strike angle of the first nodal plane in degrees.
    dip : float
        Dip angle of the first nodal plane in degrees.
    rake : float
        Rake angle of the first nodal plane in degrees.

    Returns
    -------
    s2 : float
        Strike angle of the conjugate nodal plane in degrees.
    d2 : float
        Dip angle of the conjugate nodal plane in degrees.
    r2 : float
        Rake angle of the conjugate nodal plane in degrees.
    """

    s2, d2, r2 = beachball.aux_plane(strike, dip, rake)

    # Normalise strike to [0, 360]
    s2 %= 360.0

    # Normalise rake to [-180, 180]
    if r2 > 180.0:
        r2 -= 360.0

    return s2, d2, r2


def add_conjugate_nodal_planes(df: pd.DataFrame,
                               strike_col: str = "strike1",
                               dip_col: str = "dip1",
                               rake_col: str = "rake1") -> pd.DataFrame:
    """
    Add conjugate nodal planes to a DataFrame containing focal mechanism data.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing focal mechanism data with columns for strike, dip, and rake.
    strike_col : str, optional
        Name of the column containing strike values for the first nodal plane.
    dip_col : str, optional
        Name of the column containing dip values for the first nodal plane.
    rake_col : str, optional
        Name of the column containing rake values for the first nodal plane.

    Returns
    -------
    pd.DataFrame
        DataFrame with additional columns for the conjugate nodal plane.
    """

    s2_list = []
    d2_list = []
    r2_list = []

    for _, row in df.iterrows():
        s1 = row[strike_col]
        d1 = row[dip_col]
        r1 = row[rake_col]

        s2, d2, r2 = conjugate_nodal_plane(s1, d1, r1)

        s2_list.append(s2)
        d2_list.append(d2)
        r2_list.append(r2)

    df["strike2"] = s2_list
    df["dip2"] = d2_list
    df["rake2"] = r2_list

    return df