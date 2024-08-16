import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from urllib.parse import urlparse

# Define the CTR curve as percentages
ctr_curve = {
    1: 44.97, 2: 13.62, 3: 8.65, 4: 4.96, 5: 3.05, 6: 2.61,
    7: 2.38, 8: 2.47, 9: 2.55, 10: 1.92, 11: 2.31, 12: 2.35,
    13: 2.42, 14: 2.58, 15: 2.51, 16: 2.12, 17: 1.99, 18: 1.9,
    19: 1.76, 20: 1.3
}

def normalize_domain(domain):
    # Remove protocol if present
    domain = re.sub(r'^https?://', '', domain)
    
    # Parse the domain
    parsed = urlparse('//' + domain)
    
    # Get the network location (domain)
    domain = parsed.netloc
    
    # Remove 'www.' if present
    domain = re.sub(r'^www\.', '', domain)
    
    return domain

# Function to estimate traffic based on position
def estimate_traffic(position, search_volume):
    if pd.isna(position) or pd.isna(search_volume):
        return 0
    position = int(position)
    search_volume = int(search_volume)
    if position in ctr_curve:
        return round((ctr_curve[position] / 100) * search_volume)
    return 0

# Function to clean and preprocess data
def clean_data(df):
    # Replace '-', 'N/A', and empty strings with NaN
    df = df.replace(['-', 'N/A', ''], np.nan)
    
    # Drop rows where all required columns are NaN
    required_columns = ['Keywords', 'Keyword Ranking', 'Search Volume', 'Ranked Domain Name', 'Ranked Page URL']
    df = df.dropna(subset=required_columns, how='all')
    
    # Convert 'Keyword Ranking' and 'Search Volume' to numeric, coercing errors to NaN
    df['Keyword Ranking'] = pd.to_numeric(df['Keyword Ranking'], errors='coerce')
    df['Search Volume'] = pd.to_numeric(df['Search Volume'], errors='coerce')
    
    # Filter out rows with invalid rankings or search volumes
    df = df[(df['Keyword Ranking'] >= 1) & (df['Keyword Ranking'] <= 100) & (df['Search Volume'] > 0)]
    
    # Fill remaining NaNs with appropriate values
    df['Ranked Domain Name'] = df['Ranked Domain Name'].fillna('Unknown')
    df['Ranked Page URL'] = df['Ranked Page URL'].fillna('')
    
    # Normalize domain names
    df['Ranked Domain Name'] = df['Ranked Domain Name'].apply(normalize_domain)
    
    return df

# Function to process the uploaded file
def process_file(uploaded_file, designated_domains):
    # Read the uploaded Excel file
    df = pd.read_excel(uploaded_file)

    # Clean and preprocess the data
    df = clean_data(df)

    # Normalize designated domains
    designated_domains = [normalize_domain(domain) for domain in designated_domains]

    # Estimate traffic for each row
    df['Estimated Traffic'] = df.apply(
        lambda row: estimate_traffic(row['Keyword Ranking'], row['Search Volume']), axis=1
    )

    # Aggregate traffic by domain
    domain_traffic = df.groupby('Ranked Domain Name').agg(
        {'Estimated Traffic': 'sum', 'Search Volume': 'sum'}
    ).reset_index()
    domain_traffic.columns = ['Domain', 'Total Estimated Traffic', 'Total Search Volume']

    # Sort by estimated traffic and then by search volume if estimated traffic is zero
    domain_traffic = domain_traffic.sort_values(
        by=['Total Estimated Traffic', 'Total Search Volume'], 
        ascending=[False, False]
    ).reset_index(drop=True)

    # Add ranking column for full list
    domain_traffic['Rank'] = domain_traffic.index + 1

    # Select top 20 domains
    top_domains = domain_traffic.head(20)

    # Filter out designated domains for separate table
    designated_domains_traffic = domain_traffic[domain_traffic['Domain'].isin(designated_domains)]

    # Convert columns to appropriate types
    top_domains = top_domains.astype({'Rank': 'int', 'Total Estimated Traffic': 'int', 'Total Search Volume': 'int'})
    if not designated_domains_traffic.empty:
        designated_domains_traffic = designated_domains_traffic.astype({'Rank': 'int', 'Total Estimated Traffic': 'int', 'Total Search Volume': 'int'})

    # Filter for top 20 domains and non-blank page URLs
    top_pages = df[df['Ranked Domain Name'].isin(top_domains['Domain']) & (df['Ranked Page URL'] != '')]

    # Group by domain and page URL, and calculate total search volume and estimated traffic
    top_pages = top_pages.groupby(['Ranked Domain Name', 'Ranked Page URL']).agg(
        {'Search Volume': 'sum', 'Estimated Traffic': 'sum'}
    ).reset_index()

    # Sort and filter top 3 pages for each domain by Estimated Traffic
    top_pages = top_pages.sort_values(by=['Ranked Domain Name', 'Estimated Traffic'], ascending=[True, False])
    top_pages = top_pages.groupby('Ranked Domain Name').head(3).reset_index(drop=True)

    # Rename columns
    top_pages.columns = ['Domain', 'Page URL', 'Total Search Volume', 'Total Estimated Traffic']

    # Convert columns to appropriate types
    top_pages = top_pages.astype({'Total Search Volume': 'int', 'Total Estimated Traffic': 'int'})

    return top_domains, designated_domains_traffic, top_pages, domain_traffic

# Function to create a sample template
def create_sample_template():
    sample_data = {
        'Keywords': ['sample keyword 1', 'sample keyword 2'],
        'Keyword Ranking': [1, 2],
        'Search Volume': [1000, 800],
        'Ranked Domain Name': ['example.com', 'example2.com'],
        'Ranked Page URL': ['https://www.example.com/page1', 'https://www.example2.com/page2']
    }
    df = pd.DataFrame(sample_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    output.seek(0)
    return output

# Streamlit app
st.title('Share of Voice Analysis Tool')
st.write('### Created by: Brandon Lazovic')
st.write('This tool allows you to upload keyword ranking data and get a share of voice analysis for the top domains.')

# Provide sample template download
st.write('### Download Sample Template')
template = create_sample_template()
st.download_button(label='Download Sample Template', data=template, file_name='sample_template.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# File uploader
uploaded_file = st.file_uploader("Upload your keyword data Excel file", type=["xlsx"])

# Designated domains input
designated_domains_input = st.text_input("Enter designated domains (comma-separated)", value="")
designated_domains = [domain.strip() for domain in designated_domains_input.split(",") if domain.strip()]

# Process the file if uploaded
if uploaded_file:
    with st.spinner('Processing...'):
        top_domains, designated_domains_traffic, top_pages, full_domain_list = process_file(uploaded_file, designated_domains)

    st.success('Processing complete!')

    # Display results
    st.write('### Top 20 Domains by Estimated Traffic')
    st.dataframe(top_domains)

    st.write('### Designated Domains Traffic')
    if not designated_domains_traffic.empty:
        st.dataframe(designated_domains_traffic)
    else:
        st.write("No designated domains specified or not found in the data.")

    st.write('### Top 3 Pages for Top 20 Domains')
    st.dataframe(top_pages)

    # Provide download options
    st.write('### Download Results')
    top_domains_file = io.BytesIO()
    designated_domains_traffic_file = io.BytesIO()
    top_pages_file = io.BytesIO()
    full_domain_list_file = io.BytesIO()

    with pd.ExcelWriter(top_domains_file, engine='xlsxwriter') as writer:
        top_domains.to_excel(writer, index=False, sheet_name='Top Domains')
    with pd.ExcelWriter(designated_domains_traffic_file, engine='xlsxwriter') as writer:
        designated_domains_traffic.to_excel(writer, index=False, sheet_name='Designated Domains Traffic')
    with pd.ExcelWriter(top_pages_file, engine='xlsxwriter') as writer:
        top_pages.to_excel(writer, index=False, sheet_name='Top Pages')
    with pd.ExcelWriter(full_domain_list_file, engine='xlsxwriter') as writer:
        if 'Sort Order' in full_domain_list.columns:
            full_domain_list = full_domain_list.drop(columns=['Sort Order'])  # Drop 'Sort Order' column if it exists
        full_domain_list.to_excel(writer, index=False, sheet_name='Full Domain List')

    top_domains_file.seek(0)
    designated_domains_traffic_file.seek(0)
    top_pages_file.seek(0)
    full_domain_list_file.seek(0)

    st.download_button(label='Download Top Domains', data=top_domains_file, file_name='top_domains.xlsx')
    st.download_button(label='Download Designated Domains Traffic', data=designated_domains_traffic_file, file_name='designated_domains_traffic.xlsx')
    st.download_button(label='Download Top Pages', data=top_pages_file, file_name='top_pages.xlsx')
    st.download_button(label='Download Full Domain List', data=full_domain_list_file, file_name='full_domain_list.xlsx')

# Instructions
st.write('''
## Instructions
1. Download the sample template and fill in your keyword data.
2. Upload an Excel file with the following columns: 
   - Keywords
   - Keyword Rankings (1-100)
   - Keyword Search Volume
   - Ranked Domain Name (domain.com, www.domain.com, subdomain.domain.com, etc...)
   - Ranked Page URL (https://www.domain.com/page-url, subdomain.domain.com/page-url, etc...)
3. Enter any designated domains you want to be returned, separated by commas.
4. The tool will process the data and display the top 20 domains by estimated traffic, traffic for designated domains, and top 3 pages for the top 20 domains.
5. You can download the results as Excel files.
''')
