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
# LABOUR COST CALCULATION ENGINE (WITH CONTRACTOR LOGIC)
# ---------------------------------------------------------
def calculate_job_labor_cost(row):
    tech = str(row['Assigned Team Members'])
    duration = row['Job Duration Decimal']
    revenue = row['Total Invoice Amount']
    bu = str(row['Business Unit'])
    
    # Handle missing or invalid inputs gracefully
    if pd.isna(duration): duration = 0.0
    if pd.isna(revenue): revenue = 0.0
    
    # --- 1. INTERNAL SALARIED EMPLOYEES ---
    if tech == 'Sean Marble':
        return duration * (70000 / 2080)
    elif tech == 'Mathew Hodges':
        return duration * (65000 / 2080)
        
    # --- 2. INTERNAL HOURLY EMPLOYEES ($25/hr) ---
    elif tech in ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']:
        return duration * 25.00
        
    # --- 3. INTERNAL COMMISSION EMPLOYEES (34% of Revenue) ---
    elif tech in ['Erik Tange', 'Bryan Pickett']:
        return revenue * 0.34
        
    # --- 4. EXTERNAL CONTRACTORS ENGINE ---
    else:
        # Detect if worker is a contractor via common name keywords
        is_contractor = any(k in tech.lower() for k in ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian'])
        
        if is_contractor:
            # Rule A: Simple Install jobs pay out total invoice revenue
            if 'simple installs' in bu.lower():
                return revenue
            
            # Rule B: Water Heater jobs pay specified fixed flat rates
            elif 'water heaters' in bu.lower():
                if 'ken' in tech.lower():
                    return 300.00
                elif 'barber' in tech.lower():
                    return 600.00
                elif 'wrench' in tech.lower() or 'wrentch' in tech.lower():
                    return 1800.00
                elif 'indian' in tech.lower() or 'presidio' in tech.lower():
                    return 600.00
        
        # Default fallback for unconfigured accounts
        return 0.0

# ---------------------------------------------------------
# 1. SIDEBAR FILE UPLOADS
# ---------------------------------------------------------
st.sidebar.header("📁 Upload Operational Data")
st.sidebar.write("Upload your CSV exports below to populate the data tables.")

uploaded_jobs = st.sidebar.file_uploader("Upload 'jobs full data.csv'", type=["csv"])
uploaded_invoices = st.sidebar.file_uploader("Upload 'invoices.csv'", type=["csv"])

# Helper function to process the files once uploaded
def process_uploaded_file(file):
    if file is not None:
        df_raw = pd.read_csv(file)
        # Fix headers (since row 0 contains the actual column names in these reports)
        df = df_raw.copy()
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)
        return df
    return None

# Process data if files are provided
raw_jobs_df = process_uploaded_file(uploaded_jobs)
invoices_df = process_uploaded_file(uploaded_invoices)

# ---------------------------------------------------------
# 2. DASHBOARD LOGIC (Runs only when data is uploaded)
# ---------------------------------------------------------
if raw_jobs_df is not None and invoices_df is not None:
    
    # --- STAGE 1: FILTER BY BUSINESS UNIT ---
    if 'Business Unit' in raw_jobs_df.columns:
        jobs_df = raw_jobs_df[
            raw_jobs_df['Business Unit'].str.contains('Water Heaters|Simple Installs', case=False, na=False)
        ].copy()
    else:
        jobs_df = raw_jobs_df.copy()
        st.sidebar.warning("Warning: 'Business Unit' column not found. Showing all jobs.")

    # --- STAGE 2: ATTRIBUTE MULTI-TECH JOBS TO FIRST NAMED TECH ---
    if 'Assigned Team Members' in jobs_df.columns:
        jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].astype(str).str.split(',').str[0].str.strip()
        jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].replace(['nan', 'None', ''], None)

    # --- Clean numeric & date columns for Jobs ---
    numeric_cols_jobs = ['Total Invoice Amount', 'Job Duration Decimal', 'Travel Duration Decimal', 
                         'Invoice - Total Product Cost', 'Invoice - Total Service Cost']
    for col in numeric_cols_jobs:
        if col in jobs_df.columns:
            jobs_df[col] = pd.to_numeric(jobs_df[col], errors='coerce').fillna(0.0)
            
    if 'Start Date' in jobs_df.columns:
        jobs_df['Start Date'] = pd.to_datetime(jobs_df['Start Date'], errors='coerce')

    # --- Clean numeric columns for Invoices ---
    if 'Profit Margin' in invoices_df.columns:
        invoices_df['Profit Margin'] = pd.to_numeric(invoices_df['Profit Margin'], errors='coerce').fillna(0.0)

    # --- STAGE 3: APPLY PAY STRUCTURE & MATERIAL CALCULATIONS ---
    jobs_df['Labor Cost'] = jobs_df.apply(calculate_job_labor_cost, axis=1)
    
    # Base material cost calculation
    jobs_df['Material Cost'] = jobs_df['Invoice - Total Product Cost'] + jobs_df['Invoice - Total Service Cost']
    
    # Adjustment: Deduct $125 built-in labor cushion for all Water Heater business unit jobs
    if 'Business Unit' in jobs_df.columns:
        is_water_heater = jobs_df['Business Unit'].str.contains('Water Heaters', case=False, na=False)
        jobs_df.loc[is_water_heater, 'Material Cost'] = jobs_df.loc[is_water_heater, 'Material Cost'] - 125.00
        jobs_df['Material Cost'] = jobs_df['Material Cost'].clip(lower=0.0)

    # Recalculate true net gross profit based on adjusted materials
    jobs_df['Net Gross Profit'] = jobs_df['Total Invoice Amount'] - jobs_df['Material Cost'] - jobs_df['Labor Cost']

    # Create tabs for the different modules
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
    # TAB 2: Financial & Labor ROI Metrics (Updated Metric)
    # ---------------------------------------------------------
    with tab2:
        st.header("Financial Performance & Labor Cost Analysis")
        st.write("This table tracks internal payroll burden and contractor invoice payouts compared against net operational profit.")
        
        if not completed_jobs.empty:
            # Group financial metrics
            fin_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                Jobs_Completed=('Status', 'count'),
                Total_Revenue=('Total Invoice Amount', 'sum'),
                Total_Material_Cost=('Material Cost', 'sum'),
                Total_Labor_Cost=('Labor Cost', 'sum'),
                Total_Net_Profit=('Net Gross Profit', 'sum')
            ).reset_index().sort_values('Total_Net_Profit', ascending=False)
            
            # Metric Change: Calculate Labor Cost relative to Net Profit instead of Revenue
            fin_metrics['Labor % of Profit'] = (fin_metrics['Total_Labor_Cost'] / fin_metrics['Total_Net_Profit']) * 100
            # Safety: Replace infinite loops or NaN states from division by zero
            fin_metrics['Labor % of Profit'] = fin_metrics['Labor % of Profit'].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            
            fin_metrics.columns = ['Name', 'Jobs Done', 'Gross Revenue', 'Material Costs', 'Labor Cost Burden', 'Net Gross Profit', 'Labor % of Profit']
            
            st.dataframe(
                fin_metrics.style.format({
                    'Gross Revenue': '${:,.2f}',
                    'Material Costs': '${:,.2f}',
                    'Labor Cost Burden': '${:,.2f}',
                    'Net Gross Profit': '${:,.2f}',
                    'Labor % of Profit': '{:.1f}%'
                }),
                use_container_width=True,
                hide_index=True
            )
            
            st.info("💡 **Ops Management Insight:** *Labor % of Profit* measures efficiency by highlighting what portion of your take-home gross profits are absorbed by technician payroll or contractor payouts. Lower percentages represent higher organizational margin retention.")
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
