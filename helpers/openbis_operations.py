"""OpenBIS operations: creating samples and attaching datasets."""

from helpers.openbis_client import (
    add_dataset,
    build_experimental_step_name,
    build_resin_name,
)
from config import VERSION, APP_NAME


def create_sample_and_attach_summary(
    o,
    experiment,
    collection_path,
    exp_step_code,
    sample_code,
    parents,
    excel_bytes,
    purpose=None,
):
    """Create an experimental step and a resin sample in openBIS with the Excel summary.

    Parameters:
    - o: openBIS client object
    - experiment: experiment dict
    - collection_path: openBIS collection path
    - exp_step_code: experimental step code (e.g., "RES_2PP_20260310_001_EXP")
    - sample_code: sample code to create (e.g., "RES_2PP_20260310_001_SAMPLE")
    - parents: list of parent permIDs for the experimental step
    - excel_bytes: bytes of the Excel summary file
    - purpose: optional purpose description

    Returns a tuple (sample, dataset, export_path) on success. Raises on failure.
    """
    if o is None:
        raise RuntimeError("Not connected to openBIS")

    # Step 1: Create the experimental step
    exp_step_name = build_experimental_step_name(experiment, o)

    exp_step_description = f"Purpose: {purpose or 'N/A'}<br>Created using {APP_NAME} version {VERSION}"

    exp_step = o.new_sample(
        type="EXPERIMENTAL_STEP",
        collection=collection_path,
        code=exp_step_code,
        parents=parents if parents else None,
        props={
            "$name": exp_step_name,
            "finished_flag": True,
            "experimental_step.experimental_description": exp_step_description,
        },
    )
    exp_step.save()

    # Step 2: Create the resin sample with the experimental step as parent
    resin_code = sample_code
    resin_name = build_resin_name(experiment, o)

    sample_description = f"Purpose: {purpose or 'N/A'}<br>Created using {APP_NAME} version {VERSION}"

    sample = o.new_sample(
        type="SAMPLE",
        collection=collection_path,
        code=resin_code,
        parents=[exp_step.permId],  # Parent is the experimental step
        props={
            "$name": resin_name,
            "description": sample_description,
            "bam_oe": "OE_5.4",
        },
    )
    sample.save()

    # Attach Excel dataset to the sample if provided
    ds = None
    export_path = None
    if excel_bytes:
        ds, export_path = add_dataset(o, sample, experiment, excel_bytes)

    return sample, ds, export_path
