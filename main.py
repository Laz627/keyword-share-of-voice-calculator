import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from urllib.parse import urlparse
import plotly.express as px

# --- Core Functions ---

recast_ctr_curve_2 = {
    1: 18.00, 2: 5.45, 3: 3.46, 4: 2.00, 5: 1.22, 6: 1.04,
    7: 0.95, 8: 0.99, 9: 1.02, 10: 0.77, 11: 0.92, 12: 0.94,
    13: 0.97, 14: 1.03, 15: 1.00, 16: 0.85, 17: 0.80, 18: 0.76,
    19: 0.70, 20: 0.91
}

def normalize_domain(domain):
    if pd.isna(domain): return 'Unknown_Domain'
    domain = str(domain)
    domain = re.sub(r'^https?://', '', domain)
    parsed = urlparse('//' + domain)
    domain = parsed.netloc
    return re.sub(r'^www\.', '', domain)

def estimate_traffic(position, search_volume):
    if pd.isna(position) or pd.isna(search_volume): return 0
    position, search_volume = int(position), int(search_volume)
    return round((ctr_curve.get(position, 0) / 100) * search_volume)

@st.cache_data
def process_file(uploaded_file_contents, designated_domains_tuple):
    df = pd.read_excel(io.BytesIO(uploaded_file_contents))
    df.columns = df.columns.str.strip()
    st.info(f"**Columns found:** {', '.join(df.columns)}")

    required_cols = ['Keyword Ranking', 'Search Volume', 'Ranked Domain Name', 'Keywords']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"Critical columns missing: **{', '.join(missing_cols)}**. The tool requires these columns to function correctly.")
        return None, None, None

    df = df.replace(['-', 'N/A', ''], np.nan).dropna(subset=required_cols)
    for col in ['Keyword Ranking', 'Search Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=['Keyword Ranking', 'Search Volume'], inplace=True)
    df = df[(df['Keyword Ranking'] >= 1) & (df['Keyword Ranking'] <= 100) & (df['Search Volume'] > 0)]
    df['Ranked Domain Name'] = df['Ranked Domain Name'].apply(normalize_domain)
    df['Estimated Traffic'] = df.apply(lambda row: estimate_traffic(row['Keyword Ranking'], row['Search Volume']), axis=1)
    
    # --- CORRECTED AGGREGATION LOGIC ---
    # 1. Standard aggregations (sum of traffic, count of unique keywords)
    aggs = {
        'Total Estimated Traffic': ('Estimated Traffic', 'sum'),
        'Number of Keywords': ('Keywords', 'nunique')
    }
    domain_traffic = df.groupby('Ranked Domain Name').agg(**aggs).reset_index()

    # 2. Correct Addressable Search Volume calculation (deduplicated)
    deduped_sv = df.drop_duplicates(subset=['Ranked Domain Name', 'Keywords'])
    addressable_volume = deduped_sv.groupby('Ranked Domain Name')['Search Volume'].sum().reset_index()
    addressable_volume.rename(columns={'Search Volume': 'Total Addressable Search Volume'}, inplace=True)
    
    # 3. Merge the correct SV back into the main dataframe
    domain_traffic = pd.merge(domain_traffic, addressable_volume, on='Ranked Domain Name', how='left')
    # --- END CORRECTION ---

    domain_traffic.rename(columns={'Ranked Domain Name': 'Domain'}, inplace=True)
    
    total_sov_traffic = domain_traffic['Total Estimated Traffic'].sum()
    domain_traffic['SOV_Percentage'] = (domain_traffic['Total Estimated Traffic'] / total_sov_traffic) * 100 if total_sov_traffic > 0 else 0
    
    domain_traffic = domain_traffic.sort_values(by='Total Estimated Traffic', ascending=False).reset_index(drop=True)
    domain_traffic['Rank'] = domain_traffic.index + 1
    
    # Reorder columns for clarity in the detailed data view
    final_cols = ['Rank', 'Domain', 'Total Estimated Traffic', 'Total Addressable Search Volume', 'Number of Keywords', 'SOV_Percentage']
    existing_final_cols = [col for col in final_cols if col in domain_traffic.columns]
    domain_traffic = domain_traffic[existing_final_cols]

    top_domains = domain_traffic.head(20)
    designated_traffic = domain_traffic[domain_traffic['Domain'].isin(list(designated_domains_tuple))]

    return top_domains, designated_traffic, domain_traffic

def create_sample_template():
    sample_data = {
        'Keywords': ['keyword a', 'keyword b'], 'Keyword Ranking': [1, 2],
        'Search Volume': [1000, 2000], 'Ranked Domain Name': ['domain1.com', 'domain2.com']
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
st.sidebar.info("1. Download template.\n2. Fill with your data.\n3. Upload file.\n4. Enter domains to track.\n5. Analyze.")
st.sidebar.header('Download Template')
st.sidebar.download_button('Download Sample Template', create_sample_template(), 'sample_template.xlsx')

st.header('Upload & Configuration')
uploaded_file = st.file_uploader("Upload your keyword data Excel file", type=["xlsx"])
designated_domains_input = st.text_input("Enter designated domains to track (comma-separated)", "")

if uploaded_file:
    designated_tuple = tuple(normalize_domain(d.strip()) for d in designated_domains_input.split(",") if d.strip())
    
    with st.spinner('Processing...'):
        file_contents = uploaded_file.getvalue()
        top_domains, designated_traffic, full_list = process_file(file_contents, designated_tuple)

    if top_domains is not None:
        st.success('Processing complete!')
        tabs = st.tabs(["📊 Dashboard", "📄 Detailed Data", "📥 Downloads"])
        
        with tabs[0]:
            st.header("Visualizations Dashboard")
            st.subheader("Top 20 Market Landscape")
            st.info("Hover over the legend to highlight a domain in the chart.")
            col1, col2 = st.columns([2, 1])
            with col1:
                if not top_domains.empty:
                    fig_bubble = px.scatter(
                        top_domains, x='Total Estimated Traffic', y='Number of Keywords',
                        size='SOV_Percentage', color='Domain', text='Rank', log_x=True, size_max=80,
                        custom_data=['Domain', 'Total Estimated Traffic', 'Number of Keywords', 'SOV_Percentage', 'Total Addressable Search Volume']
                    )
                    fig_bubble.update_traces(
                        textposition='middle center', textfont_size=12,
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br><br>"
                            "Est. Traffic: %{customdata[1]:,}<br>"
                            "Addressable SV: %{customdata[4]:,}<br>"
                            "# of Keywords: %{customdata[2]:,}<br>"
                            "Share of Voice: %{customdata[3]:.2f}%"
                            "<extra></extra>"
                        )
                    )
                    fig_bubble.update_layout(xaxis_title="Total Estimated Traffic (Log Scale)", yaxis_title="Number of Keywords", showlegend=False)
                    st.plotly_chart(fig_bubble, use_container_width=True)
            with col2:
                st.write("#### Top 20 Legend")
                st.dataframe(top_domains[['Rank', 'Domain']].set_index('Rank'), use_container_width=True)
            
            st.subheader('Top 20 Domains by Performance')
            if not top_domains.empty:
                fig_bar = px.bar(top_domains, x='Domain', y='Total Estimated Traffic', title='Domain Performance by Traffic', labels={"Total Estimated Traffic": "Estimated Traffic"})
                fig_bar.update_xaxes(type='category')
                fig_bar.update_traces(hovertemplate='%{y:,}<extra></extra>')
                st.plotly_chart(fig_bar, use_container_width=True)

            if not designated_traffic.empty:
                st.markdown("---")
                st.header("Designated Domain Analysis")
                st.info("A focused view on the competitive cohort you specified.")
                st.subheader("Designated Domain Landscape")
                col3, col4 = st.columns([2, 1])
                with col3:
                    fig_bubble_des = px.scatter(
                        designated_traffic, x='Total Estimated Traffic', y='Number of Keywords',
                        size='SOV_Percentage', color='Domain', text='Rank', log_x=True, size_max=80,
                        custom_data=['Domain', 'Total Estimated Traffic', 'Number of Keywords', 'SOV_Percentage', 'Total Addressable Search Volume']
                    )
                    fig_bubble_des.update_traces(
                        textposition='middle center', textfont_size=12,
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br><br>"
                            "Est. Traffic: %{customdata[1]:,}<br>"
                            "Addressable SV: %{customdata[4]:,}<br>"
                            "# of Keywords: %{customdata[2]:,}<br>"
                            "Share of Voice: %{customdata[3]:.2f}%"
                            "<extra></extra>"
                        )
                    )
                    fig_bubble_des.update_layout(xaxis_title="Est. Traffic (Log Scale)", yaxis_title="# of Keywords", showlegend=False)
                    st.plotly_chart(fig_bubble_des, use_container_width=True)
                with col4:
                    st.write("#### Designated Legend")
                    st.dataframe(designated_traffic[['Rank', 'Domain']].set_index('Rank'), use_container_width=True)

                st.subheader('Designated Domains by Performance')
                fig_bar_des = px.bar(designated_traffic, x='Domain', y='Total Estimated Traffic', title='Designated Domain Performance by Traffic', labels={"Total Estimated Traffic": "Estimated Traffic"})
                fig_bar_des.update_xaxes(type='category')
                fig_bar_des.update_traces(hovertemplate='%{y:,}<extra></extra>')
                st.plotly_chart(fig_bar_des, use_container_width=True)

        with tabs[1]:
            st.header("Detailed Data Tables")
            st.subheader('Top 20 Domains Data')
            if not top_domains.empty: st.dataframe(top_domains)
            st.subheader('Designated Domains Traffic')
            if not designated_traffic.empty: st.dataframe(designated_traffic)

        with tabs[2]:
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
            if full_list is not None and not full_list.empty:
                 st.download_button("Download Full Domain List", to_excel(full_list), "full_domain_list.xlsx")
