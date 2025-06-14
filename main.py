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

    # Normalize column names for robustness
    df.columns = df.columns.str.strip()
    st.info(f"**Columns found in file:** {', '.join(df.columns)}")

    # Validate critical columns
    required_cols = ['Keyword Ranking', 'Search Volume', 'Ranked Domain Name']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"Critical columns are missing: **{', '.join(missing_cols)}**. Please check your file.")
        return None, None, None, None

    # Data Cleaning
    df = df.replace(['-', 'N/A', ''], np.nan).dropna(subset=required_cols)
    df['Keyword Ranking'] = pd.to_numeric(df['Keyword Ranking'], errors='coerce')
    df['Search Volume'] = pd.to_numeric(df['Search Volume'], errors='coerce')
    df = df.dropna(subset=['Keyword Ranking', 'Search Volume'])
    df = df[(df['Keyword Ranking'] >= 1) & (df['Keyword Ranking'] <= 100) & (df['Search Volume'] > 0)]
    df['Ranked Domain Name'] = df['Ranked Domain Name'].apply(normalize_domain)
    if 'Ranked Page URL' in df.columns:
        df['Ranked Page URL'] = df['Ranked Page URL'].fillna('')
    
    # Data Processing
    df['Estimated Traffic'] = df.apply(lambda row: estimate_traffic(row['Keyword Ranking'], row['Search Volume']), axis=1)
    
    aggs = {'Total Estimated Traffic': pd.NamedAgg(column='Estimated Traffic', aggfunc='sum')}
    if 'Search Volume' in df.columns:
        aggs['Total Search Volume'] = pd.NamedAgg(column='Search Volume', aggfunc='sum')
    if 'Keywords' in df.columns:
        aggs['Number of Keywords'] = pd.NamedAgg(column='Keywords', aggfunc='nunique')

    domain_traffic = df.groupby('Ranked Domain Name').agg(**aggs).reset_index()
    domain_traffic.rename(columns={'Ranked Domain Name': 'Domain'}, inplace=True)
    
    total_sov_traffic = domain_traffic['Total Estimated Traffic'].sum()
    domain_traffic['SOV_Percentage'] = (domain_traffic['Total Estimated Traffic'] / total_sov_traffic) * 100 if total_sov_traffic > 0 else 0
    
    domain_traffic = domain_traffic.sort_values(by='Total Estimated Traffic', ascending=False).reset_index(drop=True)
    domain_traffic['Rank'] = domain_traffic.index + 1

    top_domains = domain_traffic.head(20)
    designated_traffic = domain_traffic[domain_traffic['Domain'].isin(list(designated_domains_tuple))]

    top_pages = pd.DataFrame()
    if 'Ranked Page URL' in df.columns and 'Ranked Domain Name' in df.columns:
        top_pages_df = df[df['Ranked Domain Name'].isin(top_domains['Domain']) & (df['Ranked Page URL'] != '')].copy()
        if not top_pages_df.empty:
            page_aggs = {'Total Estimated Traffic': pd.NamedAgg(column='Estimated Traffic', aggfunc='sum')}
            if 'Search Volume' in df.columns:
                page_aggs['Total Search Volume'] = pd.NamedAgg(column='Search Volume', aggfunc='sum')
            top_pages = top_pages_df.groupby(['Ranked Domain Name', 'Ranked Page URL']).agg(**page_aggs).reset_index()
            top_pages.rename(columns={'Ranked Domain Name': 'Domain', 'Ranked Page URL': 'Page URL'}, inplace=True)
            top_pages = top_pages.sort_values(by='Total Estimated Traffic', ascending=False).reset_index(drop=True)

    return top_domains, designated_traffic, top_pages, domain_traffic

def create_sample_template():
    sample_data = {
        'Keywords': ['keyword a', 'keyword b'], 'Keyword Ranking': [1, 2],
        'Search Volume': [1000, 2000], 'Ranked Domain Name': ['domain1.com', 'domain2.com'],
        'Ranked Page URL': ['https://domain1.com/page', 'https://domain2.com/page']
    }
    df = pd.DataFrame(sample_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    return output.getvalue()

# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title('Share of Voice (SOV) Analysis Dashboard')
st.write('### Created by: Brandon Lazovic')

st.sidebar.header('Setup & Instructions')
st.sidebar.info('''
1.  **Download** the sample template.
2.  **Fill** it with your data. Column names must match the template.
3.  **Upload** your completed Excel file below.
4.  **Enter** domains to track (optional).
5.  **Analyze** the dashboard results.
''')
st.sidebar.header('Download Template')
st.sidebar.download_button(label='Download Sample Template', data=create_sample_template(), file_name='sample_template.xlsx')

st.header('Upload & Configuration')
uploaded_file = st.file_uploader("Upload your keyword data Excel file", type=["xlsx"])
designated_domains_input = st.text_input("Enter designated domains to track (comma-separated)", value="")

if uploaded_file:
    designated_tuple = tuple(d.strip() for d in designated_domains_input.split(",") if d.strip())
    
    with st.spinner('Processing...'):
        file_contents = uploaded_file.getvalue()
        top_domains, designated_traffic, top_pages, full_list = process_file(file_contents, designated_tuple)

    if top_domains is not None:
        st.success('Processing complete!')

        tabs = st.tabs(["📊 Dashboard", "📄 Detailed Data", "📥 Downloads"])
        
        with tabs[0]: # Dashboard
            st.header("Visualizations Dashboard")
            
            st.subheader("Share of Voice Landscape")
            st.info("Hover over the legend on the right to highlight a domain in the chart.")

            # Create a two-column layout: 2/3 for the chart, 1/3 for the legend
            col1, col2 = st.columns([2, 1])

            with col1:
                if not top_domains.empty and 'Number of Keywords' in top_domains.columns:
                    fig_bubble = px.scatter(
                        top_domains, x='Total Estimated Traffic', y='Number of Keywords',
                        size='SOV_Percentage', color='Domain', hover_name='Domain',
                        text='Rank', # Label bubbles with their rank number
                        log_x=True, size_max=80)
                    
                    fig_bubble.update_traces(textposition='middle center', textfont_size=12)
                    fig_bubble.update_layout(
                        xaxis_title="Total Estimated Traffic (Log Scale)",
                        yaxis_title="Number of Keywords",
                        showlegend=False, # Hide the default legend
                        title="Top 20 Domains: Traffic vs. Keyword Count vs. SOV"
                    )
                    st.plotly_chart(fig_bubble, use_container_width=True)
                else:
                    st.warning("Bubble chart requires the 'Keywords' column to be present.")

            with col2:
                st.write("#### Top 20 Domains Legend")
                # Display a clean, numbered legend table
                legend_df = top_domains[['Rank', 'Domain']].set_index('Rank')
                st.dataframe(legend_df, use_container_width=True)
            
            st.subheader('Top 20 Domains by Performance')
            if not top_domains.empty:
                chart_cols = ['Total Estimated Traffic']
                if 'Number of Keywords' in top_domains.columns:
                    chart_cols.append('Number of Keywords')
                
                # Use Plotly Bar chart for strict sorting
                fig_bar = px.bar(top_domains, x='Domain', y=chart_cols, title='Domain Performance Sorted by Traffic',
                                 labels={'value': 'Total Count', 'variable': 'Metric'})
                fig_bar.update_xaxes(type='category') # Ensures order is respected
                st.plotly_chart(fig_bar, use_container_width=True)

        with tabs[1]: # Detailed Data
            st.header("Detailed Data Tables")
            st.subheader('Top 20 Domains Data')
            if not top_domains.empty: st.dataframe(top_domains)
            
            st.subheader('Designated Domains Traffic')
            if not designated_traffic.empty: st.dataframe(designated_traffic)
            
            st.subheader('Top Performing Pages')
            if not top_pages.empty: st.dataframe(top_pages)

        with tabs[2]: # Downloads
            st.header("Download Full Datasets")
            def to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Data')
                return output.getvalue()
            
            if not top_domains.empty:
                 st.download_button("Download Top 20 Domains", to_excel(top_domains), "top_20_domains.xlsx")
            if not designated_traffic.empty:
                 st.download_button("Download Designated Domains", to_excel(designated_traffic), "designated_domains.xlsx")
            if not top_pages.empty:
                 st.download_button("Download Top Pages", to_excel(top_pages), "top_pages.xlsx")
            if full_list is not None and not full_list.empty:
                 st.download_button("Download Full Domain List", to_excel(full_list), "full_domain_list.xlsx")
