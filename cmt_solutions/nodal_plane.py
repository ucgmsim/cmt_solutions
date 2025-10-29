"""
Contains code to calculate the other nodal plane for earthquake focal mechanisms.
Useful as the John Townend dataset originally had only a single nodal plane provided.
"""

import numpy as np
from obspy.imaging import beachball
import pandas as pd


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


def add_conjugate_nodal_planes(
    df: pd.DataFrame,
    strike_col: str = "strike1",
    dip_col: str = "dip1",
    rake_col: str = "rake1",
) -> pd.DataFrame:
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

    s2, d2, r2 = zip(
        *(
            conjugate_nodal_plane(s, d, r)
            for s, d, r in zip(df[strike_col], df[dip_col], df[rake_col])
        )
    )

    df["strike2"] = np.asarray(s2)
    df["dip2"] = np.asarray(d2)
    df["rake2"] = np.asarray(r2)

    return df
