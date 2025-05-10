import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import urllib.parse

from urllib.parse import quote
import os


def scrape_linkedin(job_role, location="India", num_jobs=10):
    job_list = []
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    
    encoded_role = job_role.replace(" ", "%20")
    count = 0
    page_num = 0

    while count < num_jobs:
        start = page_num * 25
        list_url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_role}&location={location}&start={start}&f_E=2&f_TPR=r86400"
        
        response = requests.get(list_url)
        if response.status_code != 200:
            print(f"Failed to retrieve job list for page {page_num}")
            break
        
        list_soup = BeautifulSoup(response.text, "html.parser")
        page_jobs = list_soup.find_all("li")

        for job in page_jobs:
            if count >= num_jobs:
                break

            apply_link_tag = job.find("a", class_="base-card__full-link")
            if apply_link_tag:
                apply_link = apply_link_tag["href"]
                job_ID = apply_link.split('?')[0][-10:]
                job_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_ID}"
                
                job_response = requests.get(job_url)
                if job_response.status_code != 200:
                    continue
                
                job_soup = BeautifulSoup(job_response.text, "html.parser")

                job_post = {
                    "Job ID": job_ID,
                    "Job Title": job_soup.find("h2", class_="top-card-layout__title").text.strip() if job_soup.find("h2", class_="top-card-layout__title") else None,
                    "Company Name": job_soup.find("a", class_="topcard__org-name-link").text.strip() if job_soup.find("a", class_="topcard__org-name-link") else None,
                    "Location": job_soup.find("span", class_="topcard__flavor--bullet").text.strip() if job_soup.find("span", class_="topcard__flavor--bullet") else None,
                    "time_posted": job_soup.find("span", class_="posted-time-ago__text").text.strip() if job_soup.find("span", class_="posted-time-ago__text") else None,
                    "job_description": job_soup.find("div", class_="description__text--rich").text.strip() if job_soup.find("div", class_="description__text--rich") else None,
                    "Apply Link": apply_link
                    
                }
                
                job_list.append(job_post)
                count += 1

        page_num += 1
        if len(page_jobs) == 0:
            break  # Stop if no more jobs available

    driver.quit()

    df = pd.DataFrame(job_list)
    csv_file_path = "linkedin_jobs.csv"
    df.to_csv(csv_file_path, index=False)
    return csv_file_path if not df.empty else None

def scrape_naukri(job_role, num_jobs=10):
    options = Options()
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)

    path_role = job_role.replace(" ", "-")
    query_role = urllib.parse.quote(job_role)
    url = f"https://www.naukri.com/{path_role}-jobs?k={query_role}&experience=2"
    driver.get(url)

    jobs_list = []
    count, new_index, i = num_jobs, 1, 0

    while i < count:
        try:
            heading_xpath = f'(//*[@class="srp-jobtuple-wrapper"])[{new_index}]//h2/a'
            link_xpath = f'(//*[@class="srp-jobtuple-wrapper"])[{new_index}]//h2/a'
            subheading_xpath = f'(//*[@class="srp-jobtuple-wrapper"])[{new_index}]/div/div[2]//a'
            experience_xpath = f'(//*[@class="srp-jobtuple-wrapper"])[{new_index}]/div/div[3]/div/span[1]/span/span'
            salary_xpath = f'(//*[@class="srp-jobtuple-wrapper"])[{new_index}]/div/div[3]/div/span[2]/span/span'
            location_xpath = f'(//*[@class="srp-jobtuple-wrapper"])[{new_index}]/div/div[3]/div/span[3]/span/span'
            
            heading = wait.until(EC.presence_of_element_located((By.XPATH, heading_xpath))).text
            link = wait.until(EC.presence_of_element_located((By.XPATH, link_xpath))).get_attribute('href')
            subheading = wait.until(EC.presence_of_element_located((By.XPATH, subheading_xpath))).text
            experience = wait.until(EC.presence_of_element_located((By.XPATH, experience_xpath))).text
            salary = wait.until(EC.presence_of_element_located((By.XPATH, salary_xpath))).text if wait.until(EC.presence_of_element_located((By.XPATH, salary_xpath))) else "Not Disclosed"
            location = wait.until(EC.presence_of_element_located((By.XPATH, location_xpath))).text if wait.until(EC.presence_of_element_located((By.XPATH, location_xpath))) else "Not Available"
            
            # Navigate to job detail page to extract job description
            driver.get(link)
            job_desc_xpath = '//*[contains(@class, "styles_JDC__dang-inner-html__h0K4t")]'
            try:
                job_description = wait.until(EC.presence_of_element_located((By.XPATH, job_desc_xpath))).text
            except:
                job_description = "Not Available"
            driver.back()
            
            jobs_list.append({
                'Job Role': heading,
                'Company Name': subheading,
                'Vacancy Link': link,
                'Experience Needed': experience,
                'Salary': salary,
                'Location': location,
                'Job Description': job_description
            })
            
            new_index += 1
            i += 1
        except Exception:
            new_index += 1

    driver.quit()
    
    df = pd.DataFrame(jobs_list)
    csv_file_path = os.path.join(os.path.dirname(__file__), 'naukri_jobs.csv')
    df.to_csv(csv_file_path, index=False)
    return csv_file_path if not df.empty else None
