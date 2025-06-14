import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from urllib.parse import urlparse
import plotly.express as px

# --- Core Functions ---

# Define the CTR curve as percentages
ctr_curve = {
    1: 44.97, 2: 13.62, 3: 8.65, 4: 4.96, 5: 3.05, 6: 2.61,
    7: 2.38, 8: 2.47, 9: 2.55, 10: 1.92, 11: 2.31, 12: 2.35,
    13: 2.42, 14: 2.58, 15: 2.51, 16: 2.12, 17: 1.99, 18: 1.9,
    19: 1.76, 20: 1.3
}

def normalize_domain(domain):
    if pd.isna(domain) or domain == 'Unknown_Domain':
        return 'Unknown_Domain'
    domain = str(domain)
    domain = re.sub(r'^https?://', '', domain)
    parsed = urlparse('//' + domain)
    domain = parsed.netloc
    domain = re.sub(r'^www\.', '', domain)
    return domain

def estimate_traffic(position, search_volume):
    if pd.isna(position) or pd.isna(search_volume):
        return 0
    position = int(position)
    search_volume = int(search_volume)
    if position in ctr_curve:
        return round((ctr_curve[position] / 100) * search_volume)
    return 0

# Caching decorator to improve performance on re-runs
@st.cache_data
def process_file(uploaded_file_contents, designated_domains_tuple):
    df = pd.read_excel(io.BytesIO(uploaded_file_contents))

    # --- ROBUSTNESS FIX: Normalize column names ---
    # Strip leading/trailing whitespace from all column headers
    df.columns = df.columns.str.strip()
    st.info(f"**Columns found in file:** {', '.join(df.columns)}") # Diagnostic message
    # --- END FIX ---

    # --- Data Cleaning & Validation ---
    required_cols_for_processing = ['Keyword Ranking', 'Search Volume', 'Ranked Domain Name']
    missing_cols = [col for col in required_cols_for_processing if col not in df.columns]
    if missing_cols:
        st.error(f"Critical columns are missing from your file: **{', '.join(missing_cols)}**. Please check the spelling and ensure they exist in your uploaded file.")
        return None, None, None, None

    df = df.replace(['-', 'N/A', ''], np.nan)
    df = df.dropna(subset=required_cols_for_processing, how='any')

    df['Keyword Ranking'] = pd.to_numeric(df['Keyword Ranking'], errors='coerce')
    df['Search Volume'] = pd.to_numeric(df['Search Volume'], errors='coerce')
    df = df.dropna(subset=['Keyword Ranking', 'Search Volume'])
    df = df[(df['Keyword Ranking'] >= 1) & (df['Keyword Ranking'] <= 100) & (df['Search Volume'] > 0)]

    df['Ranked Domain Name'] = df['Ranked Domain Name'].apply(normalize_domain)
    if 'Ranked Page URL' in df.columns:
        df['Ranked Page URL'] = df['Ranked Page URL'].fillna('')
    
    # --- Data Processing ---
    df['Estimated Traffic'] = df.apply(lambda row: estimate_traffic(row['Keyword Ranking'], row['Search Volume']), axis=1)
    
    # Dynamic Aggregation based on available columns
    domain_aggs = {
        'Total Estimated Traffic': pd.NamedAgg(column='Estimated Traffic', aggfunc='sum'),
        'Total Search Volume': pd.NamedAgg(column='Search Volume', aggfunc='sum')
    }
    if 'Keywords' in df.columns:
        domain_aggs['Number of Keywords'] = pd.NamedAgg(column='Keywords', aggfunc='nunique')

    domain_traffic = df.groupby('Ranked Domain Name').agg(**domain_aggs).reset_index()
    domain_traffic.rename(columns={'Ranked Domain Name': 'Domain'}, inplace=True)
    
    domain_traffic = domain_traffic[domain_traffic['Domain'] != 'Unknown_Domain']

    total_traffic_for_sov = domain_traffic['Total Estimated Traffic'].sum()
    domain_traffic['SOV_Percentage'] = (domain_traffic['Total Estimated Traffic'] / total_traffic_for_sov) * 100 if total_traffic_for_sov > 0 else 0
    
    domain_traffic = domain_traffic.sort_values(by='Total Estimated Traffic', ascending=False).reset_index(drop=True)
    domain_traffic['Rank'] = domain_traffic.index + 1

    top_domains = domain_traffic.head(20)
    
    designated_domains = [normalize_domain(d) for d in designated_domains_tuple]
    designated_domains_traffic = domain_traffic[domain_traffic['Domain'].isin(designated_domains)]

    top_pages = pd.DataFrame()
    if 'Ranked Page URL' in df.columns and not df.empty:
        top_pages_df = df[df['Ranked Domain Name'].isin(top_domains['Domain']) & (df['Ranked Page URL'] != '')].copy()
        if not top_pages_df.empty:
            page_aggs = {
                'Total Estimated Traffic': pd.NamedAgg(column='Estimated Traffic', aggfunc='sum'),
                'Total Search Volume': pd.NamedAgg(column='Search Volume', aggfunc='sum')
            }
            top_pages = top_pages_df.groupby(['Ranked Domain Name', 'Ranked Page URL']).agg(**page_aggs).reset_index()
            top_pages.rename(columns={'Ranked Domain Name': 'Domain', 'Ranked Page URL': 'Page URL'}, inplace=True)
            top_pages = top_pages.sort_values(by='Total Estimated Traffic', ascending=False).reset_index(drop=True)

    return top_domains, designated_domains_traffic, top_pages, domain_traffic

def create_sample_template():
    sample_data = {
        'Keywords': ['sample keyword 1', 'sample keyword 2'], 'Keyword Ranking': [1, 2],
        'Search Volume': [1000, 800], 'Ranked Domain Name': ['example.com', 'example2.com'],
        'Ranked Page URL': ['https://www.example.com/page1', 'https://www.example2.com/page2']
    }
    df = pd.DataFrame(sample_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title('Share of Voice (SOV) Analysis Dashboard')
st.write('### Created by: Brandon Lazovic')

st.sidebar.header('Setup & Instructions')
st.sidebar.info('''
1.  **Download** the sample template to see the required format.
2.  **Fill** it with your data. Column names must match the template (though extra spaces will be handled).
3.  **Upload** your completed Excel file below.
4.  **Enter** specific domains to track, separated by commas.
5.  **Analyze** the results in the tabs.
''')
st.sidebar.header('Download Template')
st.sidebar.download_button(label='Download Sample Template', data=create_sample_template(), file_name='sample_template.xlsx')

st.header('Upload & Configuration')
uploaded_file = st.file_uploader("Upload your keyword data Excel file", type=["xlsx"])
designated_domains_input = st.text_input("Enter designated domains to track (comma-separated)", value="")

if uploaded_file:
    designated_domains_tuple = tuple(domain.strip() for domain in designated_domains_input.split(",") if domain.strip())
    
    with st.spinner('Processing... This may take a moment.'):
        file_contents = uploaded_file.getvalue()
        top_domains, designated_domains_traffic, top_pages, full_domain_list = process_file(file_contents, designated_domains_tuple)

    if top_domains is not None:
        st.success('Processing complete!')

        tab_dashboard, tab_data, tab_downloads = st.tabs(["📊 Dashboard", "📄 Detailed Data", "📥 Downloads"])

        with tab_dashboard:
            st.header("Visualizations Dashboard")
            st.info("High-level overview of the competitive landscape.")
            st.subheader("Share of Voice Bubble Chart")
            if not top_domains.empty and 'Number of Keywords' in top_domains.columns:
                fig_bubble = px.scatter(
                    top_domains, x='Total Estimated Traffic', y='Number of Keywords',
                    size='SOV_Percentage', color='Domain', hover_name='Domain',
                    log_x=True, size_max=70, title="Top 20: Traffic vs. Keyword Count vs. SOV")
                fig_bubble.update_layout(xaxis_title="Total Estimated Traffic (Log Scale)", yaxis_title="Number of Keywords", showlegend=False)
                st.plotly_chart(fig_bubble, use_container_width=True)
            else:
                st.warning("Bubble chart requires the 'Keywords' column to be present in your file.")
            
            st.subheader('Top 20 Domains by Estimated Traffic & Keyword Count')
            if not top_domains.empty:
                chart_cols = ['Total Estimated Traffic']
                if 'Number of Keywords' in top_domains.columns:
                    chart_cols.append('Number of Keywords')
                chart_data = top_domains.set_index('Domain')[chart_cols]
                st.bar_chart(chart_data)

        with tab_data:
            st.header("Detailed Data Tables")
            st.subheader('Top 20 Domains Data')
            if not top_domains.empty:
                st.dataframe(top_domains)
            
            st.subheader('Designated Domains Traffic')
            if not designated_domains_traffic.empty:
                st.dataframe(designated_domains_traffic)
            
            st.subheader('Top Performing Pages')
            if not top_pages.empty:
                st.dataframe(top_pages)

        with tab_downloads:
            st.header("Download Full Datasets")
            def to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Sheet1')
                return output.getvalue()
            
            if not top_domains.empty:
                 st.download_button(label='Download Top 20 Domains', data=to_excel(top_domains), file_name='top_20_domains.xlsx')
            if not designated_domains_traffic.empty:
                 st.download_button(label='Download Designated Domains', data=to_excel(designated_domains_traffic), file_name='designated_domains_traffic.xlsx')
            if not top_pages.empty:
                 st.download_button(label='Download Top Pages', data=to_excel(top_pages), file_name='top_pages.xlsx')
            if full_domain_list is not None and not full_domain_list.empty:
                 st.download_button(label='Download Full Domain List', data=to_excel(full_domain_list), file_name='full_domain_list.xlsx')
