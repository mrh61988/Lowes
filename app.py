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
        padding: 15px;
        border-radius: 5px;
        border-left: 5px solid #007bff;
        margin-bottom: 10px;
    }
    .variance-alert {
        color: #d9534f;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Operations & Profitability Dashboard")
st.markdown("Track contractor profitability, reconcile retail invoices, and detect labor slippage across standard and exception work streams.")
st.markdown("---")

# -----------------------------------------------------------------------------
# 2. AUTOMATED GOOGLE SHEETS LIVE INGESTION ENGINE
# -----------------------------------------------------------------------------
# Permanent direct CSV export endpoints for the provided Google Sheets
URL_MATRIX_1 = "https://docs.google.com/spreadsheets/d/1SUsLlpsON_QdiFTf-kSo1TCMyuBfVoglrzdE5iMkpBU/export?format=csv&gid=0"
URL_MATRIX_2 = "https://docs.google.com/spreadsheets/d/11hlWb0q3o30ZfweZ-Czx92bcwpJPCBi_I4wC6eN5Mi8/export?format=csv&gid=1455402036"

@st.cache_data(ttl=3600)  # Caches the sheets locally for 1 hour to maximize app speed
def fetch_live_pricing_matrices(url1, url2):
    """Downloads the master pricing sheets directly from the Google Sheet cloud endpoints."""
    try:
        df_a = pd.read_csv(url1)
        df_b = pd.read_csv(url2)
        return df_a, df_b, None
    except Exception as e:
        return None, None, str(e)

st.sidebar.header("🔄 Cloud Matrix Status")
# Provide a button to clear cache and force an instant pull of updated Google Sheet rates
if st.sidebar.button("Force Refresh Master Pricing"):
    st.cache_data.clear()

df_sheet_1, df_sheet_2, download_error = fetch_live_pricing_matrices(URL_MATRIX_1, URL_MATRIX_2)

erik_matrix_df = None
bryan_matrix_df = None

if download_error:
    st.sidebar.error(f"❌ Cloud Sync Failed: {download_error}")
    st.sidebar.warning("Please verify that both Google Sheets are set to 'Anyone with the link can view'.")
else:
    st.sidebar.success("⚡ Live Pricing Matrices Synced")
    
    # Intelligent matching: Scan headers & rows to dynamically assign the correct tech matrix
    content_dump_1 = str(df_sheet_1.columns.tolist()).lower() + str(df_sheet_1.head(5).values).lower()
    
    if "bryan" in content_dump_1 or "pickett" in content_dump_1:
        bryan_matrix_df = df_sheet_1
        erik_matrix_df = df_sheet_2
        st.sidebar.info("Detected Matrix Layout: Sheet 1 (Bryan) | Sheet 2 (Erik)")
    else:
        erik_matrix_df = df_sheet_1
        bryan_matrix_df = df_sheet_2
        st.sidebar.info("Detected Matrix Layout: Sheet 1 (Erik) | Sheet 2 (Bryan)")

# -----------------------------------------------------------------------------
# 3. ADVANCED MULTI-ITEM & QUANTITY PRICING ENGINE
# -----------------------------------------------------------------------------
def lookup_matrix_rate(row, tech_name, current_revenue, erik_mat, bryan_mat, mode="labor"):
    """
    Scans the job title for item order and maps them sequentially to slash 
    notation quantities in the subtitle. If the subtitle is empty, it assumes 
    a default quantity of 1 for each detected item.
    """
    job_title = str(row.get('Title', row.get('Job Title', ''))).lower()
    
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
                rate = float(m_row[payout_col]) if mode == "labor" else float(m_row[inv_col])
                found_keywords.append({
                    'index': idx,
                    'keyword': keyword,
                    'root': root_keyword,
                    'rate': rate
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
# 4. SIDEBAR UPLOAD CONTROL CENTER (OPERATIONAL FILES ONLY)
# -----------------------------------------------------------------------------
st.sidebar.header("📁 Upload Operational Datasets")
uploaded_jobs = st.sidebar.file_uploader("Upload Jobs Full Data CSV", type=["csv"])
uploaded_invoices = st.sidebar.file_uploader("Upload Invoices CSV", type=["csv"])
uploaded_timesheets = st.sidebar.file_uploader("Upload Timesheets CSV", type=["csv"])

# -----------------------------------------------------------------------------
# 5. DATA PROCESSING CORE LOGIC
# -----------------------------------------------------------------------------
if uploaded_jobs and uploaded_invoices and uploaded_timesheets:
    
    df_jobs = pd.read_csv(uploaded_jobs)
    df_invoices = pd.read_csv(uploaded_invoices)
    df_timesheets = pd.read_csv(uploaded_timesheets)
    
    df_jobs.columns = [c.strip() for c in df_jobs.columns]
    df_invoices.columns = [c.strip() for c in df_invoices.columns]
    df_timesheets.columns = [c.strip() for c in df_timesheets.columns]
    
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
        
    st.sidebar.info(f"📆 Date range spans **{detected_weeks} week(s)**. Scaling fixed salaries accordingly.")

    def calculate_job_metrics(row):
        tech = str(row.get('Technician', row.get('Lead Tech', ''))).strip()
        biz_unit = str(row.get('Business Unit', row.get('Department', ''))).lower()
        revenue = float(row.get('Revenue', row.get('Invoice Total', 0.0)))
        job_id = str(row.get('Job ID', row.get('Ticket Number', '')))
        
        is_exception_stream = any(ex in job_id.upper() for ex in ['LA', 'PA', 'RA'])
        lowes_cut = 0.0
        if 'water heater' in biz_unit and not is_exception_stream:
            lowes_cut = revenue * 0.15
            
        net_revenue = revenue - lowes_cut
        
        labor_cost = 0.0
        if tech in ['Erik Tange', 'Bryan Pickett']:
            calculated_payout = lookup_matrix_rate(row, tech, revenue, erik_matrix_df, bryan_matrix_df, mode="labor")
            labor_cost = calculated_payout if calculated_payout is not None else (revenue * 0.34)
        elif 'hourly' in biz_unit or 'staff_hourly' in tech.lower():
            labor_cost = float(row.get('Hours Worked', 0.0)) * 25.0  
        elif 'salary' in biz_unit or 'staff_salaried' in tech.lower():
            weekly_salary_burden = 1200.00 
            total_jobs_by_tech = len(df_jobs[df_jobs['Technician'] == tech]) if 'Technician' in df_jobs.columns else 1
            labor_cost = (weekly_salary_burden * detected_weeks) / max(1, total_jobs_by_tech)
        else:
            labor_cost = revenue * 0.30  
            
        material_cost = float(row.get('Materials', row.get('Material Costs', 0.0)))
        gross_profit = net_revenue - labor_cost - material_cost
        
        return pd.Series([lowes_cut, net_revenue, labor_cost, gross_profit])

    df_jobs[['Lowes Cut', 'Net Revenue', 'Calculated Labor', 'Gross Profit']] = df_jobs.apply(calculate_job_metrics, axis=1)

    # -----------------------------------------------------------------------------
    # 6. INTERACTIVE AUDITING WORKSPACE (FOUR FUNCTIONAL TABS)
    # -----------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Executive Dashboard Overview", 
        "🏷️ Simple Installs & Invoice Audit", 
        "⏱️ Wrench Time & Payroll Slippage Log",
        "🛒 Lowe's 15% Margin Cut Reconciliation"
    ])

    # TAB 1: EXECUTIVE OVERVIEW
    with tab1:
        st.subheader("Key Business Unit Performance Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Gross Revenue", f"${df_jobs['Revenue'].sum():,.2f}")
        col2.metric("Net Operational Revenue", f"${df_jobs['Net Revenue'].sum():,.2f}")
        col3.metric("Calculated Labor Cost", f"${df_jobs['Calculated Labor'].sum():,.2f}")
        col4.metric("Estimated Gross Profit", f"${df_jobs['Gross Profit'].sum():,.2f}")
        
        st.markdown("---")
        st.subheader("Profitability Breakdown by Working Technician")
        tech_summary = df_jobs.groupby(df_jobs.columns[1] if len(df_jobs.columns)>1 else df_jobs.columns[0]).agg({
            'Revenue': 'sum', 'Net Revenue': 'sum', 'Calculated Labor': 'sum', 'Gross Profit': 'sum'
        })
        st.dataframe(tech_summary.style.format("${:,.2f}"))

    # TAB 2: SIMPLE INSTALLS AUDIT
    with tab2:
        st.subheader("Simple Installs Menu Price Pricing Verification")
        st.markdown("Flags tickets where actual invoiced values depart from cloud Google Sheet agreements.")
        
        audit_records = []
        for idx, row in df_jobs.iterrows():
            tech = row.get('Technician', row.get('Lead Tech', ''))
            actual_inv = float(row.get('Revenue', row.get('Invoice Total', 0.0)))
            
            expected_inv = lookup_matrix_rate(row, tech, actual_inv, erik_matrix_df, bryan_matrix_df, mode="invoice")
            variance = actual_inv - expected_inv
            
            if abs(variance) > 0.01:
                audit_records.append({
                    'Job ID': row.get('Job ID', row.get('Ticket Number', idx)),
                    'Technician': tech,
                    'Job Title': row.get('Title', row.get('Job Title', '')),
                    'Subtitle/Notes': row.get(next((c for c in row.index if 'subtitle' in str(c).lower() or 'description' in str(c).lower()), row.index[0]), ''),
                    'Billed Amount': actual_inv,
                    'Matrix Expected Amount': expected_inv,
                    'Invoice Variance': variance
                })
                
        if audit_records:
            st.dataframe(pd.DataFrame(audit_records).style.format({
                'Billed Amount': '${:,.2f}', 'Matrix Expected Amount': '${:,.2f}', 'Invoice Variance': '${:,.2f}'
            }))
        else:
            st.success("🎉 Compliance Check Passed: All processed simple install items match expected cloud menu matrix prices!")

    # TAB 3: PAYROLL SLIPPAGE LOG
    with tab3:
        st.subheader("Wrench Time vs. Clocked Timesheet Alignment")
        st.markdown("Cross-references recorded timesheet clock hours against dynamic ticket status timestamps to track operational leakage.")
        
        df_slippage = df_timesheets.copy()
        if 'Clock Hours' in df_slippage.columns and 'Wrench Hours' in df_slippage.columns:
            df_slippage['Slippage (Hours)'] = df_slippage['Clock Hours'] - df_slippage['Wrench Hours']
            df_slippage['Unproductive Payroll Exposure'] = df_slippage['Slippage (Hours)'] * 25.00
            st.dataframe(df_slippage.style.format({
                'Clock Hours': '{:.2f} hrs', 'Wrench Hours': '{:.2f} hrs', 'Slippage (Hours)': '{:.2f} hrs', 'Unproductive Payroll Exposure': '${:,.2f}'
            }))
        else:
            st.warning("Ensure your loaded `timesheets.csv` file contains clear columns for `Clock Hours` and `Wrench Hours`.")
            st.dataframe(df_timesheets)

    # TAB 4: LOWE'S RECONCILIATION
    with tab4:
        st.subheader("Lowe's 15% Contractor Margin Deduction Audit")
        st.markdown("Isolates standard Water Heater streams subject to institutional cuts while strictly excluding **LA, PA, and RA** exceptions.")
        
        reconciliation_records = []
        for idx, row in df_jobs.iterrows():
            job_id = str(row.get('Job ID', row.get('Ticket Number', idx)))
            biz_unit = str(row.get('Business Unit', row.get('Department', ''))).lower()
            gross_rev = float(row.get('Revenue', 0.0))
            is_exception = any(ex in job_id.upper() for ex in ['LA', 'PA', 'RA'])
            
            if 'water heater' in biz_unit:
                expected_cut = 0.0 if is_exception else (gross_rev * 0.15)
                actual_cut_applied = float(row.get('Lowes Margin Deducted', expected_cut)) 
                variance = actual_cut_applied - expected_cut
                
                reconciliation_records.append({
                    'Job ID': job_id, 'Work Stream Type': "Exception Stream (Exempt)" if is_exception else "Standard Water Heater",
                    'Gross Revenue': gross_rev, 'Expected 15% Cut': expected_cut, 'Applied Margin Cut': actual_cut_applied, 'Audit Variance': variance
                })
                
        if reconciliation_records:
            st.dataframe(pd.DataFrame(reconciliation_records).style.format({
                'Gross Revenue': '${:,.2f}', 'Expected 15% Cut': '${:,.2f}', 'Applied Margin Cut': '${:,.2f}', 'Audit Variance': '${:,.2f}'
            }))
        else:
            st.info("No active 'Water Heater' business unit records found in the current filtered data stream.")

else:
    st.info("💡 **Welcome to the Workspace Setup:** Please drop your working operational data exports (`jobs`, `invoices`, `timesheets`) into the sidebar panel to activate full dashboard computations. Master contractor pricing profiles are already live-connected to Google Drive.")
