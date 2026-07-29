import streamlit as st
import pandas as pd
import plotly.express as px

# Set page configuration
st.set_page_config(page_title="Ops Manager Dashboard", layout="wide")

# ---------------------------------------------------------
# 1. DATA LOADING & CLEANING
# ---------------------------------------------------------
@st.cache_data
def load_data():
    # Load raw data
    jobs_raw = pd.read_csv('jobs full data.csv')
    invoices_raw = pd.read_csv('invoices.csv')
    
    # Fix headers (since row 0 contains the actual column names)
    jobs = jobs_raw.copy()
    jobs.columns = jobs.iloc[0]
    jobs = jobs[1:].reset_index(drop=True)
    
    invoices = invoices_raw.copy()
    invoices.columns = invoices.iloc[0]
    invoices = invoices[1:].reset_index(drop=True)
    
    # Clean numeric columns for Jobs
    numeric_cols_jobs = ['Feedback Score', 'Total Invoice Amount', 'Travel Duration Decimal']
    for col in numeric_cols_jobs:
        if col in jobs.columns:
            jobs[col] = pd.to_numeric(jobs[col], errors='coerce')
            
    # Clean date columns for Jobs
    if 'Start Date' in jobs.columns:
        jobs['Start Date'] = pd.to_datetime(jobs['Start Date'], errors='coerce')

    # Clean numeric columns for Invoices
    if 'Profit Margin' in invoices.columns:
        invoices['Profit Margin'] = pd.to_numeric(invoices['Profit Margin'], errors='coerce')

    return jobs, invoices

# Load the data
jobs_df, invoices_df = load_data()

# ---------------------------------------------------------
# 2. DASHBOARD LAYOUT & TABS
# ---------------------------------------------------------
st.title("Water Heater & Install Operations Dashboard")

# Create tabs for the different modules
tab1, tab2 = st.tabs(["Customer Satisfaction & Quality Control", "Geographic & Territory Performance"])

# ---------------------------------------------------------
# TAB 1: Customer Satisfaction & Quality Control
# ---------------------------------------------------------
with tab1:
    st.header("Customer Satisfaction Analysis")
    
    # Filter out empty feedback scores
    feedback_df = jobs_df.dropna(subset=['Feedback Score']).copy()
    
    if not feedback_df.empty:
        col1, col2 = st.columns(2)
        
        # A. Feedback Trends over time
        with col1:
            st.subheader("Feedback Trends Over Time")
            trend_data = feedback_df.groupby(feedback_df['Start Date'].dt.to_period("M"))['Feedback Score'].mean().reset_index()
            trend_data['Start Date'] = trend_data['Start Date'].dt.to_timestamp()
            
            fig_trend = px.line(trend_data, x='Start Date', y='Feedback Score', 
                                markers=True, title="Average Feedback Score (Monthly)")
            st.plotly_chart(fig_trend, use_container_width=True)
            
        # B. Technician Scorecards
        with col2:
            st.subheader("Technician Scorecards")
            tech_scores = feedback_df.groupby('Assigned Team Members')['Feedback Score'].mean().reset_index().sort_values('Feedback Score', ascending=False)
            
            fig_tech = px.bar(tech_scores, x='Assigned Team Members', y='Feedback Score',
                              color='Feedback Score', color_continuous_scale='Viridis',
                              title="Average Score by Technician")
            st.plotly_chart(fig_tech, use_container_width=True)
            
        # C. Install Type Quality
        st.subheader("Quality by Install Type (Job Title)")
        type_scores = feedback_df.groupby('Title')['Feedback Score'].mean().reset_index().sort_values('Feedback Score', ascending=False)
        # Filter to top 15 volume jobs to keep chart readable
        top_titles = feedback_df['Title'].value_counts().nlargest(15).index
        type_scores = type_scores[type_scores['Title'].isin(top_titles)]
        
        fig_type = px.bar(type_scores, x='Title', y='Feedback Score',
                          title="Average Feedback by Job Type (Top 15 Volume)",
                          text_auto='.2f')
        fig_type.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_type, use_container_width=True)
    else:
        st.warning("No feedback score data available to display.")

# ---------------------------------------------------------
# TAB 2: Geographic & Territory Performance
# ---------------------------------------------------------
with tab2:
    st.header("Geographic & Territory Performance")
    
    # Merge Jobs and Invoices to get Profit Margin alongside Zip Code
    # Assuming 'Related Invoices' in jobs maps to '#ID' in invoices, or joining on Customer/Location
    # Adjust the left_on / right_on based on your exact ID matching rules
    if 'Related Invoices' in jobs_df.columns and '#ID' in invoices_df.columns:
        geo_df = pd.merge(jobs_df, invoices_df, left_on='Related Invoices', right_on='#ID', how='inner')
    else:
        geo_df = jobs_df.copy() # Fallback if IDs don't match perfectly in this example

    if 'Zip Code' in geo_df.columns:
        geo_df['Zip Code'] = geo_df['Zip Code'].astype(str).str.strip()
        geo_df = geo_df[geo_df['Zip Code'] != 'nan']
        
        col3, col4 = st.columns(2)
        
        # A. Profit Heatmaps (by Zip Code)
        # Note: True maps require Lat/Lon. Using a bar chart to represent top zip codes.
        with col3:
            st.subheader("Most Lucrative Zip Codes")
            if 'Profit Margin' in geo_df.columns:
                profit_by_zip = geo_df.groupby('Zip Code')['Profit Margin'].sum().reset_index().sort_values('Profit Margin', ascending=False).head(15)
                
                fig_profit = px.bar(profit_by_zip, x='Zip Code', y='Profit Margin',
                                    color='Profit Margin', color_continuous_scale='Greens',
                                    title="Total Profit Margin by Zip Code")
                fig_profit.update_xaxes(type='category')
                st.plotly_chart(fig_profit, use_container_width=True)
            else:
                st.info("Profit Margin column missing or not successfully merged.")

        # B. Travel Waste by Zone
        with col4:
            st.subheader("Travel Waste Analysis")
            if 'Travel Duration Decimal' in geo_df.columns and 'Total Invoice Amount' in geo_df.columns:
                # Group by Zip Code to find average travel vs average invoice
                travel_waste = geo_df.groupby('Zip Code').agg(
                    Avg_Travel=('Travel Duration Decimal', 'mean'),
                    Avg_Invoice=('Total Invoice Amount', 'mean'),
                    Job_Count=('Total Invoice Amount', 'count')
                ).reset_index()
                
                # Filter for zip codes with at least 3 jobs to avoid outliers
                travel_waste = travel_waste[travel_waste['Job_Count'] >= 3]
                
                fig_waste = px.scatter(travel_waste, x='Avg_Travel', y='Avg_Invoice', 
                                       size='Job_Count', color='Zip Code', hover_name='Zip Code',
                                       title="Avg Travel Time vs Avg Invoice Amount by Zip",
                                       labels={'Avg_Travel': 'Avg Travel Time (Hours)', 'Avg_Invoice': 'Avg Invoice Amount ($)'})
                
                # Add horizontal and vertical lines to show the "danger zone" (High travel, low invoice)
                fig_waste.add_hline(y=travel_waste['Avg_Invoice'].median(), line_dash="dot", line_color="red", annotation_text="Median Invoice")
                fig_waste.add_vline(x=travel_waste['Avg_Travel'].median(), line_dash="dot", line_color="red", annotation_text="Median Travel")
                
                st.plotly_chart(fig_waste, use_container_width=True)
            else:
                st.info("Travel duration or Invoice Amount columns missing.")
    else:
        st.warning("No Zip Code data available.")