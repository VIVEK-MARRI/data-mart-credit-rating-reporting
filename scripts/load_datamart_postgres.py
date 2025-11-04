# scripts/load_datamart_postgres.py
import os
import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")

# ---------------------------
# Load environment
# ---------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_PATH = os.path.join(ROOT, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "credit_rating_dm")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

if DB_PASSWORD == "":
    print("ERROR: DB_PASSWORD is empty. Update your .env with DB_PASSWORD.")
    sys.exit(1)

SCHEMA = os.getenv("DB_SCHEMA", "credit_dm")

# ---------------------------
# Create engine
# ---------------------------
CONN_STR = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(CONN_STR, pool_pre_ping=True)

print(f"Connecting to DB: {DB_NAME} @ {DB_HOST}:{DB_PORT} as {DB_USER} (schema={SCHEMA})")

# ---------------------------
# Paths to CSVs
# ---------------------------
processed_dir = os.path.join(ROOT, "data", "processed")
transactions_csv = os.path.join(processed_dir, "transactions_cleaned.csv")
outlier_csv = os.path.join(processed_dir, "outlier_precision_by_security_date.csv")
rating_freq_csv = os.path.join(processed_dir, "rating_frequency_per_vendor_year.csv")

# ---------------------------
# Helper DB / Upsert functions
# ---------------------------
def upsert_dim_security(df_security):
    if df_security.empty:
        print("No security rows to upsert.")
        return
    print(f"Upserting {len(df_security)} dim_security rows...")
    with engine.begin() as conn:
        for _, row in df_security.iterrows():
            conn.execute(text(f"""
                INSERT INTO {SCHEMA}.dim_security (security_id, security_name, sector, country, issue_date)
                VALUES (:security_id, :security_name, :sector, :country, :issue_date)
                ON CONFLICT (security_id) DO UPDATE SET
                  security_name = EXCLUDED.security_name,
                  sector = EXCLUDED.sector,
                  country = EXCLUDED.country;
            """), {
                "security_id": row.get("security_id"),
                "security_name": row.get("security_name"),
                "sector": row.get("sector"),
                "country": row.get("country"),
                "issue_date": row.get("issue_date")
            })
    print("dim_security upsert complete.")

def upsert_dim_vendor(df_vendor):
    if df_vendor.empty:
        print("No vendor rows to upsert.")
        return
    print(f"Upserting {len(df_vendor)} dim_rating_agency rows...")
    with engine.begin() as conn:
        for _, row in df_vendor.iterrows():
            vendor_name = row.get("vendor_name") or row.get("vendor") or "UNKNOWN"
            try:
                conn.execute(text(f"""
                    INSERT INTO {SCHEMA}.dim_rating_agency (vendor_id, vendor_name, vendor_code, country)
                    VALUES (:vendor_id, :vendor_name, :vendor_code, :country)
                    ON CONFLICT (vendor_name) DO UPDATE SET
                        vendor_id = EXCLUDED.vendor_id,
                        vendor_code = EXCLUDED.vendor_code,
                        country = EXCLUDED.country;
                """), {
                    "vendor_id": row.get("vendor_id"),
                    "vendor_name": vendor_name,
                    "vendor_code": row.get("vendor_code"),
                    "country": row.get("country")
                })
            except Exception as e:
                print(f"Warning: failed to upsert vendor '{vendor_name}': {e}")
    print("dim_rating_agency upsert complete.")

def load_dim_rating_types(df):
    if 'rating_type' not in df.columns:
        print("rating_type column missing; skipping rating type load.")
        return
    types = pd.Series(df['rating_type'].dropna().unique()).tolist()
    if not types:
        print("No rating_type values to insert.")
        return
    print(f"Loading {len(types)} rating types into dim_rating_type...")
    with engine.begin() as conn:
        for t in types:
            conn.execute(text(f"""
                INSERT INTO {SCHEMA}.dim_rating_type (rating_type)
                VALUES (:t)
                ON CONFLICT (rating_type) DO NOTHING;
            """), {"t": t})
    print("dim_rating_type loaded.")

def get_security_key(security_id):
    if pd.isna(security_id):
        return None
    with engine.begin() as conn:
        res = conn.execute(text(f"SELECT security_key FROM {SCHEMA}.dim_security WHERE security_id = :sid"), {"sid": security_id}).fetchone()
        return res[0] if res else None

def get_vendor_key(vendor_name):
    if pd.isna(vendor_name):
        return None
    with engine.begin() as conn:
        res = conn.execute(text(f"SELECT vendor_key FROM {SCHEMA}.dim_rating_agency WHERE vendor_name = :v"), {"v": vendor_name}).fetchone()
        return res[0] if res else None

def get_rating_type_key(rtype):
    if pd.isna(rtype):
        return None
    with engine.begin() as conn:
        res = conn.execute(text(f"SELECT rating_type_key FROM {SCHEMA}.dim_rating_type WHERE rating_type = :r"), {"r": rtype}).fetchone()
        return res[0] if res else None

# ---------------------------
# SCD Type-2 Upsert Logic (idempotent)
# ---------------------------
def scd_type2_upsert(trans_df, verbose=False):
    """
    trans_df columns expected:
      security_id, vendor, rating_type, original_rating, standard_rating, rating_score, rating_date, source_feed_id, rating_outlook (optional)
    This function is idempotent: repeated runs won't insert duplicate rows for the same (security, vendor, rating_type, effective_start_date).
    """
    if trans_df.empty:
        print("No transactions to process for SCD.")
        return

    # Ensure rating_date is datetime.date
    trans_df = trans_df.copy()
    if 'rating_date' in trans_df.columns:
        trans_df['rating_date'] = pd.to_datetime(trans_df['rating_date'], errors='coerce')
    else:
        trans_df['rating_date'] = pd.NaT

    trans_df = trans_df.sort_values(["security_id","vendor","rating_type","rating_date"]).reset_index(drop=True)
    print(f"Starting SCD Type-2 upsert for {len(trans_df)} rows...")
    with engine.begin() as conn:
        for idx, r in trans_df.iterrows():
            sec_key = get_security_key(r.security_id)
            vend_key = get_vendor_key(r.vendor)
            rtype_key = get_rating_type_key(r.rating_type)

            if sec_key is None or vend_key is None or rtype_key is None:
                if verbose:
                    print(f"Skipping idx {idx}: missing FK (security_id={r.security_id}, vendor={r.vendor}, rating_type={r.rating_type})")
                continue

            if pd.isna(r['rating_date']):
                if verbose:
                    print(f"Skipping idx {idx}: null rating_date for security {r.security_id}")
                continue

            start_dt = pd.to_datetime(r['rating_date']).date()

            # Find currently active record
            cur = conn.execute(text(f"""
                SELECT scd_key, standard_rating, effective_start_date FROM {SCHEMA}.fact_ratings_scd
                 WHERE security_key = :sec AND vendor_key = :vend AND rating_type_key = :rtype AND is_active = true
                 ORDER BY effective_start_date DESC LIMIT 1
            """), {"sec": sec_key, "vend": vend_key, "rtype": rtype_key}).fetchone()

            try:
                if cur is None:
                    # Insert new active record - idempotent via ON CONFLICT DO NOTHING
                    conn.execute(text(f"""
                        INSERT INTO {SCHEMA}.fact_ratings_scd
                        (security_key, vendor_key, rating_type_key, original_rating, standard_rating, rating_score, rating_outlook, effective_start_date, effective_end_date, is_active, source_feed_id)
                        VALUES (:sec, :vend, :rtype, :orig, :std, :score, :outlook, :start, NULL, TRUE, :src)
                        ON CONFLICT (security_key, vendor_key, rating_type_key, effective_start_date) DO NOTHING
                    """), {
                        "sec": sec_key, "vend": vend_key, "rtype": rtype_key,
                        "orig": r.get("original_rating"), "std": r.get("standard_rating"), "score": int(r.get("rating_score", 999)),
                        "outlook": r.get("rating_outlook"), "start": start_dt, "src": r.get("source_feed_id")
                    })
                else:
                    current_scd_key, current_std_rating, current_start = cur[0], cur[1], cur[2]
                    cur_std = str(current_std_rating) if current_std_rating is not None else None
                    new_std = str(r.get("standard_rating")) if r.get("standard_rating") is not None else None

                    if cur_std != new_std:
                        # expire existing record
                        end_date = start_dt - timedelta(days=1)
                        conn.execute(text(f"""
                            UPDATE {SCHEMA}.fact_ratings_scd
                            SET effective_end_date = :endd, is_active = false
                            WHERE scd_key = :k
                        """), {"endd": end_date, "k": current_scd_key})

                        # Insert new active record (idempotent insert)
                        conn.execute(text(f"""
                            INSERT INTO {SCHEMA}.fact_ratings_scd
                            (security_key, vendor_key, rating_type_key, original_rating, standard_rating, rating_score, rating_outlook, effective_start_date, effective_end_date, is_active, source_feed_id)
                            VALUES (:sec, :vend, :rtype, :orig, :std, :score, :outlook, :start, NULL, TRUE, :src)
                            ON CONFLICT (security_key, vendor_key, rating_type_key, effective_start_date) DO NOTHING
                        """), {
                            "sec": sec_key, "vend": vend_key, "rtype": rtype_key,
                            "orig": r.get("original_rating"), "std": r.get("standard_rating"), "score": int(r.get("rating_score", 999)),
                            "outlook": r.get("rating_outlook"), "start": start_dt, "src": r.get("source_feed_id")
                        })
                    else:
                        # same rating -> nothing to do
                        if verbose:
                            print(f"Idx {idx}: same rating; no action.")
                        continue
            except Exception as e:
                print(f"Warning: SCD operation failed at idx {idx} (security_id={r.security_id}, vendor={r.vendor}, date={start_dt}) -> {e}")
                # continue processing next rows
                continue
    print("SCD Type-2 upsert finished.")

# ---------------------------
# Load fact_outlier_metrics
# ---------------------------
# inside scripts/load_datamart_postgres.py — replace load_fact_outlier with this

def load_fact_outlier(pivot_df):
    if pivot_df.empty:
        print("No outlier rows to load.")
        return
    print(f"Loading fact_outlier_metrics for {len(pivot_df)} rows (overwrite mode)...")
    with engine.begin() as conn:
        for _, r in pivot_df.iterrows():
            sec_key = get_security_key(r.security_id)
            rtype_key = get_rating_type_key(r.rating_type)
            if sec_key is None or rtype_key is None:
                print(f"Skipping outlier row for security {r.get('security_id')} due to missing FK")
                continue
            try:
                # Delete existing row(s) for same key+date+type to implement overwrite
                conn.execute(text(f"""
                    DELETE FROM {SCHEMA}.fact_outlier_metrics
                    WHERE security_key = :sec AND rating_date = :rdate AND rating_type_key = :rtype
                """), {"sec": sec_key, "rdate": pd.to_datetime(r.get("rating_date")).date(), "rtype": rtype_key})

                conn.execute(text(f"""
                    INSERT INTO {SCHEMA}.fact_outlier_metrics
                    (security_key, rating_date, rating_type_key, outlier_pct, total_vendors, score_min, score_max, score_diff, precision_score)
                    VALUES (:sec, :rdate, :rtype, :outlier, :tot, :minv, :maxv, :diff, :prec)
                """), {
                    "sec": sec_key, "rdate": pd.to_datetime(r.get("rating_date")).date(), "rtype": rtype_key,
                    "outlier": float(r.get("outlier_pct", 0.0)),
                    "tot": int(r.get("total_vendors", 0)),
                    "minv": int(r.get("score_min", 0) if pd.notna(r.get("score_min")) else 0),
                    "maxv": int(r.get("score_max", 0) if pd.notna(r.get("score_max")) else 0),
                    "diff": int(r.get("score_diff", 0)),
                    "prec": float(r.get("precision", 1.0))
                })
            except Exception as e:
                print(f"Warning: failed to insert outlier row for security {r.get('security_id')}: {e}")
    print("fact_outlier_metrics loaded .")


# ---------------------------
# Load KPI rating changes
# ---------------------------
def load_kpi_rating_freq(kpi_df):
    if kpi_df.empty:
        print("No KPI rows to load.")
        return
    print(f"Loading kpi_rating_changes for {len(kpi_df)} rows...")
    with engine.begin() as conn:
        for _, r in kpi_df.iterrows():
            vendor_key = get_vendor_key(r.get("vendor"))
            if vendor_key is None:
                print(f"Skipping KPI row for vendor {r.get('vendor')} - vendor not found.")
                continue
            year = int(r.get("year"))
            change_count = int(r.get("rating_change_count", 0))
            upgrades = int(r.get("rating_upgrades", 0)) if "rating_upgrades" in r.index else None
            downgrades = int(r.get("rating_downgrades", 0)) if "rating_downgrades" in r.index else None
            net = int(r.get("net_change", 0)) if "net_change" in r.index else None
            try:
                conn.execute(text(f"""
                    INSERT INTO {SCHEMA}.kpi_rating_changes (vendor_key, year, rating_change_count, rating_upgrades, rating_downgrades, net_change, load_timestamp)
                    VALUES (:vk, :yr, :cnt, :up, :down, :net, now())
                    ON CONFLICT (vendor_key, year) DO UPDATE SET
                        rating_change_count = EXCLUDED.rating_change_count,
                        rating_upgrades = EXCLUDED.rating_upgrades,
                        rating_downgrades = EXCLUDED.rating_downgrades,
                        net_change = EXCLUDED.net_change,
                        load_timestamp = now()
                """), {"vk": vendor_key, "yr": year, "cnt": change_count, "up": upgrades, "down": downgrades, "net": net})
            except Exception as e:
                print(f"Warning: failed to upsert KPI row vendor={r.get('vendor')}, year={year}: {e}")
    print("kpi_rating_changes loaded.")

# ---------------------------
# Utility: print table counts
# ---------------------------
def print_table_counts():
    with engine.begin() as conn:
        for t in ["dim_security", "dim_rating_agency", "dim_rating_type", "fact_ratings_scd", "fact_outlier_metrics", "kpi_rating_changes"]:
            try:
                r = conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.{t}")).fetchone()
                print(f"{t}: {r[0] if r else 0} rows")
            except Exception as e:
                print(f"{t}: error reading count -> {e}")

# ---------------------------
# MAIN ETL Flow
# ---------------------------
def main():
    # 1. Check files
    missing = []
    for f in [transactions_csv]:
        if not os.path.exists(f):
            missing.append(f)
    if missing:
        print("Missing required files:", missing)
        sys.exit(1)

    # Read transactions (staging)
    print(f"Reading transactions from {transactions_csv} ...")
    tx = pd.read_csv(transactions_csv, dtype=str)

    # Normalize column names
    tx.columns = [c.strip() for c in tx.columns]

    # Parse rating_date if present, else try rating_date_raw
    if 'rating_date' in tx.columns and tx['rating_date'].notnull().any():
        tx['rating_date'] = pd.to_datetime(tx['rating_date'], errors='coerce')
    elif 'rating_date_raw' in tx.columns:
        tx['rating_date'] = tx['rating_date_raw'].apply(lambda x: pd.to_datetime(x, errors='coerce'))
    else:
        tx['rating_date'] = pd.NaT

    # Ensure vendor column present - use vendor or vendor_name fallback
    if 'vendor' not in tx.columns and 'vendor_name' in tx.columns:
        tx['vendor'] = tx['vendor_name']
    tx['vendor'] = tx['vendor'].fillna('').astype(str).str.strip()
    # If vendor empty, later fill with vendor_code
    if 'vendor_code' not in tx.columns:
        tx['vendor_code'] = None

    # Ensure vendor_id column exists
    if 'vendor_id' not in tx.columns:
        tx['vendor_id'] = None

    # standard_rating fallback to rating_raw or rating_code
    if 'standard_rating' not in tx.columns or tx['standard_rating'].isnull().all():
        if 'rating_raw' in tx.columns:
            tx['standard_rating'] = tx['rating_raw'].astype(str).str.upper()
        elif 'rating_code' in tx.columns:
            tx['standard_rating'] = tx['rating_code'].astype(str).str.upper()
        else:
            tx['standard_rating'] = 'UNRATED'
    tx['standard_rating'] = tx['standard_rating'].fillna('UNRATED').astype(str).str.upper()

    # original rating
    if 'rating_code' in tx.columns:
        tx['original_rating'] = tx['rating_code']
    elif 'rating_raw' in tx.columns:
        tx['original_rating'] = tx['rating_raw']
    else:
        tx['original_rating'] = None

    # rating_outlook optional
    if 'rating_outlook' not in tx.columns:
        tx['rating_outlook'] = None

    # Create security df for upsert
    if 'security_id' not in tx.columns:
        print("ERROR: transactions file does not have 'security_id' column.")
        sys.exit(1)

    sec_df = tx[['security_id']].drop_duplicates().reset_index(drop=True)
    # optional metadata mapping if present
    if 'security_name' in tx.columns:
        sec_df['security_name'] = tx.groupby('security_id')['security_name'].first().reindex(sec_df['security_id']).values
    else:
        sec_df['security_name'] = None
    if 'sector' in tx.columns:
        sec_df['sector'] = tx.groupby('security_id')['sector'].first().reindex(sec_df['security_id']).values
    else:
        sec_df['sector'] = None
    if 'country' in tx.columns:
        sec_df['country'] = tx.groupby('security_id')['country'].first().reindex(sec_df['security_id']).values
    else:
        sec_df['country'] = None

    # Vendor df
    vend_df = tx[['vendor','vendor_code','vendor_id']].drop_duplicates().rename(columns={'vendor':'vendor_name'})
    vend_df['country'] = None

    # 2. Upsert dimensions
    upsert_dim_security(sec_df)
    upsert_dim_vendor(vend_df)
    load_dim_rating_types(tx)

    # 3. Compute rating_score mapping
    scale_order = {"AAA":0,"AA":1,"A":2,"BBB":3,"BB":4,"B":5,"CCC":6,"CC":7,"C":8,"D":9,"UNRATED":10}
    tx['standard_rating'] = tx['standard_rating'].astype(str).str.upper()
    tx['rating_score'] = tx['standard_rating'].map(scale_order).fillna(10).astype(int)

    # 4. Run SCD Type-2 upsert
    scd_input_cols = ['security_id','vendor','rating_type','original_rating','standard_rating','rating_score','rating_date','source_feed_id','rating_outlook','vendor_code']
    scd_df = tx.reindex(columns=[c for c in scd_input_cols if c in tx.columns]).copy()

    # If vendor is empty, fill from vendor_code, then fallback to 'UNKNOWN'
    scd_df['vendor'] = scd_df['vendor'].fillna('').replace('', np.nan)
    if 'vendor_code' in scd_df.columns:
        scd_df['vendor'] = scd_df['vendor'].fillna(scd_df['vendor_code'])
    scd_df['vendor'] = scd_df['vendor'].fillna('UNKNOWN').astype(str).str.strip()

    # Ensure rating_date is datetime
    if 'rating_date' in scd_df.columns:
        scd_df['rating_date'] = pd.to_datetime(scd_df['rating_date'], errors='coerce')

    scd_type2_upsert(scd_df)

    # 5. Load outlier & KPI if present
    if os.path.exists(outlier_csv):
        print(f"Reading outlier file: {outlier_csv}")
        outlier = pd.read_csv(outlier_csv, parse_dates=['rating_date'], dayfirst=False)
        if 'rating_date' in outlier.columns:
            outlier['rating_date'] = pd.to_datetime(outlier['rating_date'], errors='coerce').dt.date
        load_fact_outlier(outlier)
    else:
        print("Outlier CSV not found; skipping outlier load.")

    if os.path.exists(rating_freq_csv):
        print(f"Reading KPI file: {rating_freq_csv}")
        kpi = pd.read_csv(rating_freq_csv)
        load_kpi_rating_freq(kpi)
    else:
        print("Rating frequency CSV not found; skipping KPI load.")

    print("ETL to Data Mart complete.\n")
    print("Final table counts:")
    print_table_counts()


if __name__ == "__main__":
    main()
