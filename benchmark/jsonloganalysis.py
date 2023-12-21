import argparse
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd


def combine_logs_to_csv(
        args: argparse.Namespace,
    ) -> None:
    """
    Combines all logs in a directory into a single csv file.

    Args:
        log_dir: Directory containing the log files.
        save_path: Path to save the output output CSV.
        load_recursive: Whether to load logs in all subdirectories of log_dir. 
            Defaults to True.
    """
    log_dir = args.logdir
    save_path = args.savepath
    load_recursive = args.load_recursive

    log_dir = Path(log_dir)
    log_files = log_dir.rglob("*.log") if load_recursive else log_dir.glob("*.log")
    log_files = sorted(log_files)
    num_files = len(log_files)
    # Extract run info from each log file
    run_summaries = [extract_run_info_from_log_path(log_file) for log_file in log_files]
    run_summaries = [summary for summary in run_summaries if isinstance(summary, dict)]
    # Convert to dataframe and save to csv
    if run_summaries:
        df = pd.DataFrame(run_summaries)
        df.set_index("filename", inplace=True)
        df.to_csv(save_path, index=True)
        logging.info(f"Saved {len(df)} runs to {save_path}")
    else:
        logging.error(f"No valid runs found in {log_dir}")
    return

def extract_run_info_from_log_path(log_file: str) -> Optional[dict]:
    """Extracts run info from log file path"""
    run_args = None
    last_logged_stats = None
    early_terminated = False
    # Process lines, including only info before early termination or when requests start to drain
    with open(log_file) as f:
        for line in f.readlines():
            if "got terminate signal" in line:
                early_terminated = True
            if "got terminate signal" in line or "requests to drain" in line:
                # Ignore any stats after termination or draining of requests (since RPM, TPM, rate etc will start to decline as requests gradually finish)
                break
            # Save most recent line prior to termination/draining
            if "Load" in line:
                run_args = json.loads(line.split("Load test args: ")[-1])
            if "run_seconds" in line:
                last_logged_stats = line
    if not run_args:
        logging.error(f"Could not extract run args from log file {log_file} - missing run info (it might have been generated with a previous code version).")
        return None
    run_args["early-terminated"] = early_terminated
    run_args["filename"] = Path(log_file).name
    # Extract last line of valid stats from log if available
    if last_logged_stats:
        last_logged_stats = flatten_dict(json.loads(last_logged_stats))
        run_args.update(last_logged_stats)
    return run_args

def flatten_dict(input: dict) -> dict:
    """
    Flattens dictionary of nested dictionaries/lists into a single level dictionary
    Taken from https://www.geeksforgeeks.org/flattening-json-objects-in-python/
    """
    out = {}
 
    def flatten(x, name=''):
        # If the Nested key-value
        # pair is of dict type
        if isinstance(x, dict):
            for a in x:
                flatten(x[a], name + a + '_')
 
        # If the Nested key-value
        # pair is of list type
        elif isinstance(x, dict):
            i = 0
            for a in x:
                flatten(a, name + str(i) + '_')
                i += 1
        else:
            out[name[:-1]] = x
 
    flatten(input)
    return out
