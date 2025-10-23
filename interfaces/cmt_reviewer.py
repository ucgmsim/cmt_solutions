import numpy as np
import streamlit as st
import pandas as pd
import pydeck as pdk
from pathlib import Path

from cmt_solutions import cmt_data
from source_modelling.community_fault_model import community_fault_model_as_geodataframe
from source_modelling import magnitude_scaling
from source_modelling.sources import Plane


from shapely.geometry import LineString, MultiLineString


st.set_page_config(layout="wide")

def split_dateline_shapely(geom):
    """Split geometry at the dateline (±180°)."""
    if geom.is_empty:
        return geom
    coords = list(geom.coords)
    parts = []
    current_part = [coords[0]]
    for (lon1, lat1), (lon2, lat2) in zip(coords[:-1], coords[1:]):
        if abs(lon2 - lon1) > 180:
            if lon1 > 0:
                lon_cross = 180
            else:
                lon_cross = -180
            frac = (lon_cross - lon1) / (lon2 - lon1)
            lat_cross = lat1 + frac * (lat2 - lat1)
            current_part.append((lon_cross, lat_cross))
            parts.append(LineString(current_part))
            lon_cross = -180 if lon_cross == 180 else 180
            current_part = [(lon_cross, lat_cross), (lon2, lat2)]
        else:
            current_part.append((lon2, lat2))
    parts.append(LineString(current_part))
    if len(parts) == 1:
        return parts[0]
    return MultiLineString(parts)


# corners expected as a (4,2) array from `np1.corners[:, :2]` etc.
def segments_from_corners(corners, strike, color, segments_per_line=20, keep_stride=2):
    corners = np.asarray(corners)
    if corners.shape != (4, 2):
        raise ValueError("Expected corners shape (4,2)")

    # Heuristic: lat in [-90,90], lon in [-180,180]
    col0_in_lon_range = (np.abs(corners[:, 0]) <= 180).all() and (
        np.abs(corners[:, 0]) > 90
    ).any()
    col1_in_lon_range = (np.abs(corners[:, 1]) <= 180).all() and (
        np.abs(corners[:, 1]) > 90
    ).any()

    if col0_in_lon_range and not col1_in_lon_range:
        lon = corners[:, 0]
        lat = corners[:, 1]
    elif col1_in_lon_range and not col0_in_lon_range:
        lon = corners[:, 1]
        lat = corners[:, 0]
    else:
        lat = corners[:, 0]
        lon = corners[:, 1]

    def row(i, j):
        return {
            "lon1": float(lon[i]),
            "lat1": float(lat[i]),
            "lon2": float(lon[j]),
            "lat2": float(lat[j]),
            "strike": float(strike),
        }

    # solid single segment (0->1)
    solid_df = pd.DataFrame([row(0, 1)])

    # original dashed segments (1->2, 2->3, 3->0)
    raw_dashed = [row(1, 2), row(2, 3), row(3, 0)]

    # build many short segments and keep every `keep_stride` piece to simulate dashes
    dash_pieces = []
    for seg in raw_dashed:
        lon_a, lat_a = seg["lon1"], seg["lat1"]
        lon_b, lat_b = seg["lon2"], seg["lat2"]
        # linear interpolation (simple and usually fine for short lines)
        lons = np.linspace(lon_a, lon_b, segments_per_line + 1)
        lats = np.linspace(lat_a, lat_b, segments_per_line + 1)
        for i in range(segments_per_line):
            if (i % keep_stride) == 0:
                dash_pieces.append(
                    {
                        "lon1": float(lons[i]),
                        "lat1": float(lats[i]),
                        "lon2": float(lons[i + 1]),
                        "lat2": float(lats[i + 1]),
                        "strike": seg["strike"],
                    }
                )

    dashed_segments_df = pd.DataFrame(dash_pieces)

    solid_layer = pdk.Layer(
        "LineLayer",
        data=solid_df,
        get_source_position=["lon1", "lat1"],
        get_target_position=["lon2", "lat2"],
        get_color=color,
        get_width=3,
        pickable=False,
    )

    # dashed simulated via many short visible segments
    dashed_layer = pdk.Layer(
        "LineLayer",
        data=dashed_segments_df,
        get_source_position=["lon1", "lat1"],
        get_target_position=["lon2", "lat2"],
        get_color=color,
        get_width=3,
        pickable=False,
    )

    return solid_layer, dashed_layer


@st.cache_data
def load_data():
    # Load fault model
    fault_gdf = community_fault_model_as_geodataframe()
    fault_gdf = fault_gdf.to_crs(epsg=4326)
    fault_gdf = fault_gdf.reset_index()

    fault_gdf["trace"] = fault_gdf["trace"].apply(split_dateline_shapely)

    cmt_df = cmt_data.get_cmt_data()
    cmt_df = cmt_df.set_index("PublicID")

    # # Load CMT solutions
    # modified_cmt_df = pd.read_csv(
    #     NZGMDB_DATA.fetch("GeoNet_CMT_solutions_20201129_PreferredNodalPlane_v1.csv")
    # )
    #
    # config = cfg.Config()
    # geonet_cmt_df = pd.read_csv(config.get_value("cmt_url"), dtype={"PublicID": str})
    #
    # # Merge updates
    # geonet_cmt_df = geonet_cmt_df.set_index("PublicID")
    # modified_cmt_df = modified_cmt_df.set_index("PublicID")
    # geonet_cmt_df.update(modified_cmt_df)

    return fault_gdf, cmt_df


def render_event_review(event_id, fault_gdf, cmt_gdf):
    """
    Render the full review UI for a single event_id.
    - event_id: index value in cmt_gdf
    - fault_gdf: GeoDataFrame with fault traces (EPSG:4326) and attributes used for tooltips
    - cmt_gdf: DataFrame indexed by PublicID with event fields used below
    - output_file: CSV file to append review results to (`cmt_reviewed.csv` by default)
    Returns: chosen plane as "1" or "2", or None if nothing chosen or event missing.
    """
    if event_id not in cmt_gdf.index:
        st.error(f"Event {event_id} not found in provided cmt_gdf")
        return None

    event = cmt_gdf.loc[event_id]

    # --- Event header ---
    st.subheader(f"Event {event_id} Mw {event.Mw:.1f} Depth {event.CD:.1f} km")

    # Check if the event has already been reviewed
    if event.get("reviewed", False):
        st.info(f"This event has already been reviewed by {event.get('reviewer', 'unknown')}.")

    # --- Build fault DataFrame for PyDeck (recreate compactly to keep function self-contained) ---
    all_lines = []
    fault_names = []
    dip_ranges = []
    dip_directions = []
    rake_ranges = []
    for idx, geom in enumerate(fault_gdf.geometry):
        if geom.is_empty:
            continue
        if geom.geom_type == "LineString":
            all_lines.append(list(geom.coords))
            fault_names.append(fault_gdf.iloc[idx]["name"])
            dip_ranges.append(fault_gdf.iloc[idx]["dip_range"])
            dip_directions.append(str(fault_gdf.iloc[idx]["dip_dir"]))
            rake_ranges.append(fault_gdf.iloc[idx]["rake_range"])
        elif geom.geom_type == "MultiLineString":
            for part in geom.geoms:
                all_lines.append(list(part.coords))
                fault_names.append(fault_gdf.iloc[idx]["name"])
                dip_ranges.append(fault_gdf.iloc[idx]["dip_range"])
                dip_directions.append(str(fault_gdf.iloc[idx]["dip_dir"]))
                rake_ranges.append(fault_gdf.iloc[idx]["rake_range"])

    fault_df = pd.DataFrame(
        {
            "path": all_lines,
            "fault_name": fault_names,
            "dip_range": dip_ranges,
            "dip_direction": dip_directions,
            "rake_range": rake_ranges,
        }
    )
    fault_df["tooltip"] = (
        "<div style='font-family:Arial,Helvetica,sans-serif;font-size:12px;'>"
        + "<b>Fault:</b> "
        + fault_df["fault_name"].astype(str)
        + "<br><b>Dip:</b> "
        + fault_df["dip_range"].astype(str)
        + "<br><b>Dip dir:</b> "
        + fault_df["dip_direction"].astype(str)
        + "<br><b>Rake:</b> "
        + fault_df["rake_range"].astype(str)
        + "</div>"
    )

    fault_layer = pdk.Layer(
        "PathLayer",
        data=fault_df,
        get_path="path",
        get_color=[200, 30, 0],
        width_scale=1,
        width_min_pixels=3,
        pickable=True,
        auto_highlight=True,
    )

    # --- Epicenter ---
    epicenter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame(
            {"lat": [event.Latitude], "lon": [event.Longitude], "Mw": [event.Mw]}
        ),
        get_position=["lon", "lat"],
        get_color=[255, 215, 0],
        get_radius=event.Mw * 200,
    )

    # --- Create plane visuals (uses magnitude_scaling, Plane, and segments_from_corners in module) ---
    length_np1, width_np1 = magnitude_scaling.magnitude_to_length_width(
        magnitude_scaling.ScalingRelation.LEONARD2014, event.Mw, event["rake1"]
    )
    length_np2, width_np2 = magnitude_scaling.magnitude_to_length_width(
        magnitude_scaling.ScalingRelation.LEONARD2014, event.Mw, event["rake2"]
    )

    np1 = Plane.from_centroid_strike_dip(
        np.asarray([event.Latitude, event.Longitude, 0]),
        event["dip1"],
        length_np1,
        width_np1,
        strike=event["strike1"],
    )
    np2 = Plane.from_centroid_strike_dip(
        np.asarray([event.Latitude, event.Longitude, 0]),
        event["dip2"],
        length_np2,
        width_np2,
        strike=event["strike2"],
    )

    np1_corners = np1.corners[:, :2]
    np2_corners = np2.corners[:, :2]

    solid_1, dashed_1 = segments_from_corners(np1_corners, event["strike1"], [0, 255, 0])
    solid_2, dashed_2 = segments_from_corners(np2_corners, event["strike2"], [0, 0, 255])

    tooltip = {"html": "{tooltip}", "style": {"backgroundColor": "white", "color": "black"}}
    view_state = pdk.ViewState(
        latitude=event.Latitude, longitude=event.Longitude, zoom=8, pitch=0
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[fault_layer, epicenter_layer, solid_1, dashed_1, solid_2, dashed_2],
            initial_view_state=view_state,
            tooltip=tooltip,
        )
    )

    # --- Nodal plane selection UI and persistence ---
    def plane_html(title, strike, dip, rake, border_color, text_color):
        return f"""
        <div style="border:2px solid {border_color}; padding:10px; border-radius:8px; margin-bottom:8px;">
          <div style="font-weight:600; color:{text_color}; margin-bottom:6px;">{title}</div>
          <table style="border-collapse:collapse; width:100%;">
            <tr><th style="text-align:left; padding:4px 8px;">Strike</th><td style="padding:4px 8px; color:{text_color};">{strike:.1f}</td></tr>
            <tr><th style="text-align:left; padding:4px 8px;">Dip</th><td style="padding:4px 8px; color:{text_color};">{dip:.1f}</td></tr>
            <tr><th style="text-align:left; padding:4px 8px;">Rake</th><td style="padding:4px 8px; color:{text_color};">{rake:.1f}</td></tr>
          </table>
        </div>
        """

    html1 = plane_html(
        "Nodal Plane 1",
        float(event["strike1"]),
        float(event["dip1"]),
        float(event["rake1"]),
        border_color="#28a745",
        text_color="#28a745",
    )
    html2 = plane_html(
        "Nodal Plane 2",
        float(event["strike2"]),
        float(event["dip2"]),
        float(event["rake2"]),
        border_color="#007bff",
        text_color="#007bff",
    )

    col1, col2 = st.columns(2)
    choice = None
    with col1:
        st.markdown(html1, unsafe_allow_html=True)
        if st.button("Select Plane 1", key=f"select_plane_1_{event_id}"):
            choice = "1"
    with col2:
        st.markdown(html2, unsafe_allow_html=True)
        if st.button("Select Plane 2", key=f"select_plane_2_{event_id}"):
            choice = "2"

    return choice

fault_gdf, cmt_gdf = load_data()

# compute global Mw bounds
_global_min_mw = float(cmt_gdf["Mw"].min())
_global_max_mw = float(cmt_gdf["Mw"].max())

# --- Session state initialization ---
if "cmt_work" not in st.session_state:
    cmt_work = cmt_gdf.copy()
    st.session_state.cmt_work = cmt_work
# default mw_range on first load: lower bound 5.0
if "mw_range" not in st.session_state:
    st.session_state.mw_range = (5.0, _global_max_mw)
if "show_reviewed" not in st.session_state:
    st.session_state.show_reviewed = False
if "filtered_ids" not in st.session_state:
    lo, hi = st.session_state.mw_range
    filtered_df = st.session_state.cmt_work[
        (st.session_state.cmt_work["Mw"] >= lo)
        & (st.session_state.cmt_work["Mw"] <= hi)
    ]
    if not st.session_state.show_reviewed:
        filtered_df = filtered_df[filtered_df["reviewed"] == False]
    st.session_state.filtered_ids = list(filtered_df.index)
if "pos" not in st.session_state:
    st.session_state.pos = 0
if "output_file" not in st.session_state:
    st.session_state.output_file = cmt_data.CMT_DATA_PATH



st.sidebar.header("User Settings")
username = st.sidebar.text_input("Enter your username for review:")
if username:
    # Set the reviewer name
    st.session_state.reviewer_name = username

    # with col_filters:
    st.sidebar.title("New Zealand CMT Reviewer")
    st.sidebar.write(
        "Select nodal plane solutions (1 or 2) for manual review of earthquake Centroid Moment Tensor solutions. "
        "Community Fault Model traces are shown for context as well as the epicenter and "
        "the two nodal planes (based on Leonard2014 model). Use the filters below to narrow down the events to review"
    )

    mw_range = st.sidebar.slider(
        "Magnitude (Mw) range",
        min_value=_global_min_mw,
        max_value=_global_max_mw,
        value=st.session_state.mw_range,
        step=0.1,
    )
    st.session_state.show_reviewed = st.sidebar.checkbox(
        "Show reviewed CMT solutions", value=st.session_state.show_reviewed
    )
    if st.sidebar.button("Apply filters"):
        # Reload cmt_work from original to reset any prior filtering
        cmt_df = cmt_data.get_cmt_data()
        cmt_df = cmt_df.set_index("PublicID")
        st.session_state.cmt_work = cmt_df.copy()
        # filter ids and reset position to first
        st.session_state.mw_range = mw_range
        lo, hi = mw_range
        filtered = st.session_state.cmt_work[
            (st.session_state.cmt_work["Mw"] >= lo)
            & (st.session_state.cmt_work["Mw"] <= hi)
        ]
        if not st.session_state.show_reviewed:
            filtered = filtered[filtered["reviewed"] == False]
        st.session_state.filtered_ids = list(filtered.index)
        st.session_state.pos = 0
        st.rerun()

    # If filtered list is empty, show message
    if len(st.session_state.filtered_ids) == 0:
        st.info("No events match the current filters. Adjust filters in the left column.")
    else:
        # clamp pos
        pos = max(0, min(st.session_state.pos, len(st.session_state.filtered_ids) - 1))
        st.session_state.pos = pos
        current_id = st.session_state.filtered_ids[pos]

        # Select box to jump to any event in current filtered list
        event_id = st.selectbox("Select Event (PublicID)", options=st.session_state.filtered_ids, index=pos, key="event_select")

        # Sync pos if user selected different event
        if event_id != current_id:
            st.session_state.pos = st.session_state.filtered_ids.index(event_id)
            current_id = event_id

        # Render the review UI for current event
        choice = render_event_review(current_id, fault_gdf, st.session_state.cmt_work)

        # Navigation and actions
        nav_col1, nav_col2 = st.columns([1,1])
        with nav_col1:
            if st.button("Previous"):
                st.session_state.pos = max(0, st.session_state.pos - 1)
                st.rerun()

        with nav_col2:
            if st.button("Next"):
                st.session_state.pos = min(
                    len(st.session_state.filtered_ids) - 1, st.session_state.pos + 1
                )
                st.rerun()

        total = len(st.session_state.filtered_ids) or 1
        current = st.session_state.pos + 1
        pct = int(current / total * 100)
        # visual progress bar (0-100)
        st.progress(pct)
        # textual status + small hint
        st.markdown(f"**Progress:** {current} / {total} — **{pct}%**")
        st.caption("Use Previous / Next to navigate; completed when 100%")

        if choice is not None:
            rid = current_id
            reviewer = st.session_state.get("reviewer_name", username)
            st.session_state.cmt_work.at[rid, "reviewed"] = True
            st.session_state.cmt_work.at[rid, "reviewer"] = reviewer

            # Set the PreferredPlane based on user choice
            s1 = st.session_state.cmt_work.at[rid, "strike1"]
            d1 = st.session_state.cmt_work.at[rid, "dip1"]
            r1 = st.session_state.cmt_work.at[rid, "rake1"]
            s2 = st.session_state.cmt_work.at[rid, "strike2"]
            d2 = st.session_state.cmt_work.at[rid, "dip2"]
            r2 = st.session_state.cmt_work.at[rid, "rake2"]

            if choice == "1":
                pref, other = (s1, d1, r1), (s2, d2, r2)
            else:
                pref, other = (s2, d2, r2), (s1, d1, r1)

            st.session_state.cmt_work.at[rid, "strike1"] = pref[0]
            st.session_state.cmt_work.at[rid, "dip1"] = pref[1]
            st.session_state.cmt_work.at[rid, "rake1"] = pref[2]
            st.session_state.cmt_work.at[rid, "strike2"] = other[0]
            st.session_state.cmt_work.at[rid, "dip2"] = other[1]
            st.session_state.cmt_work.at[rid, "rake2"] = other[2]

            try:
                st.session_state.cmt_work.to_csv(
                    st.session_state.output_file, index=True
                )
                st.success(f"Saved review for {event_id} (Plane {choice})")
            except Exception as e:
                st.error(f"Failed to save `{st.session_state.output_file}`: {e}")

            # Always advance to the next index in the filtered list unless we're at the last one
            last_index = len(st.session_state.filtered_ids) - 1
            if st.session_state.pos < last_index:
                st.session_state.pos = st.session_state.pos + 1
            else:
                st.info("Reached last event in filtered list.")
            st.rerun()

