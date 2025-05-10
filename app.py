import streamlit as st

st.set_page_config(layout="wide")
job_scraper=st.Page("Job_Scraper.py",title="Job Scraper")
prof_scraper=st.Page("Profile_Scraper.py",title="Profile Scraper")
pages=st.navigation([prof_scraper,job_scraper])
pages.run()