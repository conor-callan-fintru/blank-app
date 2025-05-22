import streamlit as st
import pandas as pd
import datetime
from azure.data.tables import TableServiceClient
import plotly.express as px

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
# Example secrets.toml:
# AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=supportsacc;AccountKey=YOUR_ACCOUNT_KEY;EndpointSuffix=core.windows.net"
# AZURE_TABLE_NAME = "SupportAlertsTable"
CONNECTION_STRING = st.secrets["AZURE_STORAGE_CONNECTION_STRING"]
TABLE_NAME = st.secrets["AZURE_TABLE_NAME"]

# Define severity levels for better readability
SEVERITY_LEVELS = {
    1: "Critical",
    2: "High",
    3: "Medium",
    4: "Low",
    # Add more as needed based on your data
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

def render_metric_card(value, label):
    """Renders a styled metric card."""
    st.markdown(f"""
    <div class='stats-card'>
        <p class='metric-value'>{value}</p>
        <p class='metric-label'>{label}</p>
    </div>
    """, unsafe_allow_html=True)

# --- Main Dashboard ---

st.markdown("<h1 class='main-header'>FinTrU Application Health Checks Dashboard</h1>", unsafe_allow_html=True)

# Load alert data
alerts_df = load_azure_table_data()

# Check if dataframe is empty after loading
if alerts_df.empty:
    st.warning("No data available to display. Please ensure Azure Table Storage is populated.")
    # Exit early if no data
    st.stop()

# Create tabs
tab1, tab2 = st.tabs(["Overview", "Support Alerts"])

with tab1:
    st.markdown("<h2 class='sub-header'>Dashboard Overview</h2>", unsafe_allow_html=True)
    
    # Metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        past7_alerts_df = alerts_df[alerts_df['TimeAlertReceived'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=7))]
        render_metric_card(len(past7_alerts_df), "Alerts - last 7 days")
    
    with col2:
        past1_alerts_df = alerts_df[alerts_df['TimeAlertReceived'] >= (pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=1))]
        render_metric_card(len(past1_alerts_df), "Alerts - last 24 hours")
    
    with col3:
        # Using the mapped 'Critical' string now
        critical_alerts = len(alerts_df[alerts_df['SeverityLevel'] == SEVERITY_LEVELS.get(1)]) if 'SeverityLevel' in alerts_df.columns else 0
        render_metric_card(critical_alerts, "Critical Alerts")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Alerts by Source")
        if 'Source' in alerts_df.columns and not alerts_df['Source'].empty:
            status_counts = alerts_df['Source'].value_counts().reset_index(name='Count')
            status_counts.columns = ['Source', 'Count'] # Ensure consistent column names
            
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
            priority_counts.columns = ['Severity', 'Count'] # Ensure consistent column names
            
            fig = px.bar(priority_counts, x='Severity', y='Count', color='Severity',
                         category_orders={"Severity": list(SEVERITY_LEVELS.values())}) # Order bars
            fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No severity data available for charting.")
    
    # Recent Activity
    st.subheader("Recent Activity")
    if 'TimeAlertReceived' in alerts_df.columns and not alerts_df.empty:
        recent_alerts = alerts_df.sort_values('TimeAlertReceived', ascending=False).head(5)
        # Select specific columns for display in recent activity for brevity
        display_columns = ['TimeAlertReceived', 'Source', 'SeverityLevel', 'ErrorMessage']
        st.dataframe(recent_alerts[display_columns], use_container_width=True, hide_index=True)
    else:
        st.info("No recent activity data available.")

with tab2:
    st.markdown("<h2 class='sub-header'>Support Alerts</h2>", unsafe_allow_html=True)
    
    # Filters in horizontal layout
    col1, col2 = st.columns(2)
    
    with col1:
        # Use the mapped severity levels for the selectbox options
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

# Refresh button
if st.button("Refresh Data"):
    st.cache_data.clear() # Clear cache when refreshing
    st.rerun()

# Footer
st.markdown("---")
st.markdown("Azure Support Dashboard Demo | Created with Streamlit")