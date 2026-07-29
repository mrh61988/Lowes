import streamlit as st
import pandas as pd
import numpy as np
import re

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & UI STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Operations & Profitability Audit Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .metric-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 8px;
        border-left: 5px solid #007bff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .variance-alert {
        color: #d9534f;
        font-weight: bold;
    }
    .success-alert {
        color: #28a745;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Operations & Profitability Dashboard")
st.markdown("Track contractor profitability, reconcile retail invoices, audit technician labor slippage, and ensure Lowe's contract compliance.")
st.markdown("---")

# -----------------------------------------------------------------------------
# 2. AUTOMATED GOOGLE SHEETS LIVE INGESTION ENGINE
# -----------------------------------------------------------------------------
URL_MATRIX_1 = "https://docs.google.com/spreadsheets/d/1SUsLlpsON_QdiFTf-kSo1TCMyuBfVoglrzdE5iMkpBU/export?format=csv&gid=0"
URL_MATRIX_2 = "https://docs.google.com/spreadsheets/d/11hlWb0q3o30ZfweZ-Czx92bcwpJPCBi_I4wC6eN5Mi8/export?format=csv&gid=1455402036"

@st.cache_data(ttl=3600)
def fetch_live_pricing_matrices(url1, url2):
    """Downloads the master pricing sheets directly from the Google Sheet cloud endpoints."""
    try:
        df_a = pd.read_csv(url1)
        df_b = pd.read_csv(url2)
        return df_a, df_b, None
    except Exception as e:
        return None, None, str(e)

st.sidebar.header("🔄 Cloud Matrix Status")
if st.sidebar.button("Force Refresh Master Pricing"):
    st.cache_data.clear()

df_sheet_1, df_sheet_2, download_error = fetch_live_pricing_matrices(URL_MATRIX_1, URL_MATRIX_2)

erik_matrix_df = None
bryan_matrix_df = None

if download_error:
    st.sidebar.error(f"❌ Cloud Sync Failed: {download_error}")
else:
    st.sidebar.success("⚡ Live Pricing Matrices Synced")
    content_dump_1 = str(df_sheet_1.columns.tolist()).lower() + str(df_sheet_1.head(5).values).lower()
    if "bryan" in content_dump_1 or "pickett" in content_dump_1:
        bryan_matrix_df = df_sheet_1
        erik_matrix_df = df_sheet_2
    else:
        erik_matrix_df = df_sheet_1
        bryan_matrix_df = df_sheet_2

# -----------------------------------------------------------------------------
# 3. ADVANCED MULTI-ITEM & QUANTITY PRICING ENGINE
# -----------------------------------------------------------------------------
def lookup_matrix_rate(row, tech_name, current_revenue, erik_mat, bryan_mat, mode="labor"):
    """
    Scans the job title for item order and maps them sequentially to slash 
    notation quantities in the subtitle.
    """
    job_title = str(row.get('Title', '')).lower()
    
    subtitle_col = next((c for c in row.index if 'subtitle' in str(c).lower() or 'description' in str(c).lower()), None)
    subtitle = str(row[subtitle_col]).lower().strip() if subtitle_col and pd.notna(row[subtitle_col]) else ""
    
    target_mat = None
    if "erik" in str(tech_name).lower() and erik_mat is not None:
        target_mat = erik_mat
    elif "bryan" in str(tech_name).lower() and bryan_mat is not None:
        target_mat = bryan_mat
        
    if target_mat is not None:
        item_col = target_mat.columns[0]
        inv_col = target_mat.columns[1]
        payout_col = target_mat.columns[2]
        
        found_keywords = []
        for _, m_row in target_mat.iterrows():
            keyword = str(m_row[item_col]).lower().strip()
            if not keyword:
                continue
            
            root_keyword = keyword[:-1] if keyword.endswith('s') else keyword
            idx = job_title.find(root_keyword)
            if idx != -1:
                try:
                    raw_rate = str(m_row[payout_col] if mode == "labor" else m_row[inv_col])
                    rate = float(re.sub(r'[^\d.]', '', raw_rate))
                except:
                    rate = 0.0
                found_keywords.append({
                    'index': idx, 'keyword': keyword, 'root': root_keyword, 'rate': rate
                })
                
        if found_keywords:
            found_keywords.sort(key=lambda x: x['index'])
            sub_quantities = [int(n) for n in re.findall(r'\d+', subtitle)]
            total_val = 0.0
            
            if len(found_keywords) == len(sub_quantities) and len(sub_quantities) > 0:
                for i, item in enumerate(found_keywords):
                    total_val += item['rate'] * sub_quantities[i]
                return total_val
            else:
                for item in found_keywords:
                    quantity = 1
                    pattern = rf"(\d+)?\s*{re.escape(item['root'])}"
                    title_matches = re.findall(pattern, job_title)
                    if title_matches and str(title_matches[0]).isdigit():
                        quantity = int(title_matches[0])
                        
                    total_val += item['rate'] * quantity
                return total_val

    if mode == "labor":
        if str(tech_name).strip() in ['Erik Tange', 'Bryan Pickett']:
            return current_revenue * 0.34
        return 0.0
    else:
        if 'toilet' in job_title: return 209.00
        if 'faucet' in job_title: return 135.00
        return current_revenue

# -----------------------------------------------------------------------------
# 4. SIDEBAR UPLOAD CONTROL CENTER
# -----------------------------------------------------------------------------
st.sidebar.header("📁 Upload Operational Datasets")
uploaded_jobs = st.sidebar.file_uploader("Upload Jobs Full Data CSV", type=["csv"])
uploaded_invoices = st.sidebar.file_uploader("Upload Invoices CSV", type=["csv"])
uploaded_timesheets = st.sidebar.file_uploader("Upload Timesheets CSV", type=["csv"])

def sanitize_currency_series(series):
    cleaned = series.astype(str).str.replace(r'[^\d.-]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce').fillna(0.0)

# --- RESILIENT AUTOMATIC COLUMN SCANNING ENGINE ---
def auto_map_column(keys, columns, exclude_keys=None):
    columns_lower = [c.lower() for c in columns]
    # Priority 1: Direct exact match match
    for k in keys:
        if k in columns_lower:
            return columns[columns_lower.index(k)]
    # Priority 2: Safe contextual wildcard match (excludes tracking codes/IDs)
    for k in keys:
        for col in columns:
            col_lower = col.lower()
            if k in col_lower:
                if exclude_keys and any(ex in col_lower for ex in exclude_keys):
                    continue
                return col
    # Priority 3: Global fallback matching
    for k in keys:
        for col in columns:
            if k in col.lower():
                return col
    return columns[0]

# -----------------------------------------------------------------------------
# 5. DATA PROCESSING & INGESTION RECONCILIATION
# -----------------------------------------------------------------------------
if uploaded_jobs and uploaded_invoices and uploaded_timesheets:
    
    df_jobs = pd.read_csv(uploaded_jobs)
    df_invoices = pd.read_csv(uploaded_invoices)
    df_timesheets = pd.read_csv(uploaded_timesheets)
    
    df_jobs.columns = [c.strip() for c in df_jobs.columns]
    df_invoices.columns = [c.strip() for c in df_invoices.columns]
    df_timesheets.columns = [c.strip() for c in df_timesheets.columns]
    
    job_cols = list(df_jobs.columns)

    # Automatically map fields behind the scenes cleanly
    chosen_rev = auto_map_column(['revenue', 'invoice total', 'amount', 'total', 'gross', 'price', 'billed'], job_cols)
    chosen_tech = auto_map_column(['technician', 'lead tech', 'resource', 'employee', 'worker', 'name', 'tech'], job_cols, exclude_keys=['id', '#', 'num'])
    chosen_bu = auto_map_column(['business unit', 'department', 'bu', 'stream', 'category', 'type'], job_cols)
    chosen_id = auto_map_column(['job id', 'ticket number', 'ticket', 'job #', 'id', 'wo', 'work order'], job_cols)
    chosen_mat = auto_map_column(['materials', 'material cost', 'parts', 'supply', 'expense'], job_cols)
    chosen_title = auto_map_column(['title', 'job title', 'summary', 'description'], job_cols)

    # Commit structural mappings & sanitize pricing inputs
    df_jobs['Revenue'] = sanitize_currency_series(df_jobs[chosen_rev])
    df_jobs['Technician'] = df_jobs[chosen_tech].fillna('Unknown Tech').astype(str)
    df_jobs['Business Unit'] = df_jobs[chosen_bu].fillna('General').astype(str)
    df_jobs['Job ID'] = df_jobs[chosen_id].astype(str)
    df_jobs['Materials'] = sanitize_currency_series(df_jobs[chosen_mat])
    df_jobs['Title'] = df_jobs[chosen_title].fillna('').astype(str)

    # WRENCH TIME TIMESTAMP ENGINE
    otw_col = next((c for c in df_jobs.columns if 'way' in c.lower() or 'otw' in c.lower()), None)
    store_col = next((c for c in df_jobs.columns if 'store' in c.lower() or 'lowes' in c.lower()), None)
    prog_col = next((c for c in df_jobs.columns if 'progress' in c.lower() or 'started' in c.lower()), None)
    audit_col = next((c for c in df_jobs.columns if 'audit' in c.lower() or 'pending' in c.lower() or 'complete' in c.lower()), None)

    def calculate_wrench_hours(row):
        try:
            times = []
            for col in [otw_col, store_col, prog_col]:
                if col and pd.notna(row[col]):
                    times.append(pd.to_datetime(row[col]))
            
            if not times or not audit_col or pd.isna(row[audit_col]):
                return 2.0  
                
            start_time = min(times)
            end_time = pd.to_datetime(row[audit_col])
            duration = (end_time - start_time).total_seconds() / 3600.0
            return max(0.1, duration)
        except:
            return 2.0

    df_jobs['Calculated Wrench Hours'] = df_jobs.apply(calculate_wrench_hours, axis=1)

    # Date ranges scale engine
    date_col = next((c for c in df_jobs.columns if 'date' in c.lower()), None)
    if date_col:
        df_jobs[date_col] = pd.to_datetime(df_jobs[date_col], errors='coerce')
        min_date = df_jobs[date_col].min()
        max_date = df_jobs[date_col].max()
        if pd.notna(min_date) and pd.notna(max_date):
            days_span = (max_date - min_date).days
            detected_weeks = max(1, int(np.ceil(days_span / 7)))
        else:
            detected_weeks = 1
    else:
        detected_weeks = 1
        
    st.sidebar.info(f"📆 Auto-Detected Span: **{detected_weeks} week(s)**.")

    # -----------------------------------------------------------------------------
    # FINANCIAL LABORS EXPANSION LOGIC
    # -----------------------------------------------------------------------------
    def calculate_job_metrics(row):
        tech = str(row['Technician']).strip()
        biz_unit = str(row['Business Unit']).lower()
        revenue = float(row['Revenue'])
        job_id = str(row['Job ID'])
        
        is_exception_stream = any(ex in job_id.upper() for ex in ['LA', 'PA', 'RA'])
        lowes_cut = 0.0
        if 'water heater' in biz_unit and not is_exception_stream:
            lowes_cut = revenue * 0.15
            
        net_revenue = revenue - lowes_cut
        
        labor_cost = 0.0
        if tech in ['Erik Tange', 'Bryan Pickett']:
            calculated_payout = lookup_matrix_rate(row, tech, revenue, erik_matrix_df, bryan_matrix_df, mode="labor")
            labor_cost = calculated_payout if calculated_payout is not None else (revenue * 0.34)
        elif 'hourly' in biz_unit or any(n in tech.lower() for n in ['matt', 'tanner', 'edward']):
            labor_cost = float(row['Calculated Wrench Hours']) * 25.0  
        elif 'salary' in biz_unit or any(n in tech.lower() for n in ['sean', 'mathew']):
            weekly_salary_burden = 1200.00 
            total_jobs_by_tech = len(df_jobs[df_jobs['Technician'] == tech])
            labor_cost = (weekly_salary_burden * detected_weeks) / max(1, total_jobs_by_tech)
        else:
            labor_cost = revenue * 0.30  
            
        material_cost = float(row['Materials'])
        gross_profit = net_revenue - labor_cost - material_cost
        
        return pd.Series([lowes_cut, net_revenue, labor_cost, gross_profit])

    df_jobs[['Lowes Cut', 'Net Revenue', 'Calculated Labor', 'Gross Profit']] = df_jobs.apply(calculate_job_metrics, axis=1)

    # -----------------------------------------------------------------------------
    # 6. INTERACTIVE AUDITING WORKSPACE (RESTORED MULTI-TAB VIEW)
    # -----------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Executive Dashboard Overview", 
        "🏷️ Simple Installs & Invoice Audit", 
        "⏱️ Wrench Time & Payroll Slippage Log",
        "🛒 Lowe's 15% Margin Cut Reconciliation"
    ])

    # TAB 1: EXECUTIVE DASHBOARD OVERVIEW
    with tab1:
        st.subheader("Key Business Unit Performance Metrics")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        tot_rev = df_jobs['Revenue'].sum()
        tot_net = df_jobs['Net Revenue'].sum()
        tot_lab = df_jobs['Calculated Labor'].sum()
        tot_mat = df_jobs['Materials'].sum()
        tot_prof = df_jobs['Gross Profit'].sum()
        
        col1.metric("Total Gross Revenue", f"${tot_rev:,.2f}")
        col2.metric("Net Revenue (Post-Cut)", f"${tot_net:,.2f}")
        col3.metric("Calculated Labor Cost", f"${tot_lab:,.2f}")
        col4.metric("Material Cost Expenses", f"${tot_mat:,.2f}")
        col5.metric("Estimated Gross Profit", f"${tot_prof:,.2f}")
        
        st.markdown("---")
        st.subheader("Profitability Breakdown by Working Technician")
        
        tech_summary = df_jobs.groupby('Technician').agg(
            Jobs_Completed=('Job ID', 'count'),
            Gross_Revenue=('Revenue', 'sum'),
            Net_Revenue=('Net Revenue', 'sum'),
            Labor_Cost=('Calculated Labor', 'sum'),
            Material_Cost=('Materials', 'sum'),
            Net_Profit=('Gross Profit', 'sum')
        ).reset_index()
        
        tech_summary['Profit Margin'] = (tech_summary['Net_Profit'] / tech_summary['Net_Revenue'].replace(0, np.nan)).fillna(0) * 100
        
        st.dataframe(
            tech_summary.style.format({
                'Gross_Revenue': '${:,.2f}', 'Net_Revenue': '${:,.2f}', 
                'Labor_Cost': '${:,.2f}', 'Material_Cost': '${:,.2f}', 
                'Net_Profit': '${:,.2f}', 'Profit Margin': '{:.1f}%'
            }),
            use_container_width=True
        )

        st.markdown("---")
        st.subheader("Business Unit Performance Breakdown")
        bu_summary = df_jobs.groupby('Business Unit').agg(
            Total_Tickets=('Job ID', 'count'),
            Total_Gross=('Revenue', 'sum'),
            Total_Net=('Net Revenue', 'sum'),
            Total_Labor=('Calculated Labor', 'sum'),
            Estimated_Profit=('Gross Profit', 'sum')
        ).reset_index()
        st.dataframe(bu_summary.style.format({
            'Total_Gross': '${:,.2f}', 'Total_Net': '${:,.2f}', 
            'Total_Labor': '${:,.2f}', 'Estimated_Profit': '${:,.2f}'
        }), use_container_width=True)

    # TAB 2: SIMPLE INSTALLS & INVOICE AUDIT
    with tab2:
        st.subheader("Simple Installs Matrix Pricing Verification Table")
        st.markdown("Validates every ticket against master pricing sheets to check for invoice and billing accuracy.")
        
        audit_records = []
        for idx, row in df_jobs.iterrows():
            tech = row['Technician']
            actual_inv = float(row['Revenue'])
            
            expected_inv = lookup_matrix_rate(row, tech, actual_inv, erik_matrix_df, bryan_matrix_df, mode="invoice")
            variance = actual_inv - expected_inv
            
            audit_records.append({
                'Job ID': row['Job ID'],
                'Technician': tech,
                'Job Title': row['Title'],
                'Billed Amount': actual_inv,
                'Matrix Expected Amount': expected_inv,
                'Invoice Variance': variance,
                'Compliance Status': "⚠️ MISMATCH" if abs(variance) > 0.01 else "✅ MATCH"
            })
            
        df_audit = pd.DataFrame(audit_records)
        st.dataframe(
            df_audit.style.format({
                'Billed Amount': '${:,.2f}', 'Matrix Expected Amount': '${:,.2f}', 'Invoice Variance': '${:,.2f}'
            }),
            use_container_width=True
        )
        
        mismatches = df_audit[df_audit['Compliance Status'] == "⚠️ MISMATCH"]
        if not mismatches.empty:
            st.error(f"⚠️ Found **{len(mismatches)} invoice pricing variances** requiring manual billing review.")
        else:
            st.success("🎉 All operational items perfectly match agreed pricing matrix baselines!")

    # TAB 3: WRENCH TIME & PAYROLL SLIPPAGE LOG
    with tab3:
        st.subheader("Wrench Time vs. Clocked Timesheet Alignment Workspace")
        st.markdown("Aggregates dynamic customer ticket interaction time frames (OTW to Audit) against logged timesheets.")
        
        tech_wrench = df_jobs.groupby('Technician')['Calculated Wrench Hours'].sum().reset_index()
        
        ts_tech_col = next((c for c in df_timesheets.columns if 'tech' in c.lower() or 'name' in c.lower() or 'employee' in c.lower()), None)
        ts_clock_col = next((c for c in df_timesheets.columns if 'clock' in c.lower() or 'total' in c.lower() or 'hours' in c.lower()), None)
        
        if ts_tech_col and ts_clock_col:
            df_timesheets['Cleaned Clock Hours'] = sanitize_currency_series(df_timesheets[ts_clock_col])
            ts_summary = df_timesheets.groupby(ts_tech_col)['Cleaned Clock Hours'].sum().reset_index()
            
            df_merge = pd.merge(tech_wrench, ts_summary, left_on='Technician', right_on=ts_tech_col, how='outer').fillna(0.0)
            df_merge['Labor Slippage (Hours)'] = df_merge['Cleaned Clock Hours'] - df_merge['Calculated Wrench Hours']
            df_merge['Unproductive Payroll Exposure'] = df_merge['Labor Slippage (Hours)'].apply(lambda x: max(0, x) * 25.00)
            
            st.markdown("#### Integrated Labor Leakage Ledger")
            st.dataframe(
                df_merge[['Technician', 'Calculated Wrench Hours', 'Cleaned Clock Hours', 'Labor Slippage (Hours)', 'Unproductive Payroll Exposure']].style.format({
                    'Calculated Wrench Hours': '{:.2f} hrs', 'Cleaned Clock Hours': '{:.2f} hrs',
                    'Labor Slippage (Hours)': '{:.2f} hrs', 'Unproductive Payroll Exposure': '${:,.2f}'
                }),
                use_container_width=True
            )
            
            tot_leakage = df_merge['Unproductive Payroll Exposure'].sum()
            st.metric("Total Unproductive Payroll Exposure", f"${tot_leakage:,.2f}", delta=f"{df_merge['Labor Slippage (Hours)'].sum():.1f} Lost Hrs", delta_color="inverse")
        else:
            st.warning("Could not automatically map matching Technician/Hours inside your `timesheets.csv` file.")
            st.dataframe(tech_wrench)

    # TAB 4: LOWE'S 15% MARGIN CUT RECONCILIATION
    with tab4:
        st.subheader("Lowe's 15% Contractor Margin Deduction Audit Ledger")
        st.markdown("Monitors standard Water Heater lines subject to standard 15% retainage while verifying exception rules (**LA, PA, RA**).")
        
        reconciliation_records = []
        applied_cut_col = next((c for c in df_jobs.columns if 'deducted' in c.lower() or 'lowes cut' in c.lower() or 'retainage' in c.lower()), None)
        
        for idx, row in df_jobs.iterrows():
            job_id = str(row['Job ID'])
            biz_unit = str(row['Business Unit']).lower()
            gross_rev = float(row['Revenue'])
            is_exception = any(ex in job_id.upper() for ex in ['LA', 'PA', 'RA'])
            
            if 'water heater' in biz_unit:
                expected_cut = 0.0 if is_exception else (gross_rev * 0.15)
                actual_cut_applied = float(row[applied_cut_col]) if (applied_cut_col and pd.notna(row[applied_cut_col])) else expected_cut
                variance = actual_cut_applied - expected_cut
                
                reconciliation_records.append({
                    'Job ID': job_id,
                    'Technician': row['Technician'],
                    'Work Stream Category': "Exception Stream (Exempt)" if is_exception else "Standard Water Heater",
                    'Gross Revenue': gross_rev,
                    'Expected 15% Cut': expected_cut,
                    'Applied Margin Cut': actual_cut_applied,
                    'Audit Variance': variance,
                    'Status Flag': "✅ Pass" if abs(variance) < 0.01 else "❌ Reconcile"
                })
                
        if reconciliation_records:
            df_rec = pd.DataFrame(reconciliation_records)
            st.dataframe(
                df_rec.style.format({
                    'Gross Revenue': '${:,.2f}', 'Expected 15% Cut': '${:,.2f}', 
                    'Applied Margin Cut': '${:,.2f}', 'Audit Variance': '${:,.2f}'
                }),
                use_container_width=True
            )
            
            errors = len(df_rec[df_rec['Status Flag'] == "❌ Reconcile"])
            if errors > 0:
                st.error(f"⚠️ Flagged **{errors} Lowe's compliance variances** due to incorrect exception processing.")
            else:
                st.success("🎉 Contract compliance checks verified: All margin cuts match exceptions perfectly.")
        else:
            st.info("No active 'Water Heater' business unit records found in the current uploaded file.")

else:
    st.info("💡 **Welcome to the Workspace Setup:** Please drop your working operational data exports (`jobs`, `invoices`, `timesheets`) into the sidebar panel to activate full dashboard computations. Master contractor pricing profiles are already live-connected to Google Drive.")
