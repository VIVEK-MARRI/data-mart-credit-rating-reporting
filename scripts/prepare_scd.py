
import pandas as pd
import os

def build_type2(staging_csv, out_csv):
    df = pd.read_csv(staging_csv, parse_dates=['rating_date'])
    df = df.sort_values(['security_id','vendor','rating_type','rating_date'])
    rows = []
    surrogate = 1
    for (sec, ven, rtype), grp in df.groupby(['security_id','vendor','rating_type']):
        grp = grp.sort_values('rating_date')
        active = None
        for _, r in grp.iterrows():
            rating = r['standard_rating']
            start = r['rating_date']
            if active is None:
                active = {'scd_key':surrogate,'security_id':sec,'vendor':ven,'rating_type':rtype,'rating':rating,'effective_start_date':start,'effective_end_date':None,'is_active':1}
                surrogate += 1
            else:
                if rating == active['rating']:
                    continue
                else:
                    active['effective_end_date'] = start - pd.Timedelta(days=1)
                    active['is_active'] = 0
                    rows.append(active)
                    active = {'scd_key':surrogate,'security_id':sec,'vendor':ven,'rating_type':rtype,'rating':rating,'effective_start_date':start,'effective_end_date':None,'is_active':1}
                    surrogate += 1
        if active:
            rows.append(active)
    out = pd.DataFrame(rows)
    out.to_csv(out_csv, index=False)
    print('SCD written to', out_csv)

if __name__ == '__main__':
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    staging = os.path.join(root, 'data','processed','transactions_cleaned.csv')
    out = os.path.join(root, 'data','processed','ratings_type2_sample_from_script.csv')
    build_type2(staging, out)
