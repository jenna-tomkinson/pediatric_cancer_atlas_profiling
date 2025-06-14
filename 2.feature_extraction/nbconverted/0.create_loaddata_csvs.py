#!/usr/bin/env python
# coding: utf-8

# # Create LoadData CSVs with the paths to IC functions for analysis
# 
# In this notebook, we create LoadData CSVs that contains paths to each channel per image set and associated illumination correction `npy` files per channel for CellProfiler to process. 

# ## Import libraries

# In[1]:


import argparse
import pathlib
import pandas as pd
import re

import sys

sys.path.append("../utils")
import loaddata_utils as ld_utils


# ## Set paths

# In[2]:


argparse = argparse.ArgumentParser(
    description="Create LoadData CSV files to run CellProfiler on the cluster"
)
argparse.add_argument("--HPC", action="store_true", help="Type of compute to run on")

# Parse arguments
args = argparse.parse_args(args=sys.argv[1:] if "ipykernel" not in sys.argv[0] else [])
HPC = args.HPC

print(f"HPC: {HPC}")


# In[3]:


# Batch name to find images
batch_name = "Round_2_data"
# Set the index directory based on whether HPC is used or not
if HPC:
    # Path for index directory to make loaddata csvs though compute cluster (HPC)
    index_directory = pathlib.Path(
        f"/scratch/alpine/jtomkinson@xsede.org/ALSF_pilot_data/{batch_name}/"
    )
else:
    # Path for index directory  to make loaddata csv locally
    index_directory = pathlib.Path(f"/media/18tbdrive/ALSF_pilot_data/{batch_name}/")

# Set all paths that are common to both HPC and local
config_dir_path = pathlib.Path("../1.illumination_correction/config_files").resolve(
    strict=True
)
output_csv_dir = pathlib.Path(f"./loaddata_csvs/{batch_name}").absolute()
output_csv_dir.mkdir(parents=True, exist_ok=True)
illum_directory = pathlib.Path(
    f"../1.illumination_correction/illum_directory/{batch_name}"
).resolve(strict=True)

# Find all 'Images' folders within the directory
images_folders = list(index_directory.rglob("Images"))


# ## Create LoadData CSVs with illumination functions for all data

# In[4]:


# Define the one config path to use
config_path = config_dir_path / "config.yml"

# Find all Plate folders
plate_folders = list(index_directory.glob("Plate *"))

# Build mapping of BR00 IDs to plate number
br00_to_plate = {}

# First parse "All Cell Lines" folders to get BR00 IDs
for plate_folder in plate_folders:
    if "All Cell Lines" in plate_folder.name:
        for subfolder in plate_folder.iterdir():
            if subfolder.is_dir():
                br00_id = subfolder.name.split("__")[0]
                plate_num = plate_folder.name.split()[1]
                br00_to_plate[br00_id] = plate_num

# Now process everything
for plate_folder in plate_folders:
    for subfolder in plate_folder.iterdir():
        if not subfolder.is_dir():
            continue

        br00_id = subfolder.name.split("__")[0]

        if "All Cell Lines" in plate_folder.name:
            # Original run
            plate_name = f"{br00_id}"
        else:
            # Reimaged
            parts = plate_folder.name.split()
            plate_num = parts[1]
            cell_line = (
                " ".join(parts[2:]).replace("Reimage", "").strip().replace(" ", "_")
            )
            plate_name = f"{br00_id}_{cell_line}_Reimage"

        path_to_output_csv = (
            output_csv_dir / f"{plate_name}_loaddata_original.csv"
        ).absolute()
        path_to_output_with_illum_csv = (
            output_csv_dir / f"{plate_name}_loaddata_with_illum.csv"
        ).absolute()
        folder = subfolder.absolute()
        plate_id = br00_id
        illum_output_path = (illum_directory / plate_id).absolute().resolve(strict=True)

        # Call the function to create the LoadData CSV
        ld_utils.create_loaddata_illum_csv(
            index_directory=folder / "Images",
            config_path=config_path,
            path_to_output=path_to_output_csv,
            illum_directory=illum_output_path,
            plate_id=plate_id,
            illum_output_path=path_to_output_with_illum_csv,
        )


# ## Concat the re-imaged data back to their original plate and remove the original poor quality data paths
# 
# All CSVs have linkage back to the IC directory and functions.

# ### Collect a list of original CSVs and identify unique plate IDs

# In[5]:


# Step 1: Find all CSV files in the output directory
csv_files = list(output_csv_dir.glob("*.csv"))

# Step 2: Extract unique BR00 IDs from filenames
br00_pattern = re.compile(r"(BR00\d+)")  # Regex to match 'BR00' followed by digits

# Collect all matching BR00 IDs from filenames
br00_ids = {
    br00_pattern.search(csv_file.stem).group(1)
    for csv_file in csv_files
    if br00_pattern.search(csv_file.stem)
}

# Sort BR00 IDs numerically to be consistent in ordering
br00_ids = sorted(
    br00_ids, key=lambda x: int(x[4:])
)  # Convert digits part to integer for numerical sorting

print(f"Found {len(br00_ids)} BR00 IDs: {br00_ids}")


# ### Track/store files and add a metadata column for if a row is re-imaged or not

# In[6]:


# Step 3: Initialize storage to track used files and find proper column order
br00_dataframes = {br_id: [] for br_id in br00_ids}
used_files = set()  # Store filenames used in the process
concat_files = []  # Track new concatenated CSV files

# Load one BR00 starting CSV that will have the correct column order
column_order = pd.read_csv(
    pathlib.Path(f"{output_csv_dir}/{list(br00_ids)[0]}_loaddata_with_illum.csv"),
    nrows=0,
).columns.tolist()

# Step 4: Add 'Metadata_Reimaged' column and group by BR00 ID
for csv_file in csv_files:
    filename = csv_file.stem
    match = br00_pattern.search(filename)

    if match:
        br_id = match.group(1)

        # Read the CSV file into a DataFrame
        loaddata_df = pd.read_csv(csv_file)

        # Reorder DataFrame columns to match the correct column order
        loaddata_df = loaddata_df[
            column_order
        ]  # Ensure the columns are in the correct order

        # Add 'Metadata_Reimaged' column based on filename
        loaddata_df["Metadata_Reimaged"] = "Re-imaged" in filename

        # Append the DataFrame to the corresponding BR00 group
        br00_dataframes[br_id].append(loaddata_df)

        # Track this file as used
        used_files.add(csv_file.name)

# Print an example DataFrame (first BR00 group)
example_id = next(iter(br00_dataframes))  # Get the first BR00 ID
example_df = pd.concat(br00_dataframes[example_id], ignore_index=True)
print(f"\nExample DataFrame for BR00 ID: {example_id}")
example_df.iloc[:, [0, 1, -1]]  # Display only the first two and last column


# ### Concat the re-imaged and original data for the same plate and remove any duplicate wells that come from the original data
# 
# We remove the duplicates that aren't re-imaged since they are of poor quality. We want to analyze the re-imaged data from those same wells.

# In[7]:


# Step 5: Concatenate DataFrames, drop duplicates, and save per BR00 ID
for br_id, dfs in br00_dataframes.items():
    if dfs:  # Only process if there are matching files
        concatenated_df = pd.concat(dfs, ignore_index=True)

        # Drop duplicates, prioritizing rows with 'Metadata_Reimaged' == True
        deduplicated_df = concatenated_df.sort_values(
            "Metadata_Reimaged", ascending=False
        ).drop_duplicates(subset=["Metadata_Well", "Metadata_Site"], keep="first")

        # Sort by 'Metadata_Col', 'Metadata_Row', and 'Metadata_Site
        sorted_df = deduplicated_df.sort_values(
            ["Metadata_Col", "Metadata_Row", "Metadata_Site"], ascending=True
        )

        # Enforce correct plate ID for all rows
        sorted_df["Metadata_Plate"] = br_id

        # Define the expected base path for images
        expected_base_path = str(index_directory.resolve())

        # List of columns that contain image paths (not illum functions)
        image_path_columns = [
            col
            for col in loaddata_df.columns
            if col.startswith("PathName_") and "Illum" not in col
        ]

        # Sanity check: Ensure all image paths start with the expected base path
        warning_found = False
        for col in image_path_columns:
            if (
                not loaddata_df[col]
                .astype(str)
                .str.startswith(expected_base_path)
                .all()
            ):
                print(
                    f"Warning: Not all paths in column '{col}' start with '{expected_base_path}'"
                )
                warning_found = True

        if not warning_found:
            print(f"All image path columns start correctly for {plate_name}")

        # Save the cleaned, concatenated, and sorted DataFrame to a new CSV file
        output_path = output_csv_dir / f"{br_id}_concatenated_with_illum.csv"
        sorted_df.to_csv(output_path, index=False)

        print(f"Saved: {output_path}")
        concat_files.append(output_path)  # Track new concatenated files
    else:
        print(f"No files found for {br_id}")


# ### Confirm that all LoadData CSV files were included in previous concat (avoid data loss)

# In[8]:


# Step 6: Verify all files were used
unused_files = set(csv_file.name for csv_file in csv_files) - used_files

if unused_files:
    print("Warning: Some files were not used in the concatenation!")
    for file in unused_files:
        print(f"Unused: {file}")
else:
    print("All files were successfully used.")


# ### Remove the original CSV files to prevent CellProfiler from using them

# In[9]:


# Step 7: Remove all non-concatenated CSVs to avoid confusion
for csv_file in csv_files:
    if csv_file not in concat_files:  # Keep only new concatenated files
        csv_file.unlink()  # Delete the file
        print(f"Removed: {csv_file.name}")
print("All non-concatenated CSV files have been removed.")

