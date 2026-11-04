# SYNTHETIC DATA · for training only · no OSFI data
"""Builds excel/supervisory_watch_thresholds.xlsx (v1) and _v2.xlsx with the SAME function
nb_fda_00_generate_data uses to drop the v1 file into lh_supervisory/Files/reference.
Internal watch thresholds (illustrative) - NOT OSFI regulatory minimums."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "data_gen"))
import gen_supervisory_data as g  # noqa: E402

if __name__ == "__main__":
    for version, fname in g.THRESHOLD_FILES.items():
        print("wrote", g.build_thresholds_workbook(version, os.path.join(HERE, fname)))
