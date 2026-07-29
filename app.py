import streamlit as st
import pandas as pd
import numpy as np

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
# LABOUR COST CALCULATION ENGINE (JOB TICKETS)
# ---------------------------------------------------------
def calculate_job_labor_cost(row):
    tech = str(row['Assigned Team Members'])
    duration = row['Job Duration Decimal']
    revenue = row['Total Invoice Amount']
    bu = str(row['Business Unit'])
    
    if pd.isna(duration): duration = 0.0
    if pd.isna(revenue): revenue = 0.0
    
    # Internal Salaried Staff (High-level allocation for job rows)
    if tech == 'Sean Marble':
        return duration * (70000 / 2080)
    elif tech == 'Mathew Hodges':
        return duration * (65000 / 2080)
        
    # Internal Hourly Staff ($25/hr baseline for individual tickets)
    elif tech in ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']:
        return duration * 25.00
        
    # Internal Commission Staff (34% of Revenue)
    elif tech in ['Erik Tange', 'Bryan Pickett']:
        return revenue * 0.34
        
    # External Contractors Engine
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
    
    # Base material cost calculation from fields
    base_mat = row['Invoice - Total Product Cost'] + row['Invoice - Total Service Cost']
    
    # Detect Contractor Status
    is_contractor = any(k in tech for k in ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian'])
    
    if is_contractor:
        # Rule 1: No materials costs for contractors on Simple Installs
        if 'simple installs' in bu:
            return 0.00
        # Rule 2: Hardcoded $650 material override for contractors on Water Heaters
        elif 'water heaters' in bu:
            return 650.00
        return base_mat
    else:
        # Internal crews rules: Deduct $125 built-in labor cushion from Water Heater jobs
        if 'water heaters' in bu:
            return max(0.00, base_mat - 125.00)
        return base_mat

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
    
    # Clean Timesheet Numeric Fields
    if 'Duration Decimal' in timesheets_df.columns:
        timesheets_df['Duration Decimal'] = pd.to_numeric(timesheets_df['Duration Decimal'], errors='coerce').fillna(0.0)
    
    # Filter Business Units
    if 'Business Unit' in raw_jobs_df.columns:
        jobs_df = raw_jobs_df[
            raw_jobs_df['Business Unit'].str.contains('Water Heaters|Simple Installs', case=False, na=False)
        ].copy()
    else:
        jobs_df = raw_jobs_df.copy()

    # Multi-Tech Primary Attribution
    if 'Assigned Team Members' in jobs_df.columns:
        jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].astype(str).str.split(',').str[0].str.strip()
        jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].replace(['nan', 'None', ''], None)

    # Clean numeric fields
    numeric_cols_jobs = ['Total Invoice Amount', 'Job Duration Decimal', 'Travel Duration Decimal', 
                         'Invoice - Total Product Cost', 'Invoice - Total Service Cost']
    for col in numeric_cols_jobs:
        if col in jobs_df.columns:
            jobs_df[col] = pd.to_numeric(jobs_df[col], errors='coerce').fillna(0.0)
            
    if 'Start Date' in jobs_df.columns:
        jobs_df['Start Date'] = pd.to_datetime(jobs_df['Start Date'], errors='coerce')

    if 'Profit Margin' in invoices_df.columns:
        invoices_df['Profit Margin'] = pd.to_numeric(invoices_df['Profit Margin'], errors='coerce').fillna(0.0)

    # Apply Engines
    jobs_df['Labor Cost'] = jobs_df.apply(calculate_job_labor_cost, axis=1)
    jobs_df['Material Cost'] = jobs_df.apply(calculate_job_material_cost, axis=1)
    jobs_df['Net Gross Profit'] = jobs_df['Total Invoice Amount'] - jobs_df['Material Cost'] - jobs_df['Labor Cost']

    # Initialize Interface Tabs
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
                st.subheader("📋 Volume & Speed by Technician / Contractor")
                tech_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                    Total_Jobs_Completed=('Status', 'count'),
                    Avg_Duration_Hours=('Job Duration Decimal', 'mean'),
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
                    Avg_Duration_Hours=('Job Duration Decimal', 'mean'),
                    Avg_Revenue_Per_Job=('Total Invoice Amount', 'mean'),
                    Total_Revenue=('Total Invoice Amount', 'sum')
                ).reset_index().sort_values('Job_Count', ascending=False)
                
                job_mix.columns = ['Job Title / Type', 'Volume Done', 'Avg Time Spent (H:MM)', 'Avg Ticket Size', 'Total Revenue']
                st.dataframe(job_mix.style.format({
                    'Avg Time Spent (H:MM)': format_hours_mins, 'Avg Ticket Size': '${:,.2f}', 'Total Revenue': '${:,.2f}'
                }), use_container_width=True, hide_index=True)
            
            st.write("---")
            
            # ---------------------------------------------------------
            # FIXED TABLE: CLOCK HOURS VS TICKET HOURS AUDITING LOG
            # ---------------------------------------------------------
            st.subheader("⏰ Clock Hours vs. Ticket Hours Auditing Log")
            st.write("Exposes unallocated time by contrasting total clocked timesheet hours against direct billable job durations.")
            
            ts_totals_audit = timesheets_df.groupby('User')['Duration Decimal'].sum().reset_index()
            all_unique_techs = completed_jobs['Assigned Team Members'].unique()
            
            utilization_records = []
            for tech in all_unique_techs:
                j_hours = completed_jobs[completed_jobs['Assigned Team Members'] == tech]['Job Duration Decimal'].sum()
                ts_match = ts_totals_audit[ts_totals_audit['User'] == tech]
                ts_hours = ts_match['Duration Decimal'].values[0] if not ts_match.empty else 0.0
                unallocated = max(0.0, ts_hours - j_hours)
                
                is_hourly = tech in ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']
                waste_cost = unallocated * 25.00 if is_hourly else 0.0
                
                utilization_records.append({
                    'Tech Name': tech,
                    'Paid Clock Hours (Timesheets)': ts_hours,
                    'On-Ticket Hours (Jobs)': j_hours,
                    'Unallocated Variance (Hours)': unallocated,
                    'Hourly Payroll Slippage': waste_cost if is_hourly else np.nan
                })
                
            utilization_df = pd.DataFrame(utilization_records).sort_values(by='Unallocated Variance (Hours)', ascending=False)
            
            # Formatted using na_rep='-' to cleanly display non-hourly rows without crashing
            styler_utilization = utilization_df.style.format({
                'Paid Clock Hours (Timesheets)': '{:.2f} hrs',
                'On-Ticket Hours (Jobs)': '{:.2f} hrs',
                'Unallocated Variance (Hours)': '{:.2f} hrs',
                'Hourly Payroll Slippage': '${:,.2f}'
            }, na_rep='-')
            
            st.dataframe(styler_utilization, use_container_width=True, hide_index=True)
        else:
            st.warning("No 'Completed' status jobs found.")

    # ---------------------------------------------------------
    # TAB 2: Financial & Labor ROI Metrics
    # ---------------------------------------------------------
    with tab2:
        st.header("Financial Performance & Labor Cost Analysis")
        
        if not completed_jobs.empty:
            st.subheader("📊 Aggregate Team Efficiency")
            st.write("Hourly employee labor is drawn directly from **Timesheets** at **$25.00/hr**, matching actual cash outflows.")
            
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
                return row['Total_Labor_Cost_Jobs']
            
            fin_metrics['Labor Cost Burden'] = fin_metrics.apply(determine_true_labor, axis=1)
            fin_metrics['Net Gross Profit'] = fin_metrics['Total_Revenue'] - fin_metrics['Total_Material_Cost'] - fin_metrics['Labor Cost Burden']
            
            revenue_minus_materials = fin_metrics['Total_Revenue'] - fin_metrics['Total_Material_Cost']
            fin_metrics['Labor % of Rev Less Mats'] = (fin_metrics['Labor Cost Burden'] / revenue_minus_materials) * 100
            fin_metrics['Labor % of Rev Less Mats'] = fin_metrics['Labor % of Rev Less Mats'].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            
            fin_metrics_display = fin_metrics[['Assigned Team Members', 'Jobs_Completed', 'Total_Revenue', 'Total_Material_Cost', 'Labor Cost Burden', 'Net Gross Profit', 'Labor % of Rev Less Mats']].copy()
            fin_metrics_display = fin_metrics_display.sort_values(by='Net Gross Profit', ascending=False)
            fin_metrics_display.columns = ['Name', 'Jobs Done', 'Gross Revenue', 'Material Costs', 'Labor Cost Burden', 'Net Gross Profit', 'Labor % of (Rev - Mats)']
            
            st.dataframe(
                fin_metrics_display.style.format({
                    'Gross Revenue': '${:,.2f}',
                    'Material Costs': '${:,.2f}',
                    'Labor Cost Burden': '${:,.2f}',
                    'Net Gross Profit': '${:,.2f}',
                    'Labor % of (Rev - Mats)': '{:.1f}%'
                }),
                use_container_width=True,
                hide_index=True
            )
            
            st.write("---")
            
            def color_profit_loss(val):
                if val < 0:
                    return 'background-color: #f8d7da; color: #721c24;'
                elif val == 0:
                    return 'background-color: #fff3cd; color: #856404;'
                else:
                    return 'background-color: #d4edda; color: #155724;'

            contractor_keywords = ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian']
            is_contractor_mask = completed_jobs['Assigned Team Members'].astype(str).str.lower().apply(
                lambda x: any(k in x for k in contractor_keywords)
            )
            contractor_df = completed_jobs[is_contractor_mask].copy()
            
            # ---------------------------------------------------------
            # CONTRACTOR AGGREGATE PERFORMANCE SUMMARY
            # ---------------------------------------------------------
            st.subheader("🏢 Contractor Aggregate Performance Summary")
            st.write("Summarizes total revenue, material overhead, payouts, and net business profit/loss aggregated by contractor entity. Sorted from most unlucrative to most profitable.")
            
            if not contractor_df.empty:
                contractor_summary = contractor_df.groupby('Assigned Team Members').agg(
                    Total_Jobs=('Status', 'count'),
                    Total_Revenue=('Total Invoice Amount', 'sum'),
                    Total_Materials=('Material Cost', 'sum'),
                    Total_Payout=('Labor Cost', 'sum'),
                    Total_Net_Profit=('Net Gross Profit', 'sum')
                ).reset_index().sort_values(by='Total_Net_Profit', ascending=True)
                
                contractor_summary.columns = ['Contractor Name', 'Total Jobs Done', 'Total Revenue', 'Total Material Overhead', 'Total Payouts', 'Total Net Profit / Loss']
                
                styler_summary = contractor_summary.style.format({
                    'Total Revenue': '${:,.2f}',
                    'Total Material Overhead': '${:,.2f}',
                    'Total Payouts': '${:,.2f}',
                    'Total Net Profit / Loss': '${:,.2f}'
                })
                
                if hasattr(styler_summary, 'map'):
                    styler_summary = styler_summary.map(color_profit_loss, subset=['Total Net Profit / Loss'])
                else:
                    styler_summary = styler_summary.applymap(color_profit_loss, subset=['Total Net Profit / Loss'])
                    
                st.dataframe(styler_summary, use_container_width=True, hide_index=True)
            else:
                st.info("No contractor metrics found to aggregate.")
                
            st.write("---")
            
            # ---------------------------------------------------------
            # CONTRACTOR PROFIT/LOSS AUDIT (JOB-BY-JOB DETAIL)
            # ---------------------------------------------------------
            st.subheader("🏗️ Contractor Profit & Loss Audit (Job-by-Job Detail)")
            
            if not contractor_df.empty:
                contractor_audit = contractor_df[['#ID', 'Assigned Team Members', 'Business Unit', 'Total Invoice Amount', 'Material Cost', 'Labor Cost', 'Net Gross Profit']].copy()
                contractor_audit = contractor_audit.sort_values(by='Net Gross Profit', ascending=True)
                contractor_audit.columns = ['Job #', 'Contractor', 'Business Unit', 'Gross Revenue', 'Material Cost', 'Contractor Payout', 'Net Profit / Loss']
                
                styler_audit = contractor_audit.style.format({
                    'Gross Revenue': '${:,.2f}',
                    'Material Cost': '${:,.2f}',
                    'Contractor Payout': '${:,.2f}',
                    'Net Profit / Loss': '${:,.2f}'
                })
                
                if hasattr(styler_audit, 'map'):
                    styler_audit = styler_audit.map(color_profit_loss, subset=['Net Profit / Loss'])
                else:
                    styler_audit = styler_audit.applymap(color_profit_loss, subset=['Net Profit / Loss'])
                
                st.dataframe(styler_audit, use_container_width=True, hide_index=True)
            else:
                st.info("No contractor assignments matched in the currently uploaded data range.")
                
            st.info("💡 **Ops Management Insight:** *Labor % of (Rev - Mats)* displays exactly what percentage of your job margin is consumed by labor after paying for equipment/supplies. This accurately captures true labor efficiency independent of material price fluctuations.")
        else:
            st.warning("No completed financial data available to build margins.")

    # ---------------------------------------------------------
    # TAB 3: Geographic Performance
    # ---------------------------------------------------------
    with tab3:
        st.header("Geographic Profitability & Travel Time Analysis")
        if 'Related Invoices' in jobs_df.columns and '#ID' in invoices_df.columns:
            jobs_df['Related Invoices'] = jobs_df['Related Invoices'].astype(str).str.split('.').str[0].str.strip()
            invoices_df['#ID'] = invoices_df['#ID'].astype(str).str.split('.').str[0].str.strip()
            geo_df = pd.merge(jobs_df, invoices_df, left_on='Related Invoices', right_on='#ID', how='inner')
        else:
            geo_df = jobs_df.copy()

        if 'Assigned Team Members' in geo_df.columns:
            geo_df = geo_df.dropna(subset=['Assigned Team Members'])

        if 'Zip Code' in geo_df.columns:
            geo_df['Zip Code'] = geo_df['Zip Code'].astype(str).str.strip()
            geo_df = geo_df[(geo_df['Zip Code'] != 'nan') & (geo_df['Zip Code'] != '')]
            
            col3, col4 = st.columns(2)
            with col3:
                st.subheader("💰 Most Lucrative Zip Codes (Net Profit)")
                if 'Profit Margin' in geo_df.columns:
                    profit_by_zip = geo_df.groupby('Zip Code').agg(
                        Job_Count=('Zip Code', 'count'),
                        Total_Net_Profit=('Profit Margin', 'sum'),
                        Avg_Profit_Per_Job=('Profit Margin', 'mean')
                    ).reset_index().sort_values('Total_Net_Profit', ascending=False)
                    
                    profit_by_zip.columns = ['Zip Code', 'Total Jobs', 'Total Net Profit', 'Avg Profit/Job']
                    st.dataframe(profit_by_zip.style.format({
                        'Total Net Profit': '${:,.2f}', 'Avg Profit/Job': '${:,.2f}'
                    }), use_container_width=True, hide_index=True)
                else:
                    st.info("Profit Margin details missing.")

            with col4:
                st.subheader("🚗 Travel Efficiency by Zone")
                if 'Travel Duration Decimal' in geo_df.columns and 'Total Invoice Amount' in geo_df.columns:
                    travel_waste = geo_df.groupby('Zip Code').agg(
                        Job_Count=('Zip Code', 'count'),
                        Avg_Travel_Hours=('Travel Duration Decimal', 'mean'),
                        Avg_Invoice_Amount=('Total Invoice Amount', 'mean')
                    ).reset_index().sort_values('Avg_Travel_Hours', ascending=False)
                    
                    travel_waste.columns = ['Zip Code', 'Total Jobs', 'Avg Drive Time (H:MM)', 'Avg Ticket Size']
                    st.dataframe(travel_waste.style.format({
                        'Avg Drive Time (H:MM)': format_hours_mins, 'Avg Ticket Size': '${:,.2f}'
                    }), use_container_width=True, hide_index=True)
        else:
            st.warning("No Zip Code field populated in source data.")
else:
    st.info("👋 Welcome! Please upload **all three** operational CSV exports in the sidebar to build your data tables.")
