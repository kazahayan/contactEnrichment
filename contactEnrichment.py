import requests
import streamlit as st
import pandas as pd
import time

from nameparser import HumanName
from datetime import datetime

st.set_page_config(
    page_title="Contact Enrichment",
    page_icon="random",
    layout="wide"
)

# name parser function
# def parse_name(name):
#     human_name = HumanName(name)
#     return pd.Series([human_name.first, human_name.middle, human_name.last])

def parse_name(name):
    if pd.isna(name):
        return pd.Series([None, None, None])
    human_name = HumanName(name)
    return pd.Series([human_name.first, human_name.middle, human_name.last])

# function to enrich contacts
def enrich_contact(row):
    url = "https://devapi.endato.com/Contact/Enrich"

    payload = {
        "FirstName": row['firstName'],
        "MiddleName": row["middleName"],
        "LastName": row['lastName'],
        "Address": {
            "addressLine1": row["addressLine1"],
            "addressLine2": row["addressLine2"]
        }
    }

    headers = {
        "accept": "application/json",
        "galaxy-ap-name": key_name,
        "galaxy-ap-password": key_password,
        "galaxy-search-type": search_type,
        "content-type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    response_json = response.json()

    # phone columns
    connected_phones = [
        phone for phone in response_json.get('person', {}).get('phones', [])
        if phone.get('isConnected', False)
    ]

    if connected_phones:
        most_recent_phone = max(
            connected_phones,
            key=lambda x: datetime.strptime(x['lastReportedDate'], '%m/%d/%Y')
        )
        phone_number = most_recent_phone['number']
        phone_type = most_recent_phone['type']
        last_reported_date = most_recent_phone['lastReportedDate']
    else:
        phone_number, phone_type, last_reported_date = None, None, None

    # age
    age = response_json.get('person', {}).get('age', None)

    # only validated emails
    validated_emails = [
        email['email'] for email in response_json.get('person', {}).get('emails', [])
        if email.get('isValidated', False)
    ]
    emails_string = ', '.join(validated_emails) if validated_emails else None

    return phone_number, phone_type, last_reported_date, age, emails_string

st.title("Contact Enrichment")

# API info
key_name = st.sidebar.text_input(label="Key Name", type="password")
key_password = st.sidebar.text_input(label="Key Password", type="password")
search_type = 'DevAPIContactEnrich'

uploaded_file = st.sidebar.file_uploader("", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    df['Address ID'] = df['Address ID'].astype(int).astype(str)
    df['ZIP Code'] = df['ZIP Code'].astype(int).astype(str)

    # there is discrepancy between our reports for whether two is spelled out or integer
    if 'Address Line 2' in df.columns:
        df.rename(columns={'Address Line 2': 'Address Line Two'}, inplace=True)

    uploaded_columns = df.columns.tolist()

    rows = len(df)
    st.subheader(f"Uploaded Contacts ({rows})")
    st.dataframe(df)

    # transformations before calling Endato API
    # changing column name here since I had to run Chat GPT API to get cleaned version of the name
    df[['firstName', 'middleName', 'lastName']] = df['Primary Addressee Name'].apply(parse_name)

    # changing column name here since I had to run Chat GPT API to get cleaned version of the name
    # df[['firstName', 'middleName', 'lastName']] = df['cleaned_name'].apply(parse_name)
    df['addressLine1'] = df.apply(
        lambda x: x['Formatted Address Line One'] if pd.isnull(x['Address Line Two']) or x[
            'Address Line Two'] == '' else x['Formatted Address Line One'] + ' ' + x['Address Line Two'],
        axis=1
    )
    df['addressLine2'] = df['City'].astype(str) + ', ' + df['State'].astype(str) + ' ' + df['ZIP Code'].astype(str)

    # to look at columns of pre-processed dataframe
    # st.dataframe(df)

    # cost estimator
    total_rows = len(df)
    est_cost = total_rows * 0.10
    est_cost_formatted = f"${est_cost:,.2f}"
    st.sidebar.subheader(f"Estimated Cost: {est_cost_formatted}")

    if st.sidebar.button("Enrich Contacts"):
        start_time = time.time()
        enriched_data = df.apply(enrich_contact, axis=1, result_type='expand')
        df[['phoneNumber', 'phoneType', 'phoneLastReportedDate', 'age', 'validatedEmails']] = enriched_data
        end_time = time.time()
        api_duration = end_time - start_time

        # stats on matching
        # Calculate the total cost based on matched results
        matched_rows = df[['phoneNumber', 'validatedEmails']].notnull().any(axis=1).sum()
        actual_cost = matched_rows * 0.10
        actual_cost_formatted = f"${actual_cost:,.2f}"

        matched_phones = df['phoneNumber'].notnull().sum()
        matched_emails = df['validatedEmails'].notnull().sum()

        percent_matched_phones = (matched_phones / total_rows) * 100
        percent_matched_emails = (matched_emails / total_rows) * 100

        # Display the enriched DataFrame
        st.subheader("Enriched Contacts")

        # col1, col2, col3, col4 = st.columns(4)
        # col1.metric(label="Matched Rows", value=matched_rows)
        # col2.metric(label="Actual Cost", value=actual_cost_formatted)
        # col3.metric(label="Matched Phone Numbers", value=f"{percent_matched_phones:.0f}%")
        # col4.metric(label="Matched Emails", value=f"{percent_matched_emails:.0f}%")

        col1, col2, col3 = st.columns(3)
        col1.metric(label="Run Time", value=f"{api_duration:.2f} Seconds")
        col2.metric(label="Matched Phone Numbers", value=f"{percent_matched_phones:.0f}%")
        col3.metric(label="Matched Emails", value=f"{percent_matched_emails:.0f}%")

        enriched_columns = [
            'age',
            'phoneNumber',
            'phoneType',
            'phoneLastReportedDate',
            'validatedEmails'
        ]
        final_columns = uploaded_columns + enriched_columns
        df = df[final_columns]
        st.dataframe(df)