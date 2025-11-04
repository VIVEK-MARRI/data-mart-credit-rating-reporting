# scripts/generate_outliers.py
import os
import numpy as np
import pandas as pd
from datetime import datetime
import random

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
processed_dir = os.path.join(ROOT, "data", "processed")
tx_csv = os.path.join(processed_dir, "transactions_cleaned.csv")
outlier_csv = os.path.join(processed_dir, "outlier_precision_by_security_date.csv")

# --- Parameters for injection (Option B: medium outliers) ---
RANDOM_SEED = 42
BASE_THRESH = 2                 # original threshold for score_diff → outlier
INJECTION_DATES_PCT = 0.03      # fraction of unique rating_dates to be "spike" dates (3%)
SPIKE_ADDITIONAL_OUTLIER_PCT = 0.45  # increase outlier % to ~45% on spike dates
MAX_VENDORS_TO_CHANGE = 2       # per security/date, change up to 2 vendors to create disagreement

np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)

def normalize_rating_code_to_standard(r):
    if pd.isna(r):
        return "UNRATED"
    return str(r).strip().upper()

# rating scale map (same as project)
scale_order = {"AAA":0,"AA":1,"A":2,"BBB":3,"BB":4,"B":5,"CCC":6,"CC":7,"C":8,"D":9,"UNRATED":10,
               "A+":2, "A-":2, "AA+":1, "AA-":1, "BBB+":3, "BBB-":3, "B+":5, "B-":5, "C+":8, "C-":8,
               "BAA1":2, "BAA2":2, "BAA3":2, # tolerant mapping for varied normalizations
              }

def map_score(s):
    s = normalize_rating_code_to_standard(s)
    # some inputs in dataset like 'BAA1' -> map to 'A' family fallback
    if s in scale_order:
        return scale_order[s]
    # try coarse rules:
    if s.startswith("AA"): return 1
    if s.startswith("A"): return 2
    if s.startswith("BBB"): return 3
    if s.startswith("BB"): return 4
    if s.startswith("B"): return 5
    if s.startswith("CCC") or s.startswith("CC") or s.startswith("C"): return 6
    if s.startswith("D"): return 9
    return 10

def main():
    if not os.path.exists(tx_csv):
        raise SystemExit(f"Transactions file not found: {tx_csv}")

    df = pd.read_csv(tx_csv, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Ensure rating_date present
    if 'rating_date' not in df.columns:
        if 'rating_date_raw' in df.columns:
            df['rating_date'] = pd.to_datetime(df['rating_date_raw'], errors='coerce')
        else:
            df['rating_date'] = pd.NaT
    else:
        df['rating_date'] = pd.to_datetime(df['rating_date'], errors='coerce')

    df = df.dropna(subset=['security_id', 'rating_date'])
    df['rating_type'] = df['rating_type'].fillna('Unknown')

    # Standard rating fallback from provided column
    if 'standard_rating' in df.columns:
        df['standard_rating'] = df['standard_rating'].fillna(df.get('rating_code', 'UNRATED'))
    else:
        df['standard_rating'] = df.get('rating_code', df.get('rating_raw', 'UNRATED')).fillna('UNRATED')

    df['rating_score'] = df['standard_rating'].apply(map_score).astype(int)

    # pivot vendors to columns
    pivot = df.pivot_table(
        index=['security_id','rating_date','rating_type'],
        columns='vendor',
        values='rating_score',
        aggfunc='first'
    ).reset_index()

    vendor_cols = [c for c in pivot.columns if c not in ['security_id','rating_date','rating_type']]

    # compute metrics
    pivot['score_min'] = pivot[vendor_cols].min(axis=1, skipna=True)
    pivot['score_max'] = pivot[vendor_cols].max(axis=1, skipna=True)
    pivot['score_diff'] = (pivot['score_max'] - pivot['score_min']).fillna(0).astype(int)
    pivot['total_vendors'] = pivot[vendor_cols].notnull().sum(axis=1).astype(int)
    pivot['is_outlier'] = (pivot['score_diff'] >= BASE_THRESH).astype(int)
    pivot['precision'] = 1.0  # placeholder if you have precision metric logic

    # Now inject controlled medium outliers (Option B)
    unique_dates = pivot['rating_date'].dropna().unique()
    n_spike_dates = max(1, int(len(unique_dates) * INJECTION_DATES_PCT))
    spike_dates = set(np.random.choice(unique_dates, size=n_spike_dates, replace=False))

    # For each spike date pick random securities and flip some vendor scores to make disagreement
    for sd in spike_dates:
        # select rows with that date
        rows = pivot[pivot['rating_date'] == sd].index.tolist()
        if not rows:
            continue
        # choose a fraction to be spikes on that date
        n_rows_to_spike = max(1, int(len(rows) * 0.15))  # spike ~15% of securities that date
        rows_to_spike = random.sample(rows, min(len(rows), n_rows_to_spike))

        for ridx in rows_to_spike:
            # which vendor cols exist
            present_vendors = [c for c in vendor_cols if pd.notna(pivot.at[ridx, c])]
            if len(present_vendors) < 2:
                continue
            k = min(MAX_VENDORS_TO_CHANGE, max(1, int(len(present_vendors) * 0.25)))
            vendors_to_change = random.sample(present_vendors, k)

            # shift their scores randomly up/down by 2-6 grade steps (makes score_diff grow)
            for v in vendors_to_change:
                old = pivot.at[ridx, v]
                if pd.isna(old):
                    continue
                # choose direction (up=improve -> lower numeric, down=worse -> higher numeric)
                direction = random.choice([-1, 1])
                magnitude = random.choice([2,3,4,5])
                new_score = int(max(0, min(10, old + direction * magnitude)))
                pivot.at[ridx, v] = new_score

            # recompute min/max/diff/is_outlier for this row
            vals = [pivot.at[ridx, c] for c in vendor_cols if pd.notnull(pivot.at[ridx, c])]
            if vals:
                smin = int(np.nanmin(vals))
                smax = int(np.nanmax(vals))
                pivot.at[ridx, 'score_min'] = smin
                pivot.at[ridx, 'score_max'] = smax
                pivot.at[ridx, 'score_diff'] = int(smax - smin)
                pivot.at[ridx, 'is_outlier'] = int((smax - smin) >= BASE_THRESH)

    # Recompute outlier_pct by date after injection
    pivot['rating_date'] = pd.to_datetime(pivot['rating_date'])
    outlier_pct_by_date = (
        pivot.groupby('rating_date')['is_outlier']
        .mean()
        .reset_index()
        .rename(columns={'is_outlier':'outlier_pct'})
    )

    # Merge metrics to create output table with one row per security/date/type
    output = pivot[['security_id','rating_date','rating_type','total_vendors','score_min','score_max','score_diff','is_outlier']].copy()
    # attach precision placeholder
    output['precision'] = 1.0

    # Also compute an aggregated per security-date outlier_pct (if desired)
    # We'll produce a per-row outlier_pct = is_outlier (0/1) so your fact table gets per-security outlier flags.
    output['outlier_pct'] = output['is_outlier']  # 0 or 1 (if you want percentage by date, load outlier_pct_by_date separately)

    # Ensure rating_date is date only for CSV
    output['rating_date'] = output['rating_date'].dt.date

    # Save CSV (overwrite)
    output.to_csv(outlier_csv, index=False)
    print(f"Wrote outlier CSV: {outlier_csv} ({len(output)} rows)")
    print("Sample rows:")
    print(output.head())

if __name__ == "__main__":
    main()
