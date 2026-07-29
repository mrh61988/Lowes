import streamlit as st
import pandas as pd
import numpy as np
import re
import urllib.request
import urllib.parse
import json
import time
import pydeck as pdk

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
# HIGH-FIDELITY LOCAL GEOGRAPHIC SEED DICTIONARY (ARIZONA)
# ---------------------------------------------------------
AZ_ZIP_COORDINATES = {
    '85258': (33.5634, -111.8927), '85750': (32.2980, -110.8449), 
    '86426': (35.0134, -114.5497), '85286': (33.2715, -111.8316), 
    '85251': (33.4936, -111.9167), '85741': (32.3472, -111.0419), 
    '85745': (32.2434, -111.0179), '85138': (33.0073, -111.9324), 
    '85143': (33.1911, -111.5280), '85308': (33.6539, -112.1694), 
    '85142': (33.2487, -111.6343), '85204': (33.3992, -111.7896), 
    '85042': (33.3794, -112.0283), '85326': (33.3519, -112.5908), 
    '85335': (33.6082, -112.3241), '85224': (33.3301, -111.8632), 
    '85297': (33.2781, -111.7096), '85044': (33.3291, -111.9943), 
    '85736': (31.9011, -111.3702), '85255': (33.6860, -111.9020),
    '85260': (33.6000, -111.8900), '85032': (33.6150, -112.0100),
    '85304': (33.6100, -112.1800), '85281': (33.4200, -111.9300),
    '85710': (32.2200, -110.8300), '85712': (32.2500, -110.8900)
}

# ---------------------------------------------------------
# DYNAMIC GEOJSON REGIONAL BOUNDARY INGESTION ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=604800, show_spinner=False)
def load_regional_geojson_boundaries():
    """Streams minified geometric boundary vectors for localized Arizona postal code grids."""
    url = "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/az_arizona_zip_codes_geo.min.json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OpsCode_GeoEngine/7.0'})
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None

# ---------------------------------------------------------
# HIGH-PERFORMANCE CACHED STREET-LEVEL GEOCODING UTILITY
# ---------------------------------------------------------
@st.cache_data(ttl=604800, show_spinner=False)
def geocode_address_string(address_str):
    """Converts street address strings into absolute coordinate primitives via open API queries."""
    if not address_str or len(str(address_str).strip()) < 6 or str(address_str).lower() == 'nan':
        return None
    query_string = str(address_str).strip()
    if not any(state in query_string.upper() for state in [', AZ', ' ARIZONA']):
        query_string += ", AZ"
    encoded_query = urllib.parse.quote(query_string)
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_query}&format=json&limit=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OpsManagerDashboard_Geomap/7.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
    return None

# ---------------------------------------------------------
# RESILIENT AUTOMATIC COLUMN SCANNING ENGINE
# ---------------------------------------------------------
def auto_map_column(keys, columns, exclude_keys=None):
    """Scans variations of column names using prioritized exact and wildcard matches."""
    columns_lower = [str(c).lower().strip() for c in columns]
    for k in keys:
        if k in columns_lower:
            return columns[columns_lower.index(k)]
    for k in keys:
        for col in columns:
            col_lower = str(col).lower()
            if k in col_lower:
                if exclude_keys and any(ex in col_lower for ex in exclude_keys):
                    continue
                return col
    return None

# ---------------------------------------------------------
# DYNAMIC ON-TICKET TIME CALCULATOR ENGINE
# ---------------------------------------------------------
def compute_custom_ticket_hours(row, cols):
    """Calculates ticket duration based on workflow status milestones."""
    start_times = []
    end_times = []
    for idx, col_name in enumerate(cols):
        val = row.iloc[idx]
        if pd.isna(val) or str(val).strip() in ['', '-']:
            continue
        col_clean = str(col_name).lower()
        if 'on the way' in col_clean or 'lowes store' in col_clean or 'in progress' in col_clean:
            if 'start timestamp' in col_clean:
                t = pd.to_datetime(val, errors='coerce')
                if pd.notna(t): start_times.append(t)
        if 'pending audit' in col_clean and 'start timestamp' in col_clean:
            t = pd.to_datetime(val, errors='coerce')
            if pd.notna(t): end_times.append(t)
    if not end_times: return 0.0
    latest_end = max(end_times)
    if not start_times: return 2.0
    earliest_start = min(start_times)
    return max(0.0, (latest_end - earliest_start).total_seconds() / 3600.0)

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
                if pd.notna(t): start_times.append(t)
    if start_times: return min(start_times).date()
    if 'Start Date' in row and pd.notna(row['Start Date']):
        return pd.to_datetime(row['Start Date'], errors='coerce').date()
    return None

# ---------------------------------------------------------
# LABOUR & MATERIAL CALCULATORS
# ---------------------------------------------------------
def calculate_job_labor_cost(row):
    tech = str(row['Assigned Team Members'])
    duration = row['Custom Ticket Hours']
    revenue = row['Total Invoice Amount']
    bu = str(row['Business Unit'])
    if pd.isna(duration): duration = 0.0
    if pd.isna(revenue): revenue = 0.0
    
    if tech == 'Sean Marble': return duration * (70000 / 2080)
    elif tech == 'Mathew Hodges': return duration * (65000 / 2080)
    elif tech in ['Matt Schlosser', 'Tanner LaForge', 'Edward Lopez']: return duration * 25.00
    elif tech in ['Erik Tange', 'Bryan Pickett']: return revenue * 0.34
    else:
        is_contractor = any(k in tech.lower() for k in ['contractor', 'contactor', 'llc', 'ken', 'barber', 'wrench', 'wrentch', 'presidio', 'indian'])
        if is_contractor:
            if 'simple installs' in bu.lower(): return revenue
            elif 'water heaters' in bu.lower():
                if 'ken' in tech.lower(): return 300.00
                elif 'barber' in tech.lower(): return 600.00
                elif 'wrench' in tech.lower() or 'wrentch' in tech.lower(): return 1800.00
                elif 'indian' in tech.lower() or 'presidio' in tech.lower(): return 600.00
        return 0.0

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
        return 650.00 if 'water heaters' in bu else 0.00
    return max(0.00, base_mat - 125.00) if 'water heaters' in bu else base_mat

# ---------------------------------------------------------
# 1. SIDEBAR FILE UPLOADS
# ---------------------------------------------------------
st.sidebar.header("📁 Upload Operational Data")
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
        else: return pd.read_csv(file)
    return None

raw_jobs_df = process_uploaded_file(uploaded_jobs, shifted_header=True)
invoices_df = process_uploaded_file(uploaded_invoices, shifted_header=True)
timesheets_df = process_uploaded_file(uploaded_timesheets, shifted_header=False)

# ---------------------------------------------------------
# 2. DASHBOARD LOGIC
# ---------------------------------------------------------
if raw_jobs_df is not None and invoices_df is not None and timesheets_df is not None:
    
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
    if ts_user_col and ts_user_col != 'User': timesheets_df['User'] = timesheets_df[ts_user_col]
    timesheets_df['Duration Decimal'] = sanitize_numeric_series(timesheets_df[ts_dur_col]) if ts_dur_col else 0.0
    if ts_date_col: timesheets_df['Work Date'] = pd.to_datetime(timesheets_df[ts_date_col], errors='coerce').dt.date

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
    mapped_address = auto_map_column(['street address', 'address', 'full address', 'job address', 'location', 'site address'], job_cols_list)
    mapped_rel_inv = auto_map_column(['related invoices', 'invoice id', 'related invoice', 'invoice #'], job_cols_list)
    mapped_id = auto_map_column(['#id', 'job id', 'ticket number', 'id', 'wo #'], job_cols_list)

    jobs_df_clean = pd.DataFrame()
    jobs_df_clean['Business Unit'] = raw_jobs_df[mapped_bu].fillna('General').astype(str) if mapped_bu else 'General'
    jobs_df_clean['Assigned Team Members'] = raw_jobs_df[mapped_tech].fillna('Unassigned').astype(str) if mapped_tech else 'Unassigned'
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
    jobs_df_clean['Full Address'] = raw_jobs_df[mapped_address].fillna('').astype(str) if mapped_address else ''
    jobs_df_clean['Related Invoices'] = raw_jobs_df[mapped_rel_inv].fillna('').astype(str) if mapped_rel_inv else ''
    jobs_df_clean['#ID'] = raw_jobs_df[mapped_id].fillna('').astype(str) if mapped_id else raw_jobs_df.index.astype(str)

    for col in raw_jobs_df.columns:
        if 'timestamp' in str(col).lower(): jobs_df_clean[col] = raw_jobs_df[col]

    jobs_df = jobs_df_clean[jobs_df_clean['Business Unit'].str.contains('Water Heater|Simple Install', case=False, na=False)].copy()
    jobs_df['Assigned Team Members'] = jobs_df['Assigned Team Members'].astype(str).str.split(',').str[0].str.strip().replace(['nan', 'None', ''], 'Unassigned')

    column_headers = jobs_df.columns.tolist()
    jobs_df['Custom Ticket Hours'] = jobs_df.apply(lambda r: compute_custom_ticket_hours(r, column_headers), axis=1)
    jobs_df['Work Date'] = jobs_df.apply(lambda r: compute_job_date(r, column_headers), axis=1)

    # --- AUTO-MAPPING FOR INVOICES CSV ---
    inv_cols = list(invoices_df.columns)
    inv_id_col = auto_map_column(['#id', 'invoice id', 'id', 'invoice number'], inv_cols)
    if inv_id_col and inv_id_col != '#ID': invoices_df['#ID'] = invoices_df[inv_id_col]

    valid_ts_dates = timesheets_df['Work Date'].dropna()
    days_span = (max(valid_ts_dates) - min(valid_ts_dates)).days + 1 if not valid_ts_dates.empty else 7
    total_weeks = 1.0 if days_span in [5, 6] else max(1, days_span) / 7.0

    jobs_df['Labor Cost'] = jobs_df.apply(calculate_job_labor_cost, axis=1)
    jobs_df['Material Cost'] = jobs_df.apply(calculate_job_material_cost, axis=1)
    jobs_df['Net Gross Profit'] = jobs_df['Total Invoice Amount'] - jobs_df['Material Cost'] - jobs_df['Labor Cost']

    tab1, tab2, tab3 = st.tabs(["Technician & Job Metrics", "Financial & Labor ROI", "Geographic Performance"])

    with tab1:
        st.header("Technician Productivity & Job Performance")
        completed_jobs = jobs_df[jobs_df['Status'] == 'Completed'].copy()
        if not completed_jobs.empty:
            tech_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                Total_Jobs_Completed=('Status', 'count'), Avg_Duration_Hours=('Custom Ticket Hours', 'mean'),
                Total_Revenue_Generated=('Total Invoice Amount', 'sum'), Avg_Revenue_Per_Job=('Total Invoice Amount', 'mean')
            ).reset_index().sort_values('Total_Jobs_Completed', ascending=False)
            st.dataframe(tech_metrics.style.format({'Total_Revenue_Generated': '${:,.2f}'}), use_container_width=True, hide_index=True)

    with tab2:
        st.header("Financial Performance & Labor Cost Analysis")
        if not completed_jobs.empty:
            fin_metrics = completed_jobs.groupby('Assigned Team Members').agg(
                Jobs_Completed=('Status', 'count'), Total_Revenue=('Total Invoice Amount', 'sum'),
                Total_Material_Cost=('Material Cost', 'sum'), Total_Labor_Cost_Jobs=('Labor Cost', 'sum')
            ).reset_index()
            st.dataframe(fin_metrics.style.format({'Total_Revenue': '${:,.2f}'}), use_container_width=True, hide_index=True)

    # ---------------------------------------------------------
    # TAB 3: GEOGRAPHIC PERFORMANCE (MULTI-LAYER CHOROPLETH + TEXT OVERLAY + STREET-LEVEL ADDRESS DOTS)
    # ---------------------------------------------------------
    with tab3:
        st.header("Geographic Profitability & Travel Time Analysis")
        
        geo_df = pd.merge(jobs_df, invoices_df, left_on='Related Invoices', right_on='#ID', how='left', suffixes=('', '_invoice')) if 'Related Invoices' in jobs_df.columns else jobs_df.copy()

        if 'Zip Code' in geo_df.columns:
            geo_df['Zip Code'] = geo_df['Zip Code'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.zfill(5)
            geo_df = geo_df[(geo_df['Zip Code'] != '00nan') & (geo_df['Zip Code'] != '00000') & (geo_df['Zip Code'] != '0None')]

        if not geo_df.empty:
            st.subheader("🗺️ Regional Density Choropleth Map")
            st.write("Shaded areas track high-volume zip codes. **Blue pins showcase the exact street address geolocations of individual tickets**.")
            
            # --- HIGH-FIDELITY HYBRID GEOLOCATION PIPELINE ---
            with st.spinner("Resolving street addresses to precise geo-coordinates..."):
                def resolve_exact_coordinates(row):
                    addr = str(row.get('Full Address', '')).strip()
                    # Step 1: Attempt to process explicit street address geocoding
                    if addr and addr.lower() != 'nan' and len(addr) > 5:
                        coords = geocode_address_string(addr)
                        if coords:
                            return coords[0], coords[1]
                    
                    # Step 2: Fallback to static seed lookup dictionary if street fail matches
                    z_code = str(row.get('Zip Code', '')).strip()
                    if z_code in AZ_ZIP_COORDINATES:
                        return AZ_ZIP_COORDINATES[z_code]
                        
                    return np.nan, np.nan

                # Apply mapping layout coordinates
                geo_df['coords_tuple'] = geo_df.apply(resolve_exact_coordinates, axis=1)
                geo_df['latitude'] = geo_df['coords_tuple'].map(lambda x: x[0])
                geo_df['longitude'] = geo_df['coords_tuple'].map(lambda x: x[1])
            
            # Drop entries completely unable to compile spatial variables
            map_clean_df = geo_df.dropna(subset=['latitude', 'longitude']).copy()
            
            # Aggregate totals per zip zone for boundary layer distribution maps
            zip_geo_counts = map_clean_df.groupby('Zip Code').size().reset_index(name='Job_Count')
            max_jobs = max(1, zip_geo_counts['Job_Count'].max())
            zip_counts_dict = zip_geo_counts.set_index('Zip Code')['Job_Count'].to_dict()
            
            geojson_data = load_regional_geojson_boundaries()
            
            if geojson_data:
                features_to_render = []
                text_overlay_data = []
                
                # HIGH-CONTRAST EXPONENTIAL GRADIENT COLOR SCALE
                def get_high_contrast_red_ramp(count, max_val):
                    if max_val <= 1:
                        ratio = 1.0
                    else:
                        ratio = (count - 1) / (max_val - 1) if max_val > 1 else 0.0
                        ratio = ratio ** 0.7  # Expands visual variance in low-mid tier shifts
                    
                    r = int(255 - (ratio * (255 - 139)))
                    g = int(185 - (ratio * 185))
                    b = int(185 - (ratio * 185))
                    alpha = int(60 + (ratio * 175))
                    return [r, g, b, alpha]

                for feature in geojson_data.get('features', []):
                    props = feature.get('properties', {})
                    z_code = None
                    for key in ['ZCTA5CE10', 'ZCTA5', 'name', 'GEOID10']:
                        if key in props and props[key]:
                            z_code = str(props[key]).strip().zfill(5)
                            break
                    
                    if z_code and z_code in zip_counts_dict:
                        count = zip_counts_dict[z_code]
                        color = get_high_contrast_red_ramp(count, max_jobs)
                        
                        feature['properties']['fill_color'] = color
                        feature['properties']['zip_label'] = z_code
                        feature['properties']['job_volume'] = int(count)
                        features_to_render.append(feature)
                        
                        # Generate text anchors via spatial geometry polygons on the fly
                        geom = feature.get('geometry', {})
                        g_type = geom.get('type', '')
                        coords = geom.get('coordinates', [])
                        lats, lons = [], []
                        
                        if g_type == 'Polygon':
                            for ring in coords:
                                for pt in ring:
                                    lons.append(pt[0])
                                    lats.append(pt[1])
                        elif g_type == 'MultiPolygon':
                            for poly in coords:
                                for ring in poly:
                                    for pt in ring:
                                        lons.append(pt[0])
                                        lats.append(pt[1])
                                        
                        if lats and lons:
                            text_overlay_data.append({
                                'zip_code': z_code,
                                'job_count_str': str(count),
                                'latitude': np.mean(lats),
                                'longitude': np.mean(lons)
                            })

                if features_to_render:
                    filtered_geojson = {"type": "FeatureCollection", "features": features_to_render}
                    text_overlay_df = pd.DataFrame(text_overlay_data)
                    
                    # LAYER 1: Translucent Regional Boundary Choropleth Layer
                    choropleth_layer = pdk.Layer(
                        "GeoJsonLayer",
                        filtered_geojson,
                        opacity=0.85,
                        stroked=True,
                        filled=True,
                        wireframe=True,
                        get_fill_color="properties.fill_color",
                        get_line_color=[120, 20, 20, 255],
                        get_line_width=2.5,
                        line_width_min_pixels=1,
                        pickable=True
                    )
                    
                    # LAYER 2: Heavy Text Value Overlay Layer Centered inside Polygon
                    text_layer = pdk.Layer(
                        "TextLayer",
                        text_overlay_df,
                        get_position="[longitude, latitude]",
                        get_text="job_count_str",
                        get_color=[20, 20, 20, 255],
                        get_size=22,
                        size_scale=1,
                        get_alignment_baseline="'center'",
                        get_text_anchor="'middle'",
                        font_weight="'bold'",
                        font_family="'Arial, sans-serif'"
                    )
                    
                    # LAYER 3: NEW Precision Street Address Dot Matrix Scatter Layer
                    # Clean strings to prevent pydeck from breaking on formatting values
                    map_clean_df['tip_title'] = map_clean_df['Title'].astype(str).str.replace('"', '')
                    map_clean_df['tip_tech'] = map_clean_df['Assigned Team Members'].astype(str)
                    map_clean_df['tip_addr'] = map_clean_df['Full Address'].astype(str).str.replace('"', '')
                    
                    scatterplot_layer = pdk.Layer(
                        "ScatterplotLayer",
                        map_clean_df,
                        get_position="[longitude, latitude]",
                        get_color=[0, 90, 255, 230],       # Electric blue dots piercing the red fields
                        get_line_color=[255, 255, 255, 255], # Crisp white perimeter borders
                        get_radius=35,
                        radius_min_pixels=4.5,            # Highly visible across any scaling configuration
                        radius_max_pixels=12,
                        stroked=True,
                        filled=True,
                        line_width_min_pixels=1,
                        pickable=True
                    )
                    
                    # Generate view dimensions framework 
                    st.pydeck_chart(pdk.Deck(
                        # Multi-layered stack sequence
                        layers=[choropleth_layer, text_layer, scatterplot_layer],
                        initial_view_state=pdk.ViewState(
                            latitude=map_clean_df['latitude'].mean() if not map_clean_df.empty else 33.45,
                            longitude=map_clean_df['longitude'].mean() if not map_clean_df.empty else -112.07,
                            zoom=9.5, pitch=0
                        ),
                        map_style=pdk.map_styles.CARTO_ROAD,
                        tooltip={
                            "html": """
                                <b>Pinpoint Ticket Details</b><br/>
                                <b>Job:</b> {tip_title}<br/>
                                <b>Tech:</b> {tip_tech}<br/>
                                <b>Address:</b> {tip_addr}<br/>
                                <b>Value:</b> ${Total Invoice Amount}<br/>
                                <hr style='margin: 5px 0;'/>
                                <i>Hovering Zone Registry: {Zip Code}</i>
                            """,
                            "style": {"backgroundColor": "maroon", "color": "white", "fontFamily": "Arial"}
                        }
                    ))
                else:
                    st.warning("Uploaded file records are valid but no postal zip matches intersected the state boundaries coordinate registry.")
            else:
                st.error("Boundary layout assets could not be streamed from cloud repositories.")
                
            st.markdown("---")
            
            # --- METRICS TABLES ---
            col3, col4 = st.columns(2)
            with col3:
                st.subheader("💰 Most Lucrative Zip Codes (Net Profit)")
                profit_col = 'Profit Margin' if ('Profit Margin' in geo_df.columns and geo_df['Profit Margin'].sum() != 0) else 'Net Gross Profit'
                profit_by_zip = geo_df.groupby('Zip Code').agg(
                    Job_Count=('Zip Code', 'count'), Total_Net_Profit=(profit_col, 'sum')
                ).reset_index().sort_values('Total_Net_Profit', ascending=False)
                st.dataframe(profit_by_zip.style.format({'Total_Net_Profit': '${:,.2f}'}), use_container_width=True, hide_index=True)
            
            with col4:
                st.subheader("🚗 Travel Efficiency by Zone")
                if 'Travel Duration Decimal' in geo_df.columns and 'Total Invoice Amount' in geo_df.columns:
                    travel_waste = geo_df.groupby('Zip Code').agg(
                        Job_Count=('Zip Code', 'count'), Avg_Travel_Hours=('Travel Duration Decimal', 'mean')
                    ).reset_index().sort_values('Avg_Travel_Hours', ascending=False)
                    st.dataframe(travel_waste.style.format({'Avg_Travel_Hours': '{:.2f} hrs'}), use_container_width=True, hide_index=True)
                else:
                    st.info("Travel tracking metrics are missing or empty in this upload layout stream.")
else:
    st.info("👋 Welcome! Please upload all three operational CSV exports in the sidebar to run data logs.")
