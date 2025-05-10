import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import re
import requests
import fitz  # PyMuPDF
import pdfplumber
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime
from dotenv import load_dotenv
from linkedin_api import Linkedin
import os


scraped_data_df=pd.DataFrame()

# Custom CSS for styling and positioning
st.markdown(
    """
    <style>
    .header-container {
        display: flex;
        align-items: center;
        padding: 10px;
        border-bottom: 2px solid #e6e6e6; /* Adds a divider line below the header */
        margin-bottom: 20px; /* Space between header and content */
    }
    .header-container img {
        width: 150px;
        height: auto;
        margin-right: 10px;
    }
    .header-container .title {
        font-size: 24px;
        font-weight: bold;
        color: #262730;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Header section: Logo and title side by side
st.markdown(
    """
    <div class="header-container">
        <img src="https://mma.prnewswire.com/media/900145/Imarticus_Logo.jpg?p=publish" alt="Imarticus Logo">
        <div class="title">Career Placement Monitoring</div>
    </div>
    """,
    unsafe_allow_html=True
)
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()
options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)

# Vertical page division using columns
col1, col2 = st.columns(2)  # Splits the page into two vertical sections

# Left column: Resized Illustration
with col1:
    st.subheader("LinkedIn Login")
# Streamlit input for email and password
    EMAIL = st.text_input("## Enter your LinkedIn username or email:")
    PASSWORD = st.text_input("## Enter your password:", type="password")
    if EMAIL and PASSWORD:
    # Proceed with authentication if both fields are filled
        api = Linkedin(EMAIL, PASSWORD, debug=True)

    SERVICE_ACCOUNT_FILE = "credentials.json"
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

    # Authenticate with Google Sheets
    try:
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        client = gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Failed to authenticate Google Sheets API. Error: {e}")
        st.stop()

    # Function to extract LinkedIn URLs from a given cell (text or HTML)
    def extract_hyperlinks(cell):
        linkedin_urls = []
        if isinstance(cell, str):  # Ensure the cell contains a string.
            linkedin_urls = re.findall(r'https?://(?:www\.)?linkedin\.com/in/[^\s]+', cell)
        return linkedin_urls

    # Function to extract LinkedIn URLs from PDF
    def extract_linkedin_from_pdf(pdf_file):
        linkedin_urls = []
        with fitz.open(pdf_file) as my_pdf_file:
            for page_number in range(1, len(my_pdf_file) + 1):
                page = my_pdf_file[page_number - 1]
                for pdf_link in page.links():
                    if "uri" in pdf_link:
                        url = pdf_link["uri"]
                        if re.match(r'https?://(?:www\.)?linkedin\.com/in/[^\s]+', url):
                            linkedin_urls.append(url)
        return linkedin_urls

    def split_experience(row):
        # If no experience data is found, return "No Experience Data" for both companies
        if row['Experience'] == "No experience data found.":
            return {"Company 1": "No Experience Data", "Company 2": "No Experience Data found" }

        # Split the experience data by newlines to separate different companies
        companies = row['Experience'].split("\n")

        # Create a dictionary to store the company data
        company_dict = {}

        # Assign each company data to a Company column
        for i, company in enumerate(companies):
            company_dict[f"Company {i + 1}"] = company.strip()  # Strip any extra spaces

        return company_dict

    # Function to process the DataFrame and split experience columns
    def process_data(df, api):
        # Split the experience data and add new columns
        experience_split = df.apply(split_experience, axis=1)
        experience_part = pd.DataFrame(experience_split.tolist())

        # Merge the new experience columns into the original DataFrame
        df = pd.concat([df, experience_part], axis=1)

        # Fill any NaN values with "No Experience Data found"
        df.fillna("No Experience Data found", inplace=True)

        return df

    # Updated classify_experience function
    def classify_experience(row, company_columns):
        # Check if Batch Start Date and Batch End Date are valid
        if pd.isna(row['Batch Start Date']) or pd.isna(row['Batch End Date']):
            return "Invalid Batch Dates"

        try:
            batch_start_date = datetime.strptime(row['Batch Start Date'], "%m %Y")
            batch_end_date = datetime.strptime(row['Batch End Date'], "%m %Y")
        except ValueError:
            return "Invalid Batch Date Format"

        # Loop through the experience columns (e.g., Company 1, Company 2, etc.)
        for company_col in company_columns:
            # If the company column is empty or has 'Not placed' data, classify as "No experience"
            if pd.isna(row.get(company_col, None)) or 'Not placed' in str(row.get(company_col, '')):
                return "No experience"

            # Extract the experience data from the company column
            experience_data = row[company_col]

            # Try to extract the start date from the experience data
            try:
                start_date_str = experience_data.split("Start Date:")[1].split(",")[0].strip()
                start_date = datetime.strptime(start_date_str, "%m %Y")
            except (IndexError, ValueError):
                return "Not placed"  # If unable to extract the start date, return "Not placed"

            # Classify based on the batch dates
            if start_date < batch_start_date:
                return "Pre Imarticus"
            elif start_date > batch_end_date:
                return "Post Imarticus"
            elif batch_start_date <= start_date <= batch_end_date:
                return "Self Placed"
            else:
                return "Unknown"  # In case no condition is met, you can use "Unknown"

        # If no valid experience is found after checking all columns
        return "No experience data found"


# Right column: Additional content
with col2:
    st.subheader("Data Input")
    file_type = st.radio("Choose the source of data:", ("Google Sheets", "Excel File"))

    # Convert Batch Start Date and Batch End Date to datetime format with only month and year (month as number)
    def convert_to_month_year(df, date_column_name):
        try:
            df[date_column_name] = pd.to_datetime(df[date_column_name], errors='coerce').dt.to_period('M').dt.strftime('%m %Y')
        except Exception as e:
            logging.warning(f"Error converting {date_column_name}: {e}")
        return df

    if file_type == "Google Sheets":
        SHEET_ID = st.text_input("## Enter the Google Sheet URL (found in the sheet URL):")

        if SHEET_ID:
            try:
                sheet = gc.open_by_key(SHEET_ID).sheet1
                cell_values = sheet.get_all_values()
                data = pd.DataFrame(cell_values[1:], columns=cell_values[0])
                st.dataframe(data)

                # LinkedIn URL Extraction Logic
                df_linkedin = pd.DataFrame(columns=["Unique ID", "Student Name", "Batch Start Date", "Batch End Date", "Link"])

                # Process each row for LinkedIn URLs
                for _, row in data.iterrows():
                    linkedin_urls_collected = []
                    for cell in row:
                        linkedin_urls = extract_hyperlinks(cell)
                        linkedin_urls_collected.extend(linkedin_urls)

                    # Look for Google Drive links to extract PDFs
                    for cell in row:
                        if isinstance(cell, str) and 'drive.google.com' in cell:
                            try:
                                if "id=" in cell:
                                    file_id = cell.split("id=")[1].split("&")[0]
                                elif "/d/" in cell:
                                    file_id = cell.split("/d/")[1].split("/")[0]
                                else:
                                    continue

                                download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                                response = requests.get(download_url)
                                if response.status_code == 200:
                                    with open("temp.pdf", "wb") as f:
                                        f.write(response.content)

                                    linkedin_urls_from_pdf = extract_linkedin_from_pdf("temp.pdf")
                                    linkedin_urls_collected.extend(linkedin_urls_from_pdf)
                            except Exception as e:
                                logging.error(f"Error processing Google Drive link: {e}")

                    linkedin_urls_collected = list(set(linkedin_urls_collected))  # Remove duplicates

                    # Add LinkedIn URLs to DataFrame
                    if linkedin_urls_collected:
                        for linkedin_url in linkedin_urls_collected:
                            temp_df = pd.DataFrame({
                                "Unique ID": [row['Unique ID']],
                                "Student Name": [row['Student Name']],
                                "Batch Start Date": [row['Batch Start Date']],
                                "Batch End Date": [row['Batch End Date']],
                                "Link": [linkedin_url]
                            })
                            df_linkedin = pd.concat([df_linkedin, temp_df], ignore_index=True)
                    else:
                        temp_df = pd.DataFrame({
                            "Unique ID": [row['Unique ID']],
                            "Student Name": [row['Student Name']],
                            "Batch Start Date": [row['Batch Start Date']],
                            "Batch End Date": [row['Batch End Date']],
                            "Link": ["No LinkedIn URL found"]
                        })
                        df_linkedin = pd.concat([df_linkedin, temp_df], ignore_index=True)

                # LinkedIn username extraction for the Google Sheets data
                df_linkedin["Username"] = df_linkedin["Link"].apply(lambda link: re.search(r'linkedin\.com/in/([^/]+)/?', link).group(1) if pd.notnull(link) and "linkedin.com/in/" in link else "Invalid URL")

                # Apply date conversion to 'Batch Start Date' and 'Batch End Date' after LinkedIn extraction
                df_linkedin = convert_to_month_year(df_linkedin, "Batch Start Date")
                df_linkedin = convert_to_month_year(df_linkedin, "Batch End Date")

                # Initialize LinkedIn API
                api = None
                if EMAIL and PASSWORD:
                    try:
                        api = Linkedin(EMAIL, PASSWORD)
                    except Exception as e:
                        st.error(f"Failed to authenticate with LinkedIn API. Please check your credentials. Error: {e}")
                else:
                    st.warning("Please enter your LinkedIn credentials to enable profile scraping.")

                if api:
                    data1 = []
                    with st.spinner("Scraping LinkedIn profiles..."):
                        for _, row in df_linkedin.iterrows():
                            username = row["Username"]
                            url = row["Link"]
                            name_text = row["Student Name"]
                            batch_start_date = row["Batch Start Date"]
                            batch_end_date = row["Batch End Date"]
                            unique_id = row["Unique ID"]

                            if username != "Invalid URL":
                                try:
                                    profile = api.get_profile(username)
                                    experience_data = profile.get("experience", [])
                                    experience_text = "\n".join(
                                        [
                                            f"Company: {exp.get('companyName', 'N/A')}, Title: {exp.get('title', 'N/A')}, "
                                            f"Start Date: {exp.get('timePeriod', {}).get('startDate', {}).get('month', 'N/A')} "
                                            f"{exp.get('timePeriod', {}).get('startDate', {}).get('year', 'N/A')}, "
                                            f"End Date: {exp.get('timePeriod', {}).get('endDate', {}).get('month', 'Present')} "
                                            f"{exp.get('timePeriod', {}).get('endDate', {}).get('year', 'N/A')}"
                                            for exp in experience_data
                                        ]
                                    ) if experience_data else "No experience data found."
                                except Exception as e:
                                    logging.warning(f"API failed for {username}: {e}")
                                    experience_text = "API Error"
                            else:
                                experience_text = "Invalid URL"

                            data1.append({
                                "Unique ID": unique_id,
                                "Student Name": name_text,
                                "Batch Start Date": batch_start_date,
                                "Batch End Date": batch_end_date,
                                "LinkedIn URL": url,
                                "Experience": experience_text
                            })

                    # Display the scraped data
                    scraped_data_df = pd.DataFrame(data1)
                    scraped_data_df = process_data(scraped_data_df, api)

                    # Apply experience classification
                    company_columns = ["Company 1", "Company 2"]  # Modify based on your actual column names
                    scraped_data_df["Experience Classification"] = scraped_data_df.apply(
                        lambda row: classify_experience(row, company_columns), axis=1
                    )

                    st.subheader("Scraped LinkedIn Data")
                    st.dataframe(scraped_data_df)

                    # Function to convert DataFrame to CSV
                    def convert_df_to_csv(df):
                        return df.to_csv(index=False).encode("utf-8")

                    # Convert DataFrame to CSV
                    csv_data = convert_df_to_csv(scraped_data_df)

                    # Add download button
                    st.download_button(
                        label="Download Scraped Data as CSV",
                        data=csv_data,
                        file_name="scraped_data.csv",
                        mime="text/csv",
                    )

            except Exception as e:
                st.error(f"Error accessing Google Sheets: {e}")

    # For Excel File input
    elif file_type == "Excel File":
        excel_file = st.file_uploader("Upload Excel file", type=["xls", "xlsx"])

        if excel_file:
            try:
                data = pd.read_excel(excel_file)
                st.dataframe(data)

                # LinkedIn URL Extraction Logic
                df_linkedin = pd.DataFrame(columns=["Unique ID", "Student Name", "Batch Start Date", "Batch End Date", "Link"])

                # Process each row for LinkedIn URLs
                for _, row in data.iterrows():
                    linkedin_urls_collected = []
                    for cell in row:
                        linkedin_urls = extract_hyperlinks(cell)
                        linkedin_urls_collected.extend(linkedin_urls)

                    # Look for Google Drive links to extract PDFs
                    for cell in row:
                        if isinstance(cell, str) and 'drive.google.com' in cell:
                            try:
                                if "id=" in cell:
                                    file_id = cell.split("id=")[1].split("&")[0]
                                elif "/d/" in cell:
                                    file_id = cell.split("/d/")[1].split("/")[0]
                                else:
                                    continue

                                download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                                response = requests.get(download_url)
                                if response.status_code == 200:
                                    with open("temp.pdf", "wb") as f:
                                        f.write(response.content)

                                    linkedin_urls_from_pdf = extract_linkedin_from_pdf("temp.pdf")
                                    linkedin_urls_collected.extend(linkedin_urls_from_pdf)
                            except Exception as e:
                                logging.error(f"Error processing Google Drive link: {e}")

                    linkedin_urls_collected = list(set(linkedin_urls_collected))  # Remove duplicates

                    # Add LinkedIn URLs to DataFrame
                    if linkedin_urls_collected:
                        for linkedin_url in linkedin_urls_collected:
                            temp_df = pd.DataFrame({
                                "Unique ID": [row['Unique ID']],
                                "Student Name": [row['Student Name']],
                                "Batch Start Date": [row['Batch Start Date']],
                                "Batch End Date": [row['Batch End Date']],
                                "Link": [linkedin_url]
                            })
                            df_linkedin = pd.concat([df_linkedin, temp_df], ignore_index=True)
                    else:
                        temp_df = pd.DataFrame({
                            "Unique ID": [row['Unique ID']],
                            "Student Name": [row['Student Name']],
                            "Batch Start Date": [row['Batch Start Date']],
                            "Batch End Date": [row['Batch End Date']],
                            "Link": ["No LinkedIn URL found"]
                        })
                        df_linkedin = pd.concat([df_linkedin, temp_df], ignore_index=True)

                # LinkedIn username extraction for the Google Sheets data
                df_linkedin["Username"] = df_linkedin["Link"].apply(lambda link: re.search(r'linkedin\.com/in/([^/]+)/?', link).group(1) if pd.notnull(link) and "linkedin.com/in/" in link else "Invalid URL")

                # Apply date conversion to 'Batch Start Date' and 'Batch End Date' after LinkedIn extraction
                df_linkedin = convert_to_month_year(df_linkedin, "Batch Start Date")
                df_linkedin = convert_to_month_year(df_linkedin, "Batch End Date")

                # Initialize LinkedIn API
                api = None
                if EMAIL and PASSWORD:
                    try:
                        api = Linkedin(EMAIL, PASSWORD)
                    except Exception as e:
                        st.error(f"Failed to authenticate with LinkedIn API. Please check your credentials. Error: {e}")
                else:
                    st.warning("Please enter your LinkedIn credentials to enable profile scraping.")

                if api:
                    data1 = []
                    with st.spinner("Scraping LinkedIn profiles..."):
                        for _, row in df_linkedin.iterrows():
                            username = row["Username"]
                            url = row["Link"]
                            name_text = row["Student Name"]
                            batch_start_date = row["Batch Start Date"]
                            batch_end_date = row["Batch End Date"]
                            unique_id = row["Unique ID"]

                            if username != "Invalid URL":
                                try:
                                    profile = api.get_profile(username)
                                    experience_data = profile.get("experience", [])
                                    experience_text = "\n".join(
                                        [
                                            f"Company: {exp.get('companyName', 'N/A')}, Title: {exp.get('title', 'N/A')}, "
                                            f"Start Date: {exp.get('timePeriod', {}).get('startDate', {}).get('month', 'N/A')} "
                                            f"{exp.get('timePeriod', {}).get('startDate', {}).get('year', 'N/A')}, "
                                            f"End Date: {exp.get('timePeriod', {}).get('endDate', {}).get('month', 'Present')} "
                                            f"{exp.get('timePeriod', {}).get('endDate', {}).get('year', 'N/A')}"
                                            for exp in experience_data
                                        ]
                                    ) if experience_data else "No experience data found."
                                except Exception as e:
                                    logging.warning(f"API failed for {username}: {e}")
                                    experience_text = "API Error"
                            else:
                                experience_text = "Invalid URL"

                            data1.append({
                                "Unique ID": unique_id,
                                "Student Name": name_text,
                                "Batch Start Date": batch_start_date,
                                "Batch End Date": batch_end_date,
                                "LinkedIn URL": url,
                                "Experience": experience_text
                            })

                    # Display the scraped data
                    scraped_data_df = pd.DataFrame(data1)
                    scraped_data_df = process_data(scraped_data_df, api)

                    # Apply experience classification
                    company_columns = ["Company 1", "Company 2"]  # Modify based on your actual column names
                    scraped_data_df["Experience Classification"] = scraped_data_df.apply(
                        lambda row: classify_experience(row, company_columns), axis=1
                    )
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")
    driver.quit()
st.subheader("Placement Report")
st.dataframe(scraped_data_df)

                    # Function to convert DataFrame to CSV
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")

                    # Convert DataFrame to CSV
csv_data = convert_df_to_csv(scraped_data_df)

                    # Add download button
st.download_button(
    label="Download Scraped Data as CSV",
    data=csv_data,
    file_name="scraped_data.csv",
    mime="text/csv",
    )
def generate_summary_report(scraped_data_df):
    """
    Generates and displays a summary report for experience classification with names included.
    """
    if "Experience Classification" in scraped_data_df.columns and "Student Name" in scraped_data_df.columns:
        summary_report = scraped_data_df.groupby(["Experience Classification"])\
                                      .agg({"Student Name": list, "Experience Classification": "count"})\
                                      .rename(columns={"Experience Classification": "Count"})\
                                      .reset_index()
        
        st.subheader("Summary Report: Experience Classification")
        st.dataframe(summary_report)
        
        
        
        
        # Prepare CSV data for download
        csv = summary_report.to_csv(index=False).encode('utf-8')
        st.download_button(label="Download Summary Report", 
                           data=csv, 
                           file_name="experience_summary_report.csv", 
                           mime="text/csv")
    else:
        st.warning("Required columns not found in the DataFrame.")

search_query = st.text_input("Search for specific records:")
if search_query:
                # Filter the data to search across all columns
    filtered_data = scraped_data_df[scraped_data_df.astype(str).apply(lambda row: search_query.lower() in row.to_string().lower(), axis=1)]
    if not filtered_data.empty:
        st.write("Search Results:")
        st.write(filtered_data)
    else:
        st.write("No matching records found.")