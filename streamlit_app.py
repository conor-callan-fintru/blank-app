import streamlit as st
import pandas as pd
import datetime
from azure.data.tables import TableServiceClient
import plotly.express as px
import requests
import json # You already have this import

# --- Configuration and Constants ---

# Set page configuration
st.set_page_config(
    page_title="FinTrU Application Health Checks Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #0078D4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #0078D4;
        margin-bottom: 1rem;
    }
    .stats-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #0078D4;
    }
    .metric-label {
        font-size: 1rem;
        color: #555;
    }
</style>
""", unsafe_allow_html=True)

# Azure Table Storage connection details using Streamlit Secrets
# You'll need to set these in your .streamlit/secrets.toml file
CONNECTION_STRING = st.secrets["AZURE_STORAGE_CONNECTION_STRING"]
TABLE_NAME = st.secrets["AZURE_TABLE_NAME"]

# Azure Log Analytics connection details
# You'll need to set these in your .streamlit/secrets.toml file
LOG_ANALYTICS_APP_ID = st.secrets["LOG_ANALYTICS_APP_ID"]
LOG_ANALYTICS_API_KEY = st.secrets["LOG_ANALYTICS_API_KEY"]
LOG_ANALYTICS_API_URL = f"https://api.loganalytics.io/v1/apps/{LOG_ANALYTICS_APP_ID}/query"
LOG_ANALYTICS_ENV_ID = st.secrets["LOG_ANALYTICS_ENV_ID"]

# Define the KQL query to fetch data from Azure Log Analytics
requests_query = f""" 
requests
| where timestamp > ago(7d)
| where customDimensions['resourceProvider'] == 'Cloud Flow'
| where customDimensions['signalCategory'] == 'Cloud flow runs'
| where customDimensions['environmentId'] == '{LOG_ANALYTICS_ENV_ID}'
| extend Data = todynamic(tostring(customDimensions.Data))
| extend Error = todynamic(tostring(customDimensions.error))
| project
    timestamp,
    id,
    environmentId = customDimensions.environmentId,
    DisplayName = Data.FlowDisplayName,
    name,
    RunID = Data.OriginRunId,
    ErrorCode = Error.code,
    ErrorMessage = Error.message,
    success
"""

# Define severity levels for better readability
SEVERITY_LEVELS = {
    1: "Critical",
    2: "Warning",
    3: "Info"
}

# --- Helper Functions ---

@st.cache_data(ttl=300) # Cache data for 5 mins
def load_azure_table_data():
    """Load data from Azure Table Storage"""
    try:
        table_service = TableServiceClient.from_connection_string(CONNECTION_STRING)
        table_client = table_service.get_table_client(TABLE_NAME)
        entities = table_client.query_entities("")
        data = [dict(entity) for entity in entities]
        df = pd.DataFrame(data)

        # Convert 'TimeAlertReceived' to datetime and localize to UTC if not already
        if 'TimeAlertReceived' in df.columns:
            df['TimeAlertReceived'] = pd.to_datetime(df['TimeAlertReceived'], utc=True)
        
        # Map SeverityLevel to human-readable strings
        if 'SeverityLevel' in df.columns:
            df['SeverityLevel'] = df['SeverityLevel'].map(SEVERITY_LEVELS).fillna(df['SeverityLevel']) # Keep original if no mapping
        
        return df

    except Exception as e:
        st.error(f"Error connecting to Azure Table Storage. Please check your connection string and table name: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300) # Cache data for 5 mins
def load_loganalytics_data():
    """Load data from Azure Log Analytics"""
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": LOG_ANALYTICS_API_KEY # Corrected access for API key
        }
        body = {"query": requests_query} # Corrected access for query string
        response = requests.post(LOG_ANALYTICS_API_URL, headers=headers, json=body)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()
        
        # Extract columns and rows from the 'tables' key in the response
        if 'tables' in data and len(data['tables']) > 0:
            columns = [col['name'] for col in data['tables'][0]['columns']]
            rows = data['tables'][0]['rows']
            df = pd.DataFrame(rows, columns=columns)
            
            # Convert 'timestamp' to datetime and localize to UTC
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            
            # Convert 'success' to boolean
            if 'success' in df.columns:
                df['success'] = df['success'].astype(bool)

            return df
        else:
            st.warning("No data found in Azure Log Analytics for the specified query.")
            return pd.DataFrame()
    
    except requests.exceptions.RequestException as req_err:
        st.error(f"Network or HTTP error connecting to Azure Log Analytics: {req_err}")
        return pd.DataFrame()
    except json.JSONDecodeError:
        st.error("Failed to decode JSON response from Azure Log Analytics. Check API key and query.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred while loading Log Analytics data: {str(e)}")
        return pd.DataFrame()

def render_metric_card(value, label):
    """Renders a styled metric card with larger, centered value."""
    st.markdown(f"""
    <div class='stats-card' style="text-align: center;">
        <p class='metric-value' style="font-size: 3rem; text-align: center; margin: 0;">{value}</p>
        <p class='metric-label' style="text-align: center; margin: 0;">{label}</p>
    </div>
    """, unsafe_allow_html=True)

# --- Main Dashboard ---

st.markdown("<h1 class='main-header'>FinTrU Application Health Checks Dashboard</h1>", unsafe_allow_html=True)

# Create tabs
tab1, tab2, tab3 = st.tabs(["Overview", "Support Alerts", "Power Automate"])

with tab1:
    st.subheader("Alerts Overview")
    
    # Load alert data for Overview tab
    alerts_df = load_azure_table_data()

    # Check if dataframe is empty after loading
    if alerts_df.empty:
        st.warning("No data available from Azure Table Storage for Overview. Please ensure it is populated.")
    else:
        # Metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            past7_alerts_df = alerts_df[alerts_df['TimeAlertReceived'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=7))]
            render_metric_card(len(past7_alerts_df), "Alerts - last 7 days")
        
        with col2:
            past1_alerts_df = alerts_df[alerts_df['TimeAlertReceived'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=1))]
            render_metric_card(len(past1_alerts_df), "Alerts - last 24 hours")
        
        with col3:
            critical_alerts = len(alerts_df[alerts_df['SeverityLevel'] == SEVERITY_LEVELS.get(1)]) if 'SeverityLevel' in alerts_df.columns else 0
            render_metric_card(critical_alerts, "Critical Alerts")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Alerts by Source")
            if 'Source' in alerts_df.columns and not alerts_df['Source'].empty:
                status_counts = alerts_df['Source'].value_counts().reset_index(name='Count')
                status_counts.columns = ['Source', 'Count'] 
                
                fig = px.pie(status_counts, values='Count', names='Source', hole=0.4)
                fig.update_traces(textinfo='label+value', hovertemplate='%{label}: %{value}')
                fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No source data available for charting.")
        
        with col2:
            st.subheader("Alerts by Severity")
            if 'SeverityLevel' in alerts_df.columns and not alerts_df['SeverityLevel'].empty:
                priority_counts = alerts_df['SeverityLevel'].value_counts().reset_index(name='Count')
                priority_counts.columns = ['Severity', 'Count'] 
                
                fig = px.bar(priority_counts, x='Severity', y='Count', color='Severity',
                             category_orders={"Severity": list(SEVERITY_LEVELS.values())}) 
                fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No severity data available for charting.")
        
        # Recent Activity
        st.subheader("Recent Activity")
        if 'TimeAlertReceived' in alerts_df.columns and not alerts_df.empty:
            recent_alerts = alerts_df.sort_values('TimeAlertReceived', ascending=False).head(5)
            display_columns = ['TimeAlertReceived', 'Source', 'SeverityLevel', 'ErrorMessage']
            st.dataframe(recent_alerts[display_columns], use_container_width=True, hide_index=True)
        else:
            st.info("No recent activity data available.")

with tab2:
    st.markdown("<h2 class='sub-header'>Support Alerts</h2>", unsafe_allow_html=True)
    
    # Load alert data for Support Alerts tab
    alerts_df = load_azure_table_data()

    if alerts_df.empty:
        st.warning("No data available from Azure Table Storage for Support Alerts. Please ensure it is populated.")
    else:
        # Filters in horizontal layout
        col1, col2 = st.columns(2)
        
        with col1:
            source_options = ['All'] + sorted(alerts_df['Source'].unique().tolist()) if 'Source' in alerts_df.columns else ['All']
            selected_source = st.selectbox("Filter by Source", source_options)
        
        with col2:
            severity_options = ['All'] + sorted(list(SEVERITY_LEVELS.values()), key=lambda x: list(SEVERITY_LEVELS.values()).index(x)) if 'SeverityLevel' in alerts_df.columns else ['All']
            selected_priority = st.selectbox("Filter by Severity", severity_options)
        
        # Apply filters
        filtered_df = alerts_df.copy()
        
        if selected_source != 'All' and 'Source' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Source'] == selected_source]
        
        if selected_priority != 'All' and 'SeverityLevel' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['SeverityLevel'] == selected_priority]
        
        # Display filtered data with selected columns in order and sorted
        columns_to_display = ['TimeAlertReceived', 'Source', 'SeverityLevel', 'ErrorCode', 'ErrorMessage', 'Link', 'StackTrace', 'AdditionalData']
        if not filtered_df.empty:
            sorted_df = filtered_df.sort_values('TimeAlertReceived', ascending=False) # Display newest first
            st.dataframe(sorted_df[columns_to_display], use_container_width=True, hide_index=True)
        else:
            st.info("No alerts match the selected filters.")
            
        # Alert trend over time
        st.subheader("Alert Creation Trend")
        
        if 'TimeAlertReceived' in alerts_df.columns and not alerts_df.empty:
            alerts_df['Date'] = alerts_df['TimeAlertReceived'].dt.date
            trend_df = alerts_df.groupby('Date').size().reset_index(name='Count')
            
            fig = px.line(trend_df, x='Date', y='Count', markers=True, title="Number of Alerts Over Time")
            fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No alert creation trend data available.")

with tab3: # New Power Automate Tab
    st.markdown("<h2 class='sub-header'>Power Automate Flow Monitoring</h2>", unsafe_allow_html=True)

    # Load Power Automate data
    flow_runs_df = load_loganalytics_data()

    if flow_runs_df.empty:
        st.warning("No data available from Azure Log Analytics for Power Automate. Please ensure it is populated and the query is correct.")
    else:
        # Metrics for Power Automate
        st.subheader("Flow Run Metrics")
        col1, col2, col3 = st.columns(3)

        with col1:
            # All runs in the last 7 days
            past7_runs_df = flow_runs_df[flow_runs_df['timestamp'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=7))]
            render_metric_card(len(past7_runs_df), "Total Runs - last 7 days")
        
        with col2:
            # Failed runs in the last 24 hours
            past1_failed_runs_df = flow_runs_df[
                (flow_runs_df['timestamp'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=1))) &
                (flow_runs_df['success'] == False)
            ]
            render_metric_card(len(past1_failed_runs_df), "Failed Runs - last 24 hours")
        
        with col3:
            # Successful runs in the last 24 hours
            past1_successful_runs_df = flow_runs_df[
                (flow_runs_df['timestamp'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=1))) &
                (flow_runs_df['success'] == True)
            ]
            render_metric_card(len(past1_successful_runs_df), "Successful Runs - last 24 hours")

        # Charts for Power Automate
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Flow Runs by Display Name (Last 24 Hours)")
            
            # Filter data for the last 24 hours
            past_24_hours_flows_df = flow_runs_df[
                flow_runs_df['timestamp'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=1))
            ]

            if 'DisplayName' in past_24_hours_flows_df.columns and not past_24_hours_flows_df['DisplayName'].empty:
                # Count occurrences of each DisplayName
                flow_name_counts = past_24_hours_flows_df['DisplayName'].value_counts().reset_index(name='Count')
                flow_name_counts.columns = ['Flow Display Name', 'Count']
                
                fig = px.pie(flow_name_counts, values='Count', names='Flow Display Name', hole=0.4)
                fig.update_traces(textinfo='value', hovertemplate='%{label}: %{value}')
                fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No flow run data available for charting in the last 24 hours.")
        
        with col2:
            # Filterable Table for All Flow Runs - showing counts of each flow
            st.subheader("Flow Run Counts")
        
            # We'll still allow filtering by Display Name and Success Status
            col_flt1, col_flt2 = st.columns(2)
            with col_flt1:
                flow_display_name_options = ['All'] + sorted(flow_runs_df['DisplayName'].unique().tolist()) if 'DisplayName' in flow_runs_df.columns else ['All']
                selected_flow_display_name = st.selectbox("Filter by Flow Display Name (for counts)", flow_display_name_options)
            with col_flt2:
                success_status_options = ['All', 'Successful', 'Failed']
                selected_success_status = st.selectbox("Filter by Run Status (for counts)", success_status_options)

            # Apply filters to the original DataFrame first
            filtered_for_counts_df = flow_runs_df.copy()

            if selected_flow_display_name != 'All' and 'DisplayName' in filtered_for_counts_df.columns:
                filtered_for_counts_df = filtered_for_counts_df[filtered_for_counts_df['DisplayName'] == selected_flow_display_name]
            
            if selected_success_status != 'All' and 'success' in filtered_for_counts_df.columns:
                if selected_success_status == 'Successful':
                    filtered_for_counts_df = filtered_for_counts_df[filtered_for_counts_df['success'] == True]
                elif selected_success_status == 'Failed':
                    filtered_for_counts_df = filtered_for_counts_df[filtered_for_counts_df['success'] == False]

            # Now, group by DisplayName and count the occurrences
            if not filtered_for_counts_df.empty and 'DisplayName' in filtered_for_counts_df.columns:
                flow_summary_df = filtered_for_counts_df.groupby('DisplayName').size().reset_index(name='Run Count')
                flow_summary_df.columns = ['Flow Display Name', 'Run Count'] # Rename columns for clarity
                
                # Sort by Run Count in descending order
                flow_summary_df = flow_summary_df.sort_values('Run Count', ascending=False)

                st.dataframe(flow_summary_df, use_container_width=True, hide_index=True)
            else:
                st.info("No flow runs match the selected filters to display counts.")


        # Flow Run Trend over Time
        st.subheader("Power Automate Flow Run Trend")
        if 'timestamp' in flow_runs_df.columns and not flow_runs_df.empty:
            flow_runs_df['Date'] = flow_runs_df['timestamp'].dt.date
            trend_df = flow_runs_df.groupby('Date').size().reset_index(name='Count')
            
            fig = px.line(trend_df, x='Date', y='Count', markers=True, title="Number of Flow Runs Over Time")
            fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No flow run trend data available.")

        # Table for Recent Failed Runs
        st.subheader("Recent Failed Flow Runs")
        failed_runs_sorted_df = flow_runs_df[flow_runs_df['success'] == False].sort_values('timestamp', ascending=False)
        if not failed_runs_sorted_df.empty:
            display_cols_failed = ['timestamp', 'DisplayName', 'ErrorCode', 'ErrorMessage', 'RunID']
            st.dataframe(failed_runs_sorted_df[display_cols_failed], use_container_width=True, hide_index=True)
        else:
            st.info("No recent failed flow runs to display.")


# Refresh button
if st.button("Refresh Data"):
    st.cache_data.clear() # Clear cache when refreshing
    st.rerun()

# Footer
st.markdown("---")
st.markdown("Azure Support Dashboard Demo | Created with Streamlit")