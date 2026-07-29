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
# LABOUR COST CALCULATION ENGINE
# ---------------------------------------------------------
def calculate_job_labor_cost(row):
    tech = str(row['Assigned Team Members'])
    duration = row['Job Duration Decimal']
    revenue = row['Total Invoice Amount']
    bu = str(row['Business Unit'])
    
    if pd.isna(duration): duration = 0.0
    if pd.isna(revenue): revenue = 0.0
    
    # Internal Salaried Staff
    if tech == 'Sean Marble':
        return duration * (70000 / 2080)
    elif tech == 'Mathew Hodges':
        return duration * (65000 / 2080)
        
    # Internal Hourly Staff ($25/hr)
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
st.sidebar.write("Upload your CSV exports below to populate the data tables.")

uploaded_jobs = st.sidebar.file_uploader("Upload 'jobs full data.csv'", type=["csv"])
uploaded_invoices = st.sidebar.file_uploader("Upload 'invoices.csv'", type=["csv"])

def process_uploaded_file(file):
    if file is not None:
        df_raw = pd.read_csv(file)
        df = df_raw.copy()
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)
        return df
    return None

raw_jobs_df = process_uploaded_file(uploaded_jobs)
invoices_df = process_uploaded_file(uploaded_invoices)

# ---------------------------------------------------------
# 2. DASHBOARD LOGIC
# ---------------------------------------------------------
if raw_jobs_df is not None and invoices_df is not None:
    
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
        else:
            st.warning("No 'Completed' status jobs found.")

    # ---------------------------------------------------------
    # TAB 2: Financial & Labor ROI Metrics
    # ---------------------------------------------------------
    with tab2:
        st.header("Financial Performance & Labor Cost Analysis")
        
        if not completed_jobs.empty:
            st.subheader("📊 Aggregate Team Efficiency")
            fin_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                Jobs_Completed=('Status', 'count'),
                Total_Revenue=('Total Invoice Amount', 'sum'),
                Total_Material_Cost=('Material Cost', 'sum'),
                Total_Labor_Cost=('Labor Cost', 'sum'),
                Total_Net_Profit=('Net Gross Profit', 'sum')
            ).reset_index().sort_values('Total_Net_Profit', ascending=False)
            
            # Recalculated Metric: Labor Cost / (Revenue - Materials)
            revenue_minus_materials = fin_metrics['Total_Revenue'] - fin_metrics['Total_Material_Cost']
            fin_metrics['Labor % of Rev Less Mats'] = (fin_metrics['Total_Labor_Cost'] / revenue_minus_materials) * 100
            fin_metrics['Labor % of Rev Less Mats'] = fin_metrics['Labor % of Rev Less Mats'].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            
            fin_metrics.columns = ['Name', 'Jobs Done', 'Gross Revenue', 'Material Costs', 'Labor Cost Burden', 'Net Gross Profit', 'Labor % of (Rev - Mats)']
            
            st.dataframe(
                fin_metrics.style.format({
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
            
            # ---------------------------------------------------------
            # CONTRACTOR PROFIT/LOSS AUDIT (FIXED TO ELIMINATE MATPLOTLIB)
            # ---------------------------------------------------------
            st.subheader("🏗️ Contractor Profit & Loss Audit (Job-by-Job)")
            st.write("This log tracks contractor tickets to isolate unlucrative operations (e.g., Simple Installs yielding $0 net business margin).")
            
            contractor_keywords = ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian']
            is_contractor_mask = completed_jobs['Assigned Team Members'].astype(str).str.lower().apply(
                lambda x: any(k in x for k in contractor_keywords)
            )
            contractor_df = completed_jobs[is_contractor_mask].copy()
            
            if not contractor_df.empty:
                contractor_audit = contractor_df[['#ID', 'Assigned Team Members', 'Business Unit', 'Total Invoice Amount', 'Material Cost', 'Labor Cost', 'Net Gross Profit']].copy()
                contractor_audit = contractor_audit.sort_values(by='Net Gross Profit', ascending=True)
                contractor_audit.columns = ['Job #', 'Contractor', 'Business Unit', 'Gross Revenue', 'Material Cost', 'Contractor Payout', 'Net Profit / Loss']
                
                # Custom light-weight color rules using raw CSS styles
                def color_profit_loss(val):
                    if val < 0:
                        return 'background-color: #f8d7da; color: #721c24;'  # Soft red alert for losses
                    elif val == 0:
                        return 'background-color: #fff3cd; color: #856404;'  # Soft yellow alert for break-evens
                    else:
                        return 'background-color: #d4edda; color: #155724;'  # Soft green alert for profit margins
                
                # Base string formatting 
                styler = contractor_audit.style.format({
                    'Gross Revenue': '${:,.2f}',
                    'Material Cost': '${:,.2f}',
                    'Contractor Payout': '${:,.2f}',
                    'Net Profit / Loss': '${:,.2f}'
                })
                
                # Safely execute styling without causing cross-version environment friction
                if hasattr(styler, 'map'):
                    styler = styler.map(color_profit_loss, subset=['Net Profit / Loss'])
                else:
                    styler = styler.applymap(color_profit_loss, subset=['Net Profit / Loss'])
                
                st.dataframe(styler, use_container_width=True, hide_index=True)
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
    st.info("👋 Welcome! Please upload **both** operational CSV exports in the sidebar to build your data tables.")
