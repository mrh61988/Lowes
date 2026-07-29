import streamlit as st
import pandas as pd
import numpy as np
import re

# Set page configuration
st.set_page_config(page_title="Ops Manager Dashboard", layout="wide")

st.title("Water Heater & Simple Installs Operations Dashboard")
st.write("Data filtered exclusively for **Water Heaters** and **Simple Installs** business units. Multi-tech jobs are attributed solely to the primary (first named) technician.")

# ---------------------------------------------------------
# TIME FORMATTING HELPER FUNCTION
# ---------------------------------------------------------
def format_hours_mins(decimal_hours):
    """Converts a decimal hour value (e.g., 1.25) into an H:MM string format (e.g., 1:15)"""
    if pd.isna(decimal_hours) or decimal_hours is None:
        return "-"
    total_minutes = int(round(decimal_hours * 60))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}:{minutes:02d}"

# ---------------------------------------------------------
# AUTOMATED DATA SANITIZER HELPER
# ---------------------------------------------------------
def sanitize_numeric_series(series):
    """Cleans currency symbols, formatting commas, and whitespace to extract pure numeric values."""
    cleaned = series.astype(str).str.replace(r'[^\d.-]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce').fillna(0.0)

# ---------------------------------------------------------
# RESILIENT AUTOMATIC COLUMN SCANNING ENGINE
# ---------------------------------------------------------
def auto_map_column(keys, columns, exclude_keys=None):
    """Scans variations of column names using prioritized exact and wildcard matches."""
    columns_lower = [str(c).lower().strip() for c in columns]
    # Priority 1: Direct exact match match
    for k in keys:
        if k in columns_lower:
            return columns[columns_lower.index(k)]
    # Priority 2: Safe contextual wildcard match
    for k in keys:
        for col in columns:
            col_lower = str(col).lower()
            if k in col_lower:
                if exclude_keys and any(ex in col_lower for ex in exclude_keys):
                    continue
                return col
    # Priority 3: Fallback matching
    for k in keys:
        for col in columns:
            if k in str(col).lower():
                return col
    return None

# ---------------------------------------------------------
# DYNAMIC ON-TICKET TIME CALCULATOR ENGINE
# ---------------------------------------------------------
def compute_custom_ticket_hours(row, cols):
    """
    Calculates ticket duration based on workflow status timestamps.
    Start Time: Earliest of 'On The Way', 'Lowes Store', or 'In Progress'.
    End Time: 'Pending Audit'.
    Edge Case 1: Missing start data defaults to 2.0 hours.
    Edge Case 2: Multiple visits select the absolute earliest start milestone.
    """
    start_times = []
    end_times = []
    
    for idx, col_name in enumerate(cols):
        val = row.iloc[idx]
        if pd.isna(val) or str(val).strip() in ['', '-']:
            continue
            
        col_clean = str(col_name).lower()
        # Target Start Milestones
        if 'on the way' in col_clean or 'lowes store' in col_clean or 'in progress' in col_clean:
            if 'start timestamp' in col_clean:
                t = pd.to_datetime(val, errors='coerce')
                if pd.notna(t):
                    start_times.append(t)
                
        # Target End Milestone
        if 'pending audit' in col_clean and 'start timestamp' in col_clean:
            t = pd.to_datetime(val, errors='coerce')
            if pd.notna(t):
                end_times.append(t)
                
    if not end_times:
        return 0.0
        
    latest_end = max(end_times)
    
    if not start_times:
        return 2.0
        
    earliest_start = min(start_times)
    duration = (latest_end - earliest_start).total_seconds() / 3600.0
    return max(0.0, duration)

def compute_job_date(row, cols):
    """Extracts the calendar date the work actually occurred based on milestones."""
    start_times = []
    for idx, col_name in enumerate(cols):
        val = row.iloc[idx]
        if pd.isna(val) or str(val).strip() in ['', '-']:
            continue
        col_clean = str(col_name).lower()
        if 'on the way' in col_clean or 'lowes store' in col_clean or 'in progress' in col_clean:
            if 'start timestamp' in col_clean:
                t = pd.to_datetime(val, errors='coerce')
                if pd.notna(t):
                    start_times.append(t)
    if start_times:
        return min(start_times).date()
    if 'Start Date' in row and pd.notna(row['Start Date']):
        return pd.to_datetime(row['Start Date'], errors='coerce').date()
    return None

# ---------------------------------------------------------
# LABOUR COST CALCULATION ENGINE (JOB TICKETS)
# ---------------------------------------------------------
def calculate_job_labor_cost(row):
    tech = str(row['Assigned Team Members'])
    duration = row['Custom Ticket Hours']
    revenue = row['Total Invoice Amount']
    bu = str(row['Business Unit'])
    
    if pd.isna(duration): duration = 0.0
    if pd.isna(revenue): revenue = 0.0
    
    if tech == 'Sean Marble':
        return duration * (70000 / 2080)
    elif tech == 'Mathew Hodges':
        return duration * (65000 / 2080)
    elif tech in ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']:
        return duration * 25.00
    elif tech in ['Erik Tange', 'Bryan Pickett']:
        return revenue * 0.34
    else:
        is_contractor = any(k in tech.lower() for k in ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian'])
        if is_contractor:
            if 'simple installs' in bu.lower():
                return revenue
            elif 'water heaters' in bu.lower():
                if 'ken' in tech.lower(): return 300.00
                elif 'barber' in tech.lower(): return 600.00
                elif 'wrench' in tech.lower() or 'wrentch' in tech.lower(): return 1800.00
                elif 'indian' in tech.lower() or 'presidio' in tech.lower(): return 600.00
        return 0.0

# ---------------------------------------------------------
# MATERIAL COST CALCULATION ENGINE
# ---------------------------------------------------------
def calculate_job_material_cost(row):
    tech = str(row['Assigned Team Members']).lower()
    bu = str(row['Business Unit']).lower()
    
    prod_cost = pd.to_numeric(row['Invoice - Total Product Cost'], errors='coerce')
    serv_cost = pd.to_numeric(row['Invoice - Total Service Cost'], errors='coerce')
    
    if pd.isna(prod_cost): prod_cost = 0.0
    if pd.isna(serv_cost): serv_cost = 0.0
    
    base_mat = prod_cost + serv_cost
    is_contractor = any(k in tech for k in ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian'])
    
    if is_contractor:
        if 'simple installs' in bu:
            return 0.00
        elif 'water heaters' in bu:
            return 650.00
        return base_mat
    else:
        if 'water heaters' in bu:
            return max(0.00, base_mat - 125.00)
        return base_mat

# ---------------------------------------------------------
# EXEMPTION DETECTION HELPER
# ---------------------------------------------------------
def check_is_exemption(row):
    """Flags if a water heater job falls under LA, PA, or RA specialized streams."""
    title = str(row['Title']).upper()
    tags = [t.strip().upper() for t in str(row['Tags']).split(',')] if pd.notna(row['Tags']) else []
    ex_keys = ['LA', 'PA', 'RA']
    
    if any(k in tags for k in ex_keys):
        return True
    for k in ex_keys:
        if f" {k} " in f" {title} " or title.startswith(f"{k} ") or f" {k}:" in title:
            return True
    return False

# ---------------------------------------------------------
# 1. SIDEBAR FILE UPLOADS
# ---------------------------------------------------------
st.sidebar.header("📁 Upload Operational Data")
st.sidebar.write("Upload all three CSV files to compile comprehensive P&L figures.")

uploaded_jobs = st.sidebar.file_uploader("Upload 'jobs full data.csv'", type=["csv"])
uploaded_invoices = st.sidebar.file_uploader("Upload 'invoices.csv'", type=["csv"])
uploaded_timesheets = st.sidebar.file_uploader("Upload 'timesheets.csv'", type=["csv"])

def process_uploaded_file(file, shifted_header=True):
    if file is not None:
        if shifted_header:
            df_raw = pd.read_csv(file)
            df = df_raw.copy()
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)
            return df
        else:
            return pd.read_csv(file)
    return None

raw_jobs_df = process_uploaded_file(uploaded_jobs, shifted_header=True)
invoices_df = process_uploaded_file(uploaded_invoices, shifted_header=True)
timesheets_df = process_uploaded_file(uploaded_timesheets, shifted_header=False)

# ---------------------------------------------------------
# 2. DASHBOARD LOGIC
# ---------------------------------------------------------
if raw_jobs_df is not None and invoices_df is not None and timesheets_df is not None:
    
    # --- AUTOMATED HEADER DEDUPLICATION UTILITY ---
    def sanitize_and_deduplicate_headers(df):
        seen = {}
        new_columns = []
        for col in df.columns:
            clean_col = str(col).strip()
            if clean_col in seen:
                seen[clean_col] += 1
                new_columns.append(f"{clean_col}_{seen[clean_col]}")
            else:
                seen[clean_col] = 0
                new_columns.append(clean_col)
        df.columns = new_columns
        return df

    raw_jobs_df = sanitize_and_deduplicate_headers(raw_jobs_df)
    invoices_df = sanitize_and_deduplicate_headers(invoices_df)
    timesheets_df = sanitize_and_deduplicate_headers(timesheets_df)
    
    # --- AUTO-MAPPING FOR TIMESHEETS CSV ---
    ts_cols = list(timesheets_df.columns)
    ts_user_col = auto_map_column(['user', 'name', 'technician', 'employee'], ts_cols)
    ts_dur_col = auto_map_column(['duration decimal', 'hours', 'total hours', 'duration'], ts_cols)
    ts_date_col = auto_map_column(['clock in date', 'date', 'work date', 'timestamp'], ts_cols)
    
    if ts_user_col and ts_user_col != 'User':
        timesheets_df['User'] = timesheets_df[ts_user_col]
    if ts_dur_col:
        timesheets_df['Duration Decimal'] = sanitize_numeric_series(timesheets_df[ts_dur_col])
    else:
        timesheets_df['Duration Decimal'] = 0.0
    if ts_date_col:
        timesheets_df['Work Date'] = pd.to_datetime(timesheets_df[ts_date_col], errors='coerce').dt.date

    # --- AUTO-MAPPING FOR JOBS CSV ---
    job_cols_list = list(raw_jobs_df.columns)
    mapped_bu = auto_map_column(['business unit', 'department', 'bu', 'stream'], job_cols_list)
    mapped_tech = auto_map_column(['assigned team members', 'technician', 'lead tech', 'resource', 'name'], job_cols_list, exclude_keys=['id', '#', 'num'])
    mapped_rev = auto_map_column(['total invoice amount', 'revenue', 'amount', 'total', 'price', 'billed'], job_cols_list)
    mapped_est = auto_map_column(['total estimate amount', 'estimate', 'quote', 'estimated cost'], job_cols_list)
    mapped_job_dur = auto_map_column(['job duration decimal', 'job duration', 'wrench hours'], job_cols_list)
    mapped_trav_dur = auto_map_column(['travel duration decimal', 'travel duration', 'drive hours'], job_cols_list)
    mapped_prod = auto_map_column(['invoice - total product cost', 'product cost', 'parts', 'materials'], job_cols_list)
    mapped_serv = auto_map_column(['invoice - total service cost', 'service cost', 'labor cost baseline'], job_cols_list)
    mapped_title = auto_map_column(['title', 'job title', 'summary', 'description'], job_cols_list)
    mapped_tags = auto_map_column(['tags', 'label', 'work type'], job_cols_list)
    mapped_status = auto_map_column(['status', 'job status', 'state'], job_cols_list)
    mapped_zip = auto_map_column(['zip code', 'zip', 'postal'], job_cols_list)
    mapped_rel_inv = auto_map_column(['related invoices', 'invoice id', 'related invoice', 'invoice #'], job_cols_list)
    mapped_id = auto_map_column(['#id', 'job id', 'ticket number', 'id', 'wo #'], job_cols_list)

    # Standardize data structures to run with expected downstream variable structures
    jobs_df_clean = pd.DataFrame()
    jobs_df_clean['Business Unit'] = raw_jobs_df[mapped_bu].fillna('General').astype(str) if mapped_bu else 'General'
    jobs_df_clean['Assigned Team Members'] = raw_jobs_df[mapped_tech].fillna('Unknown Tech').astype(str) if mapped_tech else 'Unknown Tech'
    jobs_df_clean['Total Invoice Amount'] = sanitize_numeric_series(raw_jobs_df[mapped_rev]) if mapped_rev else 0.0
    jobs_df_clean['Total Estimate Amount'] = sanitize_numeric_series(raw_jobs_df[mapped_est]) if mapped_est else 0.0
    jobs_df_clean['Job Duration Decimal'] = sanitize_numeric_series(raw_jobs_df[mapped_job_dur]) if mapped_job_dur else 0.0
    jobs_df_clean['Travel Duration Decimal'] = sanitize_numeric_series(raw_jobs_df[mapped_trav_dur]) if mapped_trav_dur else 0.0
    jobs_df_clean['Invoice - Total Product Cost'] = sanitize_numeric_series(raw_jobs_df[mapped_prod]) if mapped_prod else 0.0
    jobs_df_clean['Invoice - Total Service Cost'] = sanitize_numeric_series(raw_jobs_df[mapped_serv]) if mapped_serv else 0.0
    jobs_df_clean['Title'] = raw_jobs_df[mapped_title].fillna('').astype(str) if mapped_title else ''
    jobs_df_clean['Tags'] = raw_jobs_df[mapped_tags].fillna('').astype(str) if mapped_tags else ''
    jobs_df_clean['Status'] = raw_jobs_df[mapped_status].fillna('').astype(str) if mapped_status else ''
    jobs_df_clean['Zip Code'] = raw_jobs_df[mapped_zip].fillna('').astype(str) if mapped_zip else ''
    jobs_df_clean['Related Invoices'] = raw_jobs_df[mapped_rel_inv].fillna('').astype(str) if mapped_rel_inv else ''
    jobs_df_clean['#ID'] = raw_jobs_df[mapped_id].fillna('').astype(str) if mapped_id else raw_jobs_df.index.astype(str)

    # Re-apply tracking columns dynamically for custom timestamp lookups
    for col in raw_jobs_df.columns:
        if 'timestamp' in str(col).lower():
            jobs_df_clean[col] = raw_jobs_df[col]

    # Filter for active target business units
    jobs_df = jobs_df_clean[jobs_df_clean['Business Unit'].str.contains('Water Heaters|Simple Installs', case=False, na=False)].copy()

    # Split multi-tech entries to primary tech
    jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].astype(str).str.split(',').str[0].str.strip()
    jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].replace(['nan', 'None', ''], None)

    column_headers = jobs_df.columns.tolist()
    jobs_df['Custom Ticket Hours'] = jobs_df.apply(lambda r: compute_custom_ticket_hours(r, column_headers), axis=1)
    jobs_df['Work Date'] = jobs_df.apply(lambda r: compute_job_date(r, column_headers), axis=1)

    # --- AUTO-MAPPING FOR INVOICES CSV ---
    inv_cols = list(invoices_df.columns)
    inv_id_col = auto_map_column(['#id', 'invoice id', 'id', 'invoice number'], inv_cols)
    inv_prof_col = auto_map_column(['profit margin', 'margin', 'net profit'], inv_cols)
    
    if inv_id_col and inv_id_col != '#ID':
        invoices_df['#ID'] = invoices_df[inv_id_col]
    if inv_prof_col:
        invoices_df['Profit Margin'] = sanitize_numeric_series(invoices_df[inv_prof_col])
    else:
        invoices_df['Profit Margin'] = 0.0

    # Calculate dynamic scope window from timesheet dates
    valid_ts_dates = timesheets_df['Work Date'].dropna()
    if not valid_ts_dates.empty:
        days_span = (max(valid_ts_dates) - min(valid_ts_dates)).days + 1
        if days_span in [5, 6]:
            total_weeks = 1.0
        else:
            total_weeks = max(1, days_span) / 7.0
    else:
        days_span = 7
        total_weeks = 1.0

    jobs_df['Labor Cost'] = jobs_df.apply(calculate_job_labor_cost, axis=1)
    jobs_df['Material Cost'] = jobs_df.apply(calculate_job_material_cost, axis=1)
    
    # Calculate initial job level Net Profit using base job labor rules
    jobs_df['Net Gross Profit'] = jobs_df['Total Invoice Amount'] - jobs_df['Material Cost'] - jobs_df['Labor Cost']

    tab1, tab2, tab3 = st.tabs(["Technician & Job Metrics", "Financial & Labor ROI", "Geographic Performance"])

    # ---------------------------------------------------------
    # TAB 1: Technician & Job Metrics
    # ---------------------------------------------------------
    with tab1:
        st.header("Technician Productivity & Job Performance")
        completed_jobs = jobs_df[jobs_df['Status'] == 'Completed'].dropna(subset=['Assigned Team Members']).copy()
        
        if not completed_jobs.empty:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📋 Volume & Speed by Technician")
                tech_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                    Total_Jobs_Completed=('Status', 'count'),
                    Avg_Duration_Hours=('Custom Ticket Hours', 'mean'),
                    Total_Revenue_Generated=('Total Invoice Amount', 'sum'),
                    Avg_Revenue_Per_Job=('Total Invoice Amount', 'mean')
                ).reset_index().sort_values('Total_Jobs_Completed', ascending=False)
                
                tech_metrics.columns = ['Name', 'Jobs Completed', 'Avg Job Time (H:MM)', 'Total Revenue', 'Avg Revenue/Job']
                st.dataframe(tech_metrics.style.format({
                    'Avg Job Time (H:MM)': format_hours_mins, 'Total Revenue': '${:,.2f}', 'Avg Revenue/Job': '${:,.2f}'
                }), use_container_width=True, hide_index=True)
                
            with col2:
                st.subheader("🔧 Performance Breakdown by Job Type")
                job_mix = completed_jobs.groupby('Title').agg(
                    Job_Count=('Title', 'count'),
                    Avg_Duration_Hours=('Custom Ticket Hours', 'mean'),
                    Avg_Revenue_Per_Job=('Total Invoice Amount', 'mean'),
                    Total_Revenue=('Total Invoice Amount', 'sum')
                ).reset_index().sort_values('Job_Count', ascending=False)
                
                job_mix.columns = ['Job Title / Type', 'Volume Done', 'Avg Time Spent (H:MM)', 'Avg Ticket Size', 'Total Revenue']
                st.dataframe(job_mix.style.format({
                    'Avg Time Spent (H:MM)': format_hours_mins, 'Avg Ticket Size': '${:,.2f}', 'Total Revenue': '${:,.2f}'
                }), use_container_width=True, hide_index=True)
            
            st.write("---")
            
            # AGGREGATE AUDITING LOG (SORTED BY PAYROLL SLIPPAGE)
            st.subheader("⏰ Clock Hours vs. Ticket Hours Auditing Log (Aggregate Summary)")
            st.write("Exposes team leaks by contrasting total clocked hours against active job tracking. **Sorted by highest financial payroll slippage**.")
            
            ts_totals_audit = timesheets_df.groupby('User')['Duration Decimal'].sum().reset_index()
            all_unique_techs = completed_jobs['Assigned Team Members'].unique()
            
            utilization_records = []
            for tech in all_unique_techs:
                j_hours = completed_jobs[completed_jobs['Assigned Team Members'] == tech]['Custom Ticket Hours'].sum()
                ts_match = ts_totals_audit[ts_totals_audit['User'] == tech]
                ts_hours = ts_match['Duration Decimal'].values[0] if not ts_match.empty else 0.0
                unallocated = max(0.0, ts_hours - j_hours)
                
                is_hourly = tech in ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']
                waste_cost = unallocated * 25.00 if is_hourly else 0.0
                
                utilization_records.append({
                    'Tech Name': tech,
                    'Paid Clock Hours (Timesheets)': ts_hours,
                    'On-Ticket Hours (Parsed)': j_hours,
                    'Unallocated Variance (Hours)': unallocated,
                    'Hourly Payroll Slippage': waste_cost if is_hourly else np.nan
                })
                
            utilization_df = pd.DataFrame(utilization_records).sort_values(by='Hourly Payroll Slippage', ascending=False, na_position='last')
            
            st.dataframe(utilization_df.style.format({
                'Paid Clock Hours (Timesheets)': '{:.2f} hrs', 'On-Ticket Hours (Parsed)': '{:.2f} hrs',
                'Unallocated Variance (Hours)': '{:.2f} hrs', 'Hourly Payroll Slippage': '${:,.2f}'
            }, na_rep='-'), use_container_width=True, hide_index=True)

            st.write("---")

            # DAILY DEEP DIVE FOR HOURLY TECHS
            st.subheader("🔍 Daily Slippage Deep Dive (Hourly Crew)")
            st.write("Identifies explicit dates where hourly field personnel experienced substantial time leaks between active job statuses and paid clock time.")
            
            ts_daily = timesheets_df.groupby(['User', 'Work Date'])['Duration Decimal'].sum().reset_index()
            jobs_daily = completed_jobs.groupby(['Assigned Team Members', 'Work Date'])['Custom Ticket Hours'].sum().reset_index()
            
            daily_merged = pd.merge(ts_daily, jobs_daily, left_on=['User', 'Work Date'], right_on=['Assigned Team Members', 'Work Date'], how='outer')
            hourly_techs_list = ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']
            
            daily_filtered = daily_merged[
                (daily_merged['User'].isin(hourly_techs_list)) | (daily_merged['Assigned Team Members'].isin(hourly_techs_list))
            ].copy().fillna(0)
            
            if not daily_filtered.empty:
                daily_filtered['User'] = np.where(daily_filtered['User'] == 0, daily_filtered['Assigned Team Members'], daily_filtered['User'])
                daily_filtered['Variance Hours'] = daily_filtered['Duration Decimal'] - daily_filtered['Custom Ticket Hours']
                daily_filtered['Slippage Cost'] = daily_filtered['Variance Hours'] * 25.00
                
                daily_filtered = daily_filtered.sort_values(by='Variance Hours', ascending=False)
                daily_display = daily_filtered[['User', 'Work Date', 'Duration Decimal', 'Custom Ticket Hours', 'Variance Hours', 'Slippage Cost']].copy()
                daily_display.columns = ['Technician Name', 'Calendar Date', 'Paid Clocked Hours', 'Logged Wrench Hours', 'Unallocated Variance', 'Daily Payroll Loss']
                
                st.dataframe(daily_display.style.format({
                    'Paid Clocked Hours': '{:.2f} hrs', 'Logged Wrench Hours': '{:.2f} hrs',
                    'Unallocated Variance': '{:.2f} hrs', 'Daily Payroll Loss': '${:,.2f}'
                }), use_container_width=True, hide_index=True)
            else:
                st.info("No daily tracking entries detected for hourly staff within this upload range.")
        else:
            st.warning("No 'Completed' status jobs found.")

    # ---------------------------------------------------------
    # TAB 2: Financial & Labor ROI Metrics
    # ---------------------------------------------------------
    with tab2:
        st.header("Financial Performance & Labor Cost Analysis")
        st.info(f"📅 **Dataset Scope Auto-Detected:** The uploaded logs span **{days_span} calendar days** ({total_weeks:.2f} weeks). Salaried overhead is computed using **{total_weeks:.2f} weeks of full salary burden** (Sean Marble: ${70000/52*total_weeks:,.2f}, Mathew Hodges: ${65000/52*total_weeks:,.2f}) to match this specific tracking window.")
        
        if not completed_jobs.empty:
            st.subheader("📊 Aggregate Team Efficiency")
            fin_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                Jobs_Completed=('Status', 'count'),
                Total_Revenue=('Total Invoice Amount', 'sum'),
                Total_Material_Cost=('Material Cost', 'sum'),
                Total_Labor_Cost_Jobs=('Labor Cost', 'sum')
            ).reset_index()
            
            ts_totals_finance = timesheets_df.groupby('User')['Duration Decimal'].sum().reset_index()
            hourly_techs_list = ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']
            
            def determine_true_labor(row):
                tech = row['Assigned Team Members']
                if tech in hourly_techs_list:
                    match = ts_totals_finance[ts_totals_finance['User'] == tech]
                    if not match.empty:
                        return match['Duration Decimal'].values[0] * 25.00
                    return 0.0
                elif tech == 'Sean Marble':
                    return total_weeks * (70000 / 52)
                elif tech == 'Mathew Hodges':
                    return total_weeks * (65000 / 52)
                return row['Total_Labor_Cost_Jobs']
            
            fin_metrics['Labor Cost Burden'] = fin_metrics.apply(determine_true_labor, axis=1)
            
            # Recompute accurate final net margins based on scaled salary overhead blocks
            fin_metrics['Net Gross Profit'] = fin_metrics['Total_Revenue'] - fin_metrics['Total_Material_Cost'] - fin_metrics['Labor Cost Burden']
            
            revenue_minus_materials = fin_metrics['Total_Revenue'] - fin_metrics['Total_Material_Cost']
            fin_metrics['Labor % of Rev Less Mats'] = (fin_metrics['Labor Cost Burden'] / revenue_minus_materials) * 100
            fin_metrics['Labor % of Rev Less Mats'] = fin_metrics['Labor % of Rev Less Mats'].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            
            fin_metrics_display = fin_metrics[['Assigned Team Members', 'Jobs_Completed', 'Total_Revenue', 'Total_Material_Cost', 'Labor Cost Burden', 'Net Gross Profit', 'Labor % of Rev Less Mats']].copy()
            fin_metrics_display = fin_metrics_display.sort_values(by='Net Gross Profit', ascending=False)
            fin_metrics_display.columns = ['Name', 'Jobs Done', 'Gross Revenue', 'Material Costs', 'Labor Cost Burden', 'Net Gross Profit', 'Labor % of (Rev - Mats)']
            
            st.dataframe(fin_metrics_display.style.format({
                'Gross Revenue': '${:,.2f}', 'Material Costs': '${:,.2f}', 'Labor Cost Burden': '${:,.2f}',
                'Net Gross Profit': '${:,.2f}', 'Labor % of (Rev - Mats)': '{:.1f}%'
            }), use_container_width=True, hide_index=True)
            
            # ---------------------------------------------------------
            # EXEMPTION STREAM SEGMENTER & CONTRACT VARIANCE AUDITS
            # ---------------------------------------------------------
            st.write("---")
            st.subheader("🛠️ Lowe's Contract Protections & Revenue Audits")
            
            col_seg, col_aud = st.columns([4, 5])
            
            with col_seg:
                st.markdown("#### 🔀 Exemption Stream Segmenter (Water Heaters)")
                st.caption("Splits completed Water Heater tickets into Standard Retail (subject to Lowe's 15% cut) vs Program Exceptions (LA/PA/RA).")
                
                wh_jobs = completed_jobs[completed_jobs['Business Unit'].str.contains('Water Heaters', case=False, na=False)].copy()
                
                if not wh_jobs.empty:
                    wh_jobs['Is Exemption'] = wh_jobs.apply(check_is_exemption, axis=1)
                    wh_jobs['Stream Type'] = np.where(wh_jobs['Is Exemption'], "Program Exemption (LA/PA/RA)", "Standard Retail")
                    
                    wh_stream_summary = wh_jobs.groupby('Stream Type').agg(
                        Total_Jobs=('Status', 'count'),
                        Gross_Revenue=('Total Invoice Amount', 'sum'),
                        Material_Costs=('Material Cost', 'sum'),
                        Labor_Costs=('Labor Cost', 'sum')
                    ).reset_index()
                    
                    wh_stream_summary['Net Profit'] = wh_stream_summary['Gross_Revenue'] - wh_stream_summary['Material_Costs'] - wh_stream_summary['Labor_Costs']
                    wh_stream_summary['Avg Profit / Job'] = wh_stream_summary['Net Profit'] / wh_stream_summary['Total_Jobs']
                    
                    wh_stream_summary.columns = ['Revenue Stream', 'Jobs Done', 'Gross Revenue', 'Material Overhead', 'Labor Overhead', 'Net Profit', 'Avg Margin / Job']
                    st.dataframe(wh_stream_summary.style.format({
                        'Gross Revenue': '${:,.2f}', 'Material Overhead': '${:,.2f}', 'Labor Overhead': '${:,.2f}',
                        'Net Profit': '${:,.2f}', 'Avg Margin / Job': '${:,.2f}'
                    }), use_container_width=True, hide_index=True)
                else:
                    st.info("No completed water heater tickets found within this file upload range.")
                    
            with col_aud:
                st.markdown("#### ⚠️ Lowe's 15% Margin Cut Reconciliation Audit")
                st.caption("Flags standard retail water heater installations where the final processed invoice deviates from the required contract value (85% of original estimate).")
                
                if not wh_jobs.empty:
                    wh_standard = wh_jobs[(wh_jobs['Total Estimate Amount'] > 0) & (wh_jobs['Total Invoice Amount'] > 0) & (~wh_jobs['Is Exemption'])].copy()
                    
                    wh_standard['Expected Invoice'] = wh_standard['Total Estimate Amount'] * 0.85
                    wh_standard['Contract Variance'] = wh_standard['Total Invoice Amount'] - wh_standard['Expected Invoice']
                    
                    wh_anomalies = wh_standard[wh_standard['Contract Variance'].abs() > 1.00].copy()
                    
                    if not wh_anomalies.empty:
                        wh_anomalies_display = wh_anomalies[['#ID', 'Assigned Team Members', 'Total Estimate Amount', 'Total Invoice Amount', 'Contract Variance']].sort_values(by='Contract Variance', ascending=True)
                        wh_anomalies_display.columns = ['Job #', 'Primary Tech', 'Original Estimate', 'Lowe\'s Paid Invoice', 'Fee Discrepancy']
                        
                        st.dataframe(wh_anomalies_display.style.format({
                            'Original Estimate': '${:,.2f}', 'Lowe\'s Paid Invoice': '${:,.2f}', 'Fee Discrepancy': '${:,.2f}'
                        }), use_container_width=True, hide_index=True)
                    else:
                        st.success("100% Retainage Compliance: All standard retail water heater remittances align with the 15% discount contract threshold.")
                else:
                    st.info("No compliance data available for standard retail configurations.")
            
            st.write("---")
            
            def color_profit_loss(val):
                if val < 0: return 'background-color: #f8d7da; color: #721c24;'
                elif val == 0: return 'background-color: #fff3cd; color: #856404;'
                else: return 'background-color: #d4edda; color: #155724;'

            contractor_keywords = ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian']
            is_contractor_mask = completed_jobs['Assigned Team Members'].astype(str).str.lower().apply(lambda x: any(k in x for k in contractor_keywords))
            contractor_df = completed_jobs[is_contractor_mask].copy()
            
            st.subheader("🏢 Contractor Aggregate Performance Summary")
            if not contractor_df.empty:
                contractor_summary = contractor_df.groupby('Assigned Team Members').agg(
                    Total_Jobs=('Status', 'count'), Total_Revenue=('Total Invoice Amount', 'sum'),
                    Total_Materials=('Material Cost', 'sum'), Total_Payout=('Labor Cost', 'sum'),
                    Total_Net_Profit=('Net Gross Profit', 'sum')
                ).reset_index().sort_values(by='Total_Net_Profit', ascending=True)
                
                contractor_summary.columns = ['Contractor Name', 'Total Jobs Done', 'Total Revenue', 'Total Material Overhead', 'Total Payouts', 'Total Net Profit / Loss']
                styler_summary = contractor_summary.style.format({
                    'Total Revenue': '${:,.2f}', 'Total Material Overhead': '${:,.2f}',
                    'Total Payouts': '${:,.2f}', 'Total Net Profit / Loss': '${:,.2f}'
                })
                st.dataframe(styler_summary.map(color_profit_loss, subset=['Total Net Profit / Loss']) if hasattr(styler_summary, 'map') else styler_summary.applymap(color_profit_loss, subset=['Total Net Profit / Loss']), use_container_width=True, hide_index=True)
            
            st.write("---")
            
            st.subheader("🏗️ Contractor Profit & Loss Audit (Job-by-Job Detail)")
            if not contractor_df.empty:
                contractor_audit = contractor_df[['#ID', 'Assigned Team Members', 'Business Unit', 'Total Invoice Amount', 'Material Cost', 'Labor Cost', 'Net Gross Profit']].copy().sort_values(by='Net Gross Profit', ascending=True)
                contractor_audit.columns = ['Job #', 'Contractor', 'Business Unit', 'Gross Revenue', 'Material Cost', 'Contractor Payout', 'Net Profit / Loss']
                styler_audit = contractor_audit.style.format({
                    'Gross Revenue': '${:,.2f}', 'Material Cost': '${:,.2f}', 'Contractor Payout': '${:,.2f}', 'Net Profit / Loss': '${:,.2f}'
                })
                st.dataframe(styler_audit.map(color_profit_loss, subset=['Net Profit / Loss']) if hasattr(styler_audit, 'map') else styler_audit.applymap(color_profit_loss, subset=['Net Profit / Loss']), use_container_width=True, hide_index=True)
        else:
            st.warning("No completed financial data available to build margins.")

    # ---------------------------------------------------------
    # TAB 3: Geographic Performance (FIXED & AUDITED)
    # ---------------------------------------------------------
    with tab3:
        st.header("Geographic Profitability & Travel Time Analysis")
        
        # Fixed: Shifted to a safe Left Join with structural clean suffixes to prevent column name string drops
        if 'Related Invoices' in jobs_df.columns and '#ID' in invoices_df.columns:
            jobs_df['Related Invoices'] = jobs_df['Related Invoices'].astype(str).str.split('.').str[0].str.strip()
            invoices_df['#ID'] = invoices_df['#ID'].astype(str).str.split('.').str[0].str.strip()
            geo_df = pd.merge(jobs_df, invoices_df, left_on='Related Invoices', right_on='#ID', how='left', suffixes=('', '_invoice'))
        else:
            geo_df = jobs_df.copy()

        if 'Assigned Team Members' in geo_df.columns:
            geo_df = geo_df.dropna(subset=['Assigned Team Members'])

        # Sanitize and scrub messy string or decimal formatting artifacts out of Zip Code column values
        if 'Zip Code' in geo_df.columns:
            geo_df['Zip Code'] = geo_df['Zip Code'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            geo_df = geo_df[(geo_df['Zip Code'] != 'nan') & (geo_df['Zip Code'] != '') & (geo_df['Zip Code'] != 'None')]
            
        # Ensure data table layout executes conditionally only when geographical vectors are actually parsed
        if 'Zip Code' in geo_df.columns and not geo_df.empty:
            col3, col4 = st.columns(2)
            with col3:
                st.subheader("💰 Most Lucrative Zip Codes (Net Profit)")
                
                # Dynamic Fallback Protection: Use calculated labor profit if invoice-level profit margin column is empty
                profit_col = 'Profit Margin' if ('Profit Margin' in geo_df.columns and geo_df['Profit Margin'].sum() != 0) else 'Net Gross Profit'
                
                profit_by_zip = geo_df.groupby('Zip Code').agg(
                    Job_Count=('Zip Code', 'count'), 
                    Total_Net_Profit=(profit_col, 'sum'), 
                    Avg_Profit_Per_Job=(profit_col, 'mean')
                ).reset_index().sort_values('Total_Net_Profit', ascending=False)
                
                profit_by_zip.columns = ['Zip Code', 'Total Jobs', 'Total Net Profit', 'Avg Profit/Job']
                st.dataframe(profit_by_zip.style.format({'Total Net Profit': '${:,.2f}', 'Avg Profit/Job': '${:,.2f}'}), use_container_width=True, hide_index=True)
            
            with col4:
                st.subheader("🚗 Travel Efficiency by Zone")
                if 'Travel Duration Decimal' in geo_df.columns and 'Total Invoice Amount' in geo_df.columns:
                    travel_waste = geo_df.groupby('Zip Code').agg(
                        Job_Count=('Zip Code', 'count'), Avg_Travel_Hours=('Travel Duration Decimal', 'mean'), Avg_Invoice_Amount=('Total Invoice Amount', 'mean')
                    ).reset_index().sort_values('Avg_Travel_Hours', ascending=False)
                    
                    travel_waste.columns = ['Zip Code', 'Total Jobs', 'Avg Drive Time (H:MM)', 'Avg Ticket Size']
                    st.dataframe(travel_waste.style.format({'Avg Drive Time (H:MM)': format_hours_mins, 'Avg Ticket Size': '${:,.2f}'}), use_container_width=True, hide_index=True)
                else:
                    st.info("Travel tracking duration columns are missing or empty in this dataset upload window.")
        else:
            st.info("ℹ️ No active geographical location records or valid Zip Codes detected within this file range to map performance details.")
else:
    st.info("👋 Welcome! Please upload **all three** operational CSV exports in the sidebar to build your data tables.")
