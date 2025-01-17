import boto3.resources
import boto3.resources.factory
import boto3.session
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

import os
import json
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

account = os.getenv("AWS_ACCOUNT_NAME")
bucket_name = f"{account}-github-audit-dashboard"

st.set_page_config(page_title="GitHub Audit Dashboard", page_icon="./src/branding/ONS-symbol_digital.svg", layout="wide")
st.logo("./src/branding/ONS_Logo_Digital_Colour_Landscape_Bilingual_RGB.svg")

@st.cache_resource
def get_s3_client() -> boto3.client:
    session = boto3.Session()
    s3 = session.client("s3")
    return s3


def get_table_from_s3(s3, bucket_name: str, object_name: str) -> pd.DataFrame | str:
    """
        Gets a JSON file from an S3 bucket and returns it as a Pandas DataFrame.

        Args:
            s3: A boto3 S3 client.
            bucket_name: The name of the S3 bucket.
            object_name: The name of the object in the S3 bucket.
        Returns:
            A Pandas DataFrame containing the data from the JSON file.
            or
            A string containing an error message.
    """
    try:
        response = s3.get_object(Bucket=bucket_name, Key=object_name)
    except ClientError as e:
        return (f"An error occurred when getting {object_name} data: {e}")
    
    json_data = json.loads(response["Body"].read().decode("utf-8"))

    return pd.json_normalize(json_data)

@st.cache_data
def load_data(load_date: datetime.date):
    """
        Loads the data from the S3 bucket and returns it as a Pandas DataFrame.

        This function is cached using Streamlit's @st.cache_data decorator.

        Args:
            load_date (date): The date and time the data was loaded.
    """
    
    s3 = get_s3_client()

    df_repositories = get_table_from_s3(s3, bucket_name, "repositories.json")
    df_secret_scanning = get_table_from_s3(s3, bucket_name, "secret_scanning.json")
    df_dependabot = get_table_from_s3(s3, bucket_name, "dependabot.json")

    return df_repositories, df_secret_scanning, df_dependabot

@st.cache_data
def load_file(filename: str) -> dict:
    """Loads a JSON file and returns it as a dictionary.

    This function is cached using Streamlit's @st.cache_data decorator.

    Args:
        filename (str): The path of the JSON file to load.

    Returns:
        dict: The JSON file loaded as a dictionary.
    """
    with open(filename, "r") as f:
        file_json = json.load(f)

    return file_json


loading_date = datetime.now()

# Rounds loading_date to the nearest 10 minutes
# This means the cached data will refresh every 10 minutes

loading_date = loading_date.strftime("%Y-%m-%d %H:%M")
loading_date = loading_date[:-1] + "0"

df_repositories, df_secret_scanning, df_dependabot = load_data(loading_date)

rulemap = load_file("rulemap.json")

if type(df_repositories) == str:
    st.error(df_repositories)
    st.stop()

if type(df_secret_scanning) == str:
    st.error(df_secret_scanning)
    st.stop()

if type(df_dependabot) == str: 
    st.error(df_dependabot)
    st.stop()


col1, col2 = st.columns([0.8, 0.2])

col1.title(":blue-background[GitHub Audit Dashboard]")

col2.image("./src/branding/ONS_Logo_Digital_Colour_Landscape_Bilingual_RGB.png")


# Tabs for Repository Analysis and SLO Analysis Sections
repository_tab, slo_tab = st.tabs(["Repository Analysis", "SLO Analysis"])

# Repository Analysis Section

with repository_tab:
    st.header(":blue-background[Repository Analysis]")
    
    # Gets the rules from the repository DataFrame
    rules = df_repositories.columns.to_list()[3:]

    # Cleans the rules to remove the "checklist." prefix
    for i in range(len(rules)):
        rules[i] = rules[i].replace("checklist.", "")

    # Renames the columns of the DataFrame
    df_repositories.columns = ["repository", "repository_type", "url"] + rules

    # Uses streamlit's session state to store the selected rules
    # This is so that selected rules persist with other inputs (i.e the preset buttons)
    if "selected_rules" not in st.session_state:
        st.session_state["selected_rules"] = []
        
        for rule in rulemap:
            st.session_state["selected_rules"].append(rule["name"])

    # Preset Buttons
    
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Security Preset", use_container_width=True):
            st.session_state["selected_rules"] = []

            for rule in rulemap:
                if rule["is_security_rule"]:
                    st.session_state["selected_rules"].append(rule["name"])

    with col2:
        if st.button("Policy Preset", use_container_width=True):
            st.session_state["selected_rules"] = []

            for rule in rulemap:
                if rule["is_policy_rule"]:
                    st.session_state["selected_rules"].append(rule["name"])

    selected_rules = st.multiselect("Select rules", rules, st.session_state["selected_rules"])

    repository_type = st.selectbox("Repository Type", ["all", "public", "private", "internal"], key="repos_repo_type")

    # If any rules are selected, populate the rest of the dashboard
    if len(selected_rules) != 0:
        rules_to_exclude = []

        for rule in rules:
            if rule not in selected_rules:
                rules_to_exclude.append(rule)

        # Remove the columns for rules that aren't selected
        df_repositories = df_repositories.drop(columns=rules_to_exclude)

        # Filter the DataFrame by the selected repository type
        if repository_type != "all":
            df_repositories = df_repositories.loc[df_repositories["repository_type"] == repository_type]

        # Create a new column to check if the repository is compliant or not
        # If any check is True, the repository is non-compliant
        df_repositories["is_compliant"] = df_repositories.any(axis="columns", bool_only=True)
        df_repositories["is_compliant"] = df_repositories["is_compliant"].apply(lambda x: not x)

        # Create a new column to count the number of rules broken
        df_repositories["rules_broken"] = df_repositories[selected_rules].sum(axis="columns")
        
        # Sort the DataFrame by the number of rules broken and the repository name
        df_repositories = df_repositories.sort_values(by=["rules_broken", "repository"], ascending=[False, True])

        # Rename the columns of the DataFrame
        df_repositories.columns = ["Repository", "Repository Type", "URL"] + selected_rules + ["Is Compliant", "Rules Broken"]

        st.subheader(":blue-background[Repository Compliance]")

        # Display the rules that are being checked
        st.write("Checking for the following rules:")

        col1, col2 = st.columns(2)

        for i in range(0, len(selected_rules)):
            if i % 2 == 0:
                col1.write(f"- {selected_rules[i].replace('_', ' ').title()}")
            else:
                col2.write(f"- {selected_rules[i].replace('_', ' ').title()}")

        with st.expander("See Rule Descriptions"):
            st.subheader("Rule Descriptions")
            
            for rule in rulemap:
                st.write(f"- {rule['name'].replace('_', ' ').title()}: {rule['description']}")

            st.caption("**Note:** All rules are interpreted from ONS' [GitHub Usage Policy](https://officenationalstatistics.sharepoint.com/sites/ONS_DDaT_Communities/Software%20Engineering%20Policies/Forms/AllItems.aspx?id=%2Fsites%2FONS%5FDDaT%5FCommunities%2FSoftware%20Engineering%20Policies%2FSoftware%20Engineering%20Policies%2FApproved%2FPDF%2FGitHub%20Usage%20Policy%2Epdf&parent=%2Fsites%2FONS%5FDDaT%5FCommunities%2FSoftware%20Engineering%20Policies%2FSoftware%20Engineering%20Policies%2FApproved%2FPDF).")

        st.divider()

        col1, col2 = st.columns(2)

        # Create a dataframe summarising the compliance of the repositories
        df_compliance = df_repositories["Is Compliant"].value_counts().reset_index()

        df_compliance["Is Compliant"] = df_compliance["Is Compliant"].apply(lambda x: "Compliant" if x else "Non-Compliant")

        df_compliance.columns = ["Compliance", "Number of Repositories"]

        # Create a pie chart to show the compliance of the repositories
        with col1:
            fig = px.pie(df_compliance, values="Number of Repositories", names="Compliance")

            st.plotly_chart(fig)

        # Display metrics for the compliance of the repositories
        with col2:
            compliant_repositories = df_compliance.loc[df_compliance["Compliance"] == "Compliant", "Number of Repositories"]

            if len(compliant_repositories) == 0:
                compliant_repositories = 0

            noncompliant_repositories = df_compliance.loc[df_compliance["Compliance"] == "Non-Compliant", "Number of Repositories"]
            
            if len(noncompliant_repositories) == 0:
                noncompliant_repositories = 0

            st.metric("Compliant Repositories", compliant_repositories)
            st.metric("Non-Compliant Repositories", noncompliant_repositories)
            st.metric("Average Rules Broken", int(df_repositories["Rules Broken"].mean().round(0)))

            rule_frequency = df_repositories[selected_rules].sum()
            st.metric("Most Common Rule Broken", rule_frequency.idxmax().replace("_", " ").title())

        # Display the repositories that are non-compliant
        st.subheader(":blue-background[Non-Compliant Repositories]")

        selected_repo = st.dataframe(
            df_repositories[["Repository", "Repository Type", "Rules Broken"]].loc[df_repositories["Is Compliant"] == 0],
            on_select="rerun",
            selection_mode=["single-row"],
            use_container_width=True,
            hide_index=True
        )

        # If a non-compliant repository is selected, display the rules that are broken
        if len(selected_repo["selection"]["rows"]) > 0:
            selected_repo = selected_repo["selection"]["rows"][0]

            selected_repo = df_repositories.iloc[selected_repo]

            failed_checks = selected_repo[3:-2].loc[selected_repo[3:-2] == 1]

            col1, col2 = st.columns([0.8, 0.2])

            col1.subheader(f":blue-background[{selected_repo["Repository"]} ({selected_repo["Repository Type"].capitalize()})]")
            col2.write(f"[Go to Repository]({selected_repo['URL']})")

            st.subheader("Rules Broken:")      

            for check in failed_checks.index:
                st.write(f"- {check.replace('_', ' ').title()}")  
        else:
            st.caption("Select a repository for more information.")

    # If no rules are selected, prompt the user to select at least one rule
    else:
        st.write("Please select at least one rule.")

# SLO Analysis Section

with slo_tab:
    st.header(":blue-background[SLO Analysis]")

    st.subheader(":blue-background[Secret Scanning Alerts]")
    st.write("Alerts open for more than 5 days.")

    # Rename the columns of the DataFrame
    df_secret_scanning.columns = ["Repository Name", "Type", "Secret", "Link"]

    # Group the DataFrame by the repository name and the type
    df_secret_scanning_grouped = df_secret_scanning.groupby(["Repository Name", "Type"]).count().reset_index()

    # Rename the columns of the grouped DataFrame
    df_secret_scanning_grouped.columns = ["Repository Name", "Type", "Number of Secrets", "Link"]

    col1, col2 = st.columns([0.8, 0.2])

    with col1:
        selected_secret = st.dataframe(
            df_secret_scanning_grouped[["Repository Name", "Type", "Number of Secrets"]],
            use_container_width=True,
            on_select="rerun",
            selection_mode=["single-row"],
            hide_index=True
        )

    with col2:
        st.metric("Total Alerts", df_secret_scanning_grouped["Number of Secrets"].sum())

    # If an alert is selected, display the secrets that are open
    if len(selected_secret["selection"]["rows"]) > 0:
        selected_secret = selected_secret["selection"]["rows"][0]

        selected_secret = df_secret_scanning_grouped.iloc[selected_secret]

        st.subheader(f":blue-background[{selected_secret['Repository Name']} ({selected_secret['Type']})]")

        st.dataframe(
            df_secret_scanning.loc[df_secret_scanning["Repository Name"] == selected_secret["Repository Name"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Link": st.column_config.LinkColumn(
                    "Link",
                    display_text="Go to Alert"
                )
            }
        ) 
    else:
        st.caption("Select a repository for more information.") 

    st.divider()

    st.subheader(":blue-background[Dependabot Alerts]")
    st.write("Alerts open for more than 5 days (Critical), 15 days (High), 60 days (Medium), 90 days (Low).")    

    # Rename the columns of the DataFrame
    df_dependabot.columns = ["Repository Name", "Type", "Dependency", "Advisory", "Severity", "Days Open", "Link"]

    col1, col2 = st.columns([0.7, 0.3])

    severity = col1.multiselect("Alert Severity", ["critical", "high", "medium", "low"], ["critical", "high", "medium", "low"])
    repo_type = col2.selectbox("Repository Type", ["all", "public", "private", "internal"], key="dependabot_repo_type")
    minimum_days = st.slider("Minimum Days Open", 0, df_dependabot["Days Open"].max(), 0)

    # If any severity levels are selected, populate the rest of the dashboard
    if len(severity) > 0:
        # Filter the DataFrame by the selected severity levels and the minimum days open
        df_dependabot = df_dependabot.loc[df_dependabot["Severity"].isin(severity) & (df_dependabot["Days Open"] >= minimum_days)]

        # Filter the DataFrame by the selected repository type
        if repo_type != "all":
            df_dependabot = df_dependabot.loc[df_dependabot["Type"] == repo_type]

        # Map the severity to a weight for sorting
        df_dependabot["Severity Weight"] = df_dependabot["Severity"].map({"critical": 4, "high": 3, "medium": 2, "low": 1})

        # Group the DataFrame by the repository name and the type
        df_dependabot_grouped = df_dependabot.groupby(["Repository Name", "Type"]).agg({"Dependency": "count", "Severity Weight": "max", "Days Open": "max"}).reset_index()
        
        # Create a new column to map the severity weight to a severity level for the grouped data
        df_dependabot_grouped["Severity"] = df_dependabot_grouped["Severity Weight"].map({4: "Critical", 3: "High", 2: "Medium", 1: "Low"})

        # Rename the columns of the grouped DataFrame
        df_dependabot_grouped.columns = ["Repository Name", "Type", "Number of Alerts", "Severity Weight", "Max Days Open", "Max Severity"]

        # Sort the grouped DataFrame by the severity weight and the days open
        df_dependabot_grouped.sort_values(by=["Severity Weight", "Max Days Open"], ascending=[False, False], inplace=True)

        col1, col2 = st.columns([0.7, 0.3])

        with col1:
            # Create a dataframe summarising the alerts by severity
            df_dependabot_severity_grouped = df_dependabot.groupby("Severity").count().reset_index()[["Severity", "Repository Name"]]
            df_dependabot_severity_grouped.columns = ["Severity", "Number of Alerts"]

            # Create a pie chart to show the alerts by severity
            fig = px.pie(
                df_dependabot_severity_grouped,
                names="Severity",
                values="Number of Alerts",
                title="Number of Alerts by Severity"
            )

            st.plotly_chart(fig)


        with col2:
            st.metric("Total Alerts", df_dependabot_grouped["Number of Alerts"].sum())
            st.metric("Average Days Open", int(df_dependabot_grouped["Max Days Open"].mean().round(0)))

            st.metric("Number of Repositories", df_dependabot_grouped["Repository Name"].count())
            st.metric("Avg. Alerts per Repository", int(df_dependabot_grouped["Number of Alerts"].mean().round(0)))

        selected_repo = st.dataframe(
            df_dependabot_grouped[["Repository Name", "Type", "Number of Alerts", "Max Severity", "Max Days Open"]],
            use_container_width=True,
            on_select="rerun",
            selection_mode=["single-row"],
            hide_index=True
        )

        # If a repository is selected, display the alerts that are open for that repository
        if len(selected_repo["selection"]["rows"]) > 0:
            selected_repo = selected_repo["selection"]["rows"][0]

            selected_repo = df_dependabot_grouped.iloc[selected_repo]

            st.subheader(f":blue-background[{selected_repo['Repository Name']} ({selected_repo['Type']})]")

            st.dataframe(
                # Get the alerts for the selected repository, sort by severity weight and days open and display the columns
                df_dependabot.loc[df_dependabot["Repository Name"] == selected_repo["Repository Name"]].sort_values(by=["Severity Weight", "Days Open"], ascending=[False, False])[["Repository Name", "Dependency", "Advisory", "Severity", "Days Open", "Link"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Link": st.column_config.LinkColumn(
                        "Link",
                        display_text="Go to Alert"
                    )
                }
            )

        else:
            st.caption("Select a repository for more information.")

    # If no severity levels are selected, prompt the user to select at least one severity level
    else:
        st.write("Please select at least one severity level.")