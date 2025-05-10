import os
import pandas as pd
import requests
import streamlit as st
from urllib.parse import quote
from utils import scrape_naukri, scrape_linkedin  # Importing from utils.py

st.title("Job Scraper")

# Select Job Platform
job_platform = st.selectbox("Select Job Platform", ["LinkedIn", "Naukri"])
job_role = st.text_input("Enter Job Role")

# User input for how many jobs to scrape (min 10)
num_jobs = st.number_input("Enter number of jobs to scrape", min_value=10, value=10)

if st.button("Scrape Jobs"):
    if job_role:
        with st.spinner("Scraping jobs, please wait..."):
            if job_platform == "LinkedIn":
                scraped_data = scrape_linkedin(job_role, num_jobs=num_jobs)
            else:
                scraped_data = scrape_naukri(job_role, num_jobs=num_jobs)

        if scraped_data:
            df = pd.read_csv(scraped_data)
            st.success(f"Scraping complete! {len(df)} jobs found.")
            st.dataframe(df)
            
            # Provide Download Option
            with open(scraped_data, "rb") as file:
                st.download_button(
                    label="Download CSV",
                    data=file,
                    file_name=os.path.basename(scraped_data),
                    mime="text/csv"
                )
        else:
            st.error("No jobs found. Try a different role or platform.")
    else:
        st.warning("Please enter a job role.")
