import numpy as np
import pandas as pd
from rest_api.models import HistoricSpeed


def get_historical_mad_stats(day_type: str) -> pd.DataFrame:
    """
    Calculate MAD statistics from historical speed data.

    Groups by segment and temporal_segment to get median and MAD for each
    segment-time combination based on historical records.

    Args:
        day_type: Day type filter ('L' for weekday, 'S' for Saturday, 'D' for Sunday)

    Returns:
        DataFrame with columns: segment_id, temporal_segment, hist_median, hist_mad
    """
    # Get all historical speeds for this day type
    # Use shape__id (integer PK) to match the speed calculation which uses shape_pk
    historic_qs = HistoricSpeed.objects.filter(day_type=day_type).values(
        "segment__shape__id",  # shape_id (integer PK)
        "segment__sequence",  # spatial_segment_index
        "temporal_segment",
        "speed",
    )

    if not historic_qs.exists():
        return pd.DataFrame(
            columns=[
                "shape_id",
                "spatial_segment_index",
                "temporal_segment",
                "hist_median",
                "hist_mad",
            ]
        )

    hist_df = pd.DataFrame.from_records(historic_qs)
    hist_df = hist_df.rename(
        columns={
            "segment__shape__id": "shape_id",
            "segment__sequence": "spatial_segment_index",
        }
    )

    # Ensure consistent types for merge keys
    # shape_id from DB is int, but speed.py may pass strings
    hist_df["shape_id"] = hist_df["shape_id"].astype(str)
    hist_df["spatial_segment_index"] = hist_df["spatial_segment_index"].astype(int)
    hist_df["temporal_segment"] = hist_df["temporal_segment"].astype(int)

    # Calculate median and MAD per segment + temporal_segment
    def calc_mad_stats(group):
        speeds = group["speed"]
        median = speeds.median()
        mad = np.median(np.abs(speeds - median))
        return pd.Series(
            {"hist_median": median, "hist_mad": mad, "hist_count": len(speeds)}
        )

    stats_df = (
        hist_df.groupby(["shape_id", "spatial_segment_index", "temporal_segment"])
        .apply(calc_mad_stats, include_groups=False)
        .reset_index()
    )

    return stats_df


def apply_mad_filter_with_historical(
    df: pd.DataFrame,
    day_type: str,
    speed_col: str = "speed(km/h)",
    z_incident: float = 3.0,
    z_outlier: float = 5,
    fallback_min: float = 3.0,
    fallback_max: float = 90.0,
    fallback_flag: bool = True,
):
    """
    Apply MAD filtering using historical data as baseline.

    For each record, compares current speed against historical median/MAD
    for that segment and temporal period. If no historical data exists,
    falls back to simple bounds filtering.

    Args:
        df: DataFrame with current speed data (must include: shape_id, spatial_segment_index, temporal_segment)
        day_type: Day type ('L', 'S', 'D') for historical lookup
        speed_col: Name of speed column
        z_incident: Z-score threshold for flagging incidents (default 3.0)
        z_outlier: Z-score threshold for removing outliers (default 5)
        fallback_min: Minimum speed when no historical data (default 3 km/h)
        fallback_max: Maximum speed when no historical data (default 90 km/h)
        fallback_flag: Whether to flag outliers when using fallback bounds (default True)
    Returns:
        tuple: (df_filtered, df_outliers)
    """
    df = df.copy()

    # Ensure consistent types for merge keys
    # shape_id may come as int or string from different sources
    df["shape_id"] = df["shape_id"].astype(str)
    df["spatial_segment_index"] = df["spatial_segment_index"].astype(int)
    df["temporal_segment"] = df["temporal_segment"].astype(int)

    # Get historical MAD statistics
    print("Loading historical MAD statistics...")
    hist_stats = get_historical_mad_stats(day_type)
    print(f"  Found {len(hist_stats)} historical segment-time combinations")

    # Initialize columns
    df["hist_median"] = np.nan
    df["hist_mad"] = np.nan
    df["z_mad"] = np.nan
    df["status"] = "normal"
    df["filter_method"] = "historical"  # Track which method was used

    # Merge historical stats with current data
    if len(hist_stats) > 0:
        df = df.merge(
            hist_stats[
                [
                    "shape_id",
                    "spatial_segment_index",
                    "temporal_segment",
                    "hist_median",
                    "hist_mad",
                ]
            ],
            on=["shape_id", "spatial_segment_index", "temporal_segment"],
            how="left",
            suffixes=("", "_hist"),
        )
        # Use merged columns if they exist
        if "hist_median_hist" in df.columns:
            df["hist_median"] = df["hist_median_hist"].combine_first(df["hist_median"])
            df["hist_mad"] = df["hist_mad_hist"].combine_first(df["hist_mad"])
            df = df.drop(columns=["hist_median_hist", "hist_mad_hist"], errors="ignore")

    # Process records with historical data
    has_history = (
        df["hist_median"].notna() & df["hist_mad"].notna() & (df["hist_mad"] > 0)
    )

    if has_history.any() and not fallback_flag:
        # Calculate z-scores using historical baseline
        df.loc[has_history, "z_mad"] = np.abs(
            df.loc[has_history, speed_col] - df.loc[has_history, "hist_median"]
        ) / (1.4826 * df.loc[has_history, "hist_mad"])

        # Classify based on z-scores
        outlier_mask = has_history & (df["z_mad"] > z_outlier)
        incident_mask = (
            has_history & (df["z_mad"] > z_incident) & (df["z_mad"] <= z_outlier)
        )

        df.loc[outlier_mask, "status"] = "outlier"
        df.loc[incident_mask, "status"] = "possible_incident"

    # Fallback: records without historical data use simple bounds
    no_history = ~has_history
    if no_history.any() or fallback_flag:
        df.loc[no_history, "filter_method"] = "fallback_bounds"

        # Apply simple bounds for records without history
        speed_values = df.loc[no_history, speed_col]
        below_min = no_history & (df[speed_col] < fallback_min)
        above_max = no_history & (df[speed_col] > fallback_max)

        df.loc[below_min | above_max, "status"] = "outlier"

    # Separate results
    df_filtered = df[df["status"] != "outlier"].copy()
    df_outliers = df[df["status"] == "outlier"].copy()

    # Statistics
    n_total = len(df)
    n_with_history = has_history.sum()
    n_fallback = no_history.sum()
    n_normal = (df["status"] == "normal").sum()
    n_incidents = (df["status"] == "possible_incident").sum()
    n_outliers = len(df_outliers)

    print("MAD Filter Results (Historical-based):")
    print(
        f"  - Records with historical data: {n_with_history} ({100 * n_with_history / n_total:.1f}%)"
    )
    print(
        f"  - Records using fallback bounds: {n_fallback} ({100 * n_fallback / n_total:.1f}%)"
    )
    print(f"  - Normal observations: {n_normal} ({100 * n_normal / n_total:.1f}%)")
    print(f"  - Possible incidents: {n_incidents} ({100 * n_incidents / n_total:.1f}%)")
    print(f"  - Outliers removed: {n_outliers} ({100 * n_outliers / n_total:.1f}%)")
    print(f"  - Retained for processing: {len(df_filtered)} records")

    return df_filtered, df_outliers
