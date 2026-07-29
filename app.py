import streamlit as st
import pandas as pd

# Set page configuration
st.set_page_config(page_title="Ops Manager Dashboard", layout="wide")

st.title("Water Heater & Simple Installs Operations Dashboard")
st.write("Data filtered exclusively for **Water Heaters** and **Simple Installs** business units.")

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
        # Filter for only Water Heaters and Simple Installs rows
        jobs_df = raw_jobs_df[
            raw_jobs_df['Business Unit'].str.contains('Water Heaters|Simple Installs', case=False, na=False)
        ].copy()
    else:
        jobs_df = raw_jobs_df.copy()
        st.sidebar.warning("Warning: 'Business Unit' column not found. Showing all jobs.")

    # --- Clean numeric & date columns for Jobs ---
    numeric_cols_jobs = ['Total Invoice Amount', 'Job Duration Decimal', 'Travel Duration Decimal']
    for col in numeric_cols_jobs:
        if col in jobs_df.columns:
            jobs_df[col] = pd.to_numeric(jobs_df[col], errors='coerce')
            
    if 'Start Date' in jobs_df.columns:
        jobs_df['Start Date'] = pd.to_datetime(jobs_df['Start Date'], errors='coerce')

    # --- Clean numeric columns for Invoices ---
    if 'Profit Margin' in invoices_df.columns:
        invoices_df['Profit Margin'] = pd.to_numeric(invoices_df['Profit Margin'], errors='coerce')

    # Create tabs for the different modules
    tab1, tab2 = st.tabs(["Technician & Job Metrics", "Geographic & Territory Performance"])

    # ---------------------------------------------------------
    # TAB 1: Technician & Job Metrics (Tables Only)
    # ---------------------------------------------------------
    with tab1:
        st.header("Technician Productivity & Job Performance")
        
        # Only analyze completed work types
        completed_jobs = jobs_df[jobs_df['Status'] == 'Completed'].copy()
        
        if not completed_jobs.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📋 Completed Jobs & Speed by Technician")
                # Group metrics per technician
                tech_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                    Total_Jobs_Completed=('Status', 'count'),
                    Avg_Duration_Hours=('Job Duration Decimal', 'mean'),
                    Total_Revenue_Generated=('Total Invoice Amount', 'sum'),
                    Avg_Revenue_Per_Job=('Total Invoice Amount', 'mean')
                ).reset_index().sort_values('Total_Jobs_Completed', ascending=False)
                
                # Format for clean viewing
                tech_metrics.columns = ['Technician Name', 'Jobs Completed', 'Avg Job Hours', 'Total Revenue', 'Avg Revenue/Job']
                st.dataframe(
                    tech_metrics.style.format({
                        'Avg Job Hours': '{:.2f}', 
                        'Total Revenue': '${:,.2f}', 
                        'Avg Revenue/Job': '${:,.2f}'
                    }), 
                    use_container_width=True,
                    hide_index=True
                )
                
            with col2:
                st.subheader("🔧 Performance Breakdown by Job Type")
                # Group metrics per specific job title
                job_mix = completed_jobs.groupby('Title').agg(
                    Job_Count=('Title', 'count'),
                    Avg_Duration_Hours=('Job Duration Decimal', 'mean'),
                    Avg_Revenue_Per_Job=('Total Invoice Amount', 'mean'),
                    Total_Revenue=('Total Invoice Amount', 'sum')
                ).reset_index().sort_values('Job_Count', ascending=False)
                
                job_mix.columns = ['Job Title / Type', 'Volume Done', 'Avg Hours Spent', 'Avg Ticket Size', 'Total Revenue']
                st.dataframe(
                    job_mix.style.format({
                        'Avg Hours Spent': '{:.2f}', 
                        'Avg Ticket Size': '${:,.2f}', 
                        'Total Revenue': '${:,.2f}'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.warning("No 'Completed' status jobs found for Water Heaters or Simple Installs.")

    # ---------------------------------------------------------
    # TAB 2: Geographic & Territory Performance (Tables Only)
    # ---------------------------------------------------------
    with tab2:
        st.header("Geographic Profitability & Travel Time Analysis")
        
        # Merge the filtered Jobs and Invoices to tie financial details to Zip Codes
        if 'Related Invoices' in jobs_df.columns and '#ID' in invoices_df.columns:
            geo_df = pd.merge(jobs_df, invoices_df, left_on='Related Invoices', right_on='#ID', how='inner')
        else:
            geo_df = jobs_df.copy()

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
                    st.dataframe(
                        profit_by_zip.style.format({
                            'Total Net Profit': '${:,.2f}', 
                            'Avg Profit/Job': '${:,.2f}'
                        }), 
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Profit Margin data missing or unable to match invoice records.")

            with col4:
                st.subheader("🚗 Travel Efficiency & Revenue Leakage by Zone")
                if 'Travel Duration Decimal' in geo_df.columns and 'Total Invoice Amount' in geo_df.columns:
                    travel_waste = geo_df.groupby('Zip Code').agg(
                        Job_Count=('Zip Code', 'count'),
                        Avg_Travel_Hours=('Travel Duration Decimal', 'mean'),
                        Avg_Invoice_Amount=('Total Invoice Amount', 'mean')
                    ).reset_index().sort_values('Avg_Travel_Hours', ascending=False)
                    
                    travel_waste.columns = ['Zip Code', 'Total Jobs', 'Avg Drive Time (Hours)', 'Avg Ticket Size']
                    st.dataframe(
                        travel_waste.style.format({
                            'Avg Drive Time (Hours)': '{:.2f}', 
                            'Avg Ticket Size': '${:,.2f}'
                        }), 
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Travel duration or Invoice Amount metrics are missing in the data.")
        else:
            st.warning("No Zip Code field populated in the uploaded source files.")

else:
    # Landing page state when files aren't uploaded yet
    st.info("👋 Welcome! Please upload **both** operational CSV exports in the sidebar to build your data tables.")
