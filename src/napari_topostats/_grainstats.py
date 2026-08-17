"""Module for containing functions and widgets for running and displaying results from topostats grainstats"""

import pandas as pd
from napari.layers import Labels
from topostats.grainstats import GrainStats


def grainstats(image: Labels) -> pd.DataFrame:
    """Function used for running topostats grainstats function on a labels layer"""
    cfg = image.metadata["config"]["grainstats"]
    if "run" in cfg:
        cfg.pop("run")
    if "class_names" in cfg:
        cfg.pop("class_names")
    topostats_object = image.metadata["topostats_object"]
    stats = GrainStats(
        topostats_object,
        base_output_dir="grains",
        **cfg,
    )
    stats.calculate_stats()
    df = get_grainstats_df(stats)

    # Get scaling factors from metadata

    # Convert centre coordinates back to pixels if they exist
    if "centre_x" in df.columns and "centre_y" in df.columns:
        pixel_to_nm_scaling = image.metadata.get("px2nm", 1.0)
        metre_scaling_factor = image.metadata.get("metre_scaling_factor", 1e-9)
        length_scaling_factor = pixel_to_nm_scaling * metre_scaling_factor
        df["centre_x_px"] = df["centre_x"] / length_scaling_factor
        df["centre_y_px"] = df["centre_y"] / length_scaling_factor

        return df

    return df


def get_grainstats_df(stats: GrainStats) -> pd.DataFrame:
    """
    Reconstructs the 'grainstats' DataFrame from the nested
    grain_crops.stats attributes.
    """
    rows = []

    # 1. Check if grains exist
    if not stats.grain_crops:
        # Return empty DF with expected columns if no grains (optional, mimics old behavior)
        return pd.DataFrame()

    # Iterate through the nested structure
    for grain_index, grain_crop in stats.grain_crops.items():

        # Skip if stats haven't been calculated yet
        if not hasattr(grain_crop, "stats") or not grain_crop.stats:
            continue

        for class_index, subgrains in grain_crop.stats.items():
            for subgrain_index, stats_dict in subgrains.items():

                # Create a copy of the stats to avoid modifying the object
                row = stats_dict.copy()

                # Inject the ID columns
                row["grain_number"] = grain_index
                row["class_number"] = class_index
                row["subgrain_number"] = subgrain_index

                # Handle Image Name
                if hasattr(stats.topostats_object, "filename"):
                    row["image"] = stats.topostats_object.filename
                elif hasattr(stats.topostats_object, "image_name"):
                    row["image"] = stats.topostats_object.image_name
                else:
                    row["image"] = "unknown"

                # Handle 'threshold'
                if hasattr(stats.topostats_object, "direction"):
                    row["threshold"] = stats.topostats_object.direction

                rows.append(row)

    # Create DataFrame
    df = pd.DataFrame(rows)
    return df
