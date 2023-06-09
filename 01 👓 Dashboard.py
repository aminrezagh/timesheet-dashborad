import streamlit as st
import pandas as pd
import numpy as np
from pytimeparse.timeparse import timeparse
import distinctipy
import pyodbc
from persiantools.jdatetime import JalaliDate

st.set_page_config(layout="centered", page_title="Package Man-Hour")

hide_streamlit_logo = """
            <style>
            footer {visibility: hidden;}
            </style>
            """

st.markdown(hide_streamlit_logo, unsafe_allow_html=True)

# defines default columns names for database

drop_cols = ['FullName',
            'Esteghrar_Code',
            'Esteghrar_Name',
            'CTC_ProjectOrDiscipline',
            'TimeSheetCostCenter_Name',
            'Estekhdam_Name',
            'Estekhdam_Code',
            'Tehran_Site',
            'MahalMohasebeZarfiat',
            'MahalMohasebeZarfiat_Name',
            'Date']

default_names = ["TimeSheetCostCenter_Name", 
                "CostCenterCode", 
                "LastName", 
                "FirstName", 
                "PersonnelCode", 
                "ActivityDescription", 
                "ActivityCode",
                "DisciplineZamineKari_Name", 
                "DisciplineZamineKari_Code", 
                "Basic", 
                "OverTime", 
                "Mission", 
                "Homework"]

new_names = ["cost_center", 
            "cost_center_id", 
            "last_name", 
            "first_name", 
            "pers_id", 
            "activity_name", 
            "activity_id",
            "discipline", 
            "discipline_code",
            "basic", 
            "over_time", 
            "mission", 
            "homework"]

def date_range(base_date):

    month = int(base_date[2:4])
    as_strided = np.lib.stride_tricks.as_strided
    iter_range = np.roll(as_strided(np.arange(12, 0, -1), (12, 2), np.arange(12, 0, -1).strides * 2), [month, month])
    dates = []
    
    for m in iter_range:

        if iter_range[0, 0] >= m[0] > 1:

            start_date = "01" + "%02d" %m[1] + base_date[-4:]
            end_date = "01" + "%02d" %m[0] + base_date[-4:]
            dates.append([end_date, start_date])
        
        elif (m[0] == 1) and (m[1] == 12):
            
            start_date = "01" + "%02d" %m[1] + str(int(base_date[-4:]) - 1)
            end_date = "01" + "%02d" %m[0] + base_date[-4:]
            dates.append([end_date, start_date])
        
        else:

            start_date = "01" + "%02d" %m[1] + str(int(base_date[-4:]) - 1)
            end_date = "01" + "%02d" %m[0] + str(int(base_date[-4:]) - 1)
            dates.append([end_date, start_date])

    return dates

def connect_to_db(db_con, base_date):

    data = []
    date_ranges = date_range(base_date)

    for i in range(12):
        try:
            col_name = date_ranges[0][1][4:] + ' - ' + date_ranges[0][1][2:4]
            df = pd.read_sql(f"EXEC TimeSheet @startDate = '{date_ranges[i][1]}', @endDate = '{date_ranges[i][0]}'", db_con).assign(date=col_name)
            data = data + [df]
        except:
            pass
    
    return pd.concat(data, ignore_index=True)

# extracts package section personnel ids from a text file
pckg_pers_id = [str(i) for i in sum(pd.read_csv("package_personnel_ids.txt").values.tolist(), [])]

@st.cache
def clean_and_categorize(df: pd.DataFrame):

    df = df.drop(drop_cols, axis=1, inplace=True)

    # renames the columns
    df.rename(columns=dict(zip(default_names, new_names)), inplace=True)
    df = df[new_names]
    df = df[df["discipline"] == "MA"]
    df = df[df["pers_id"].isin(pckg_pers_id)]
    df.drop("pers_id", axis=1, inplace=True)
     
    # converts time-format to number of hours
    time_cols = ["basic", "over_time", "mission", "homework"]
    df[time_cols] = df[time_cols].applymap(lambda t: timeparse(t, granularity="minutes")/3600)
    df.drop(["discipline", "discipline_code"], axis=1, inplace=True)

    # adds thursday column to dataframe
    df.loc[df['basic'] == 0, 'thursday'] = df["over_time"]
    df["thursday"].fillna(0, inplace=True)
    df.loc[df['cost_center_id'] == "OFF", 'off_time'] = df["basic"]
    df["off_time"].fillna(0, inplace=True)
    df["pers_name"] = df["last_name"].str.split().str.get(0).str.title() + ", " + df["first_name"].str.title()
    df.drop(["first_name", "last_name"], axis=1, inplace=True)

    # defines categories for different types of activies
    df.loc[df["activity_id"].str.contains("EVD", case=True), "activity_type"] = "VDR"
    df.loc[df["activity_name"].str.contains("clarification", case=False), "activity_type"] = "TCL"
    df.loc[df["activity_name"].str.contains("data sheet", case=False), "activity_type"] = "DSH"
    df.loc[df["activity_name"].str.contains("datasheet", case=False), "activity_type"] = "DSH"
    df.loc[df["activity_name"].str.contains("requisition", case=False), "activity_type"] = "MRQ"
    df.loc[df["activity_name"].str.contains("TBE", case=True), "activity_type"] = "TBE"
    df.loc[df["activity_name"].str.contains("service", case=False), "activity_type"] = "ITC"
    df.loc[df["activity_name"].str.contains("POR", case=True), "activity_type"] = "POR"
    df.loc[df["activity_name"].str.contains("coordination", case=False), "activity_type"] = "CRD"
    df.loc[df["activity_name"].str.contains("meeting", case=False), "activity_type"] = "MTG"
    df.loc[df["activity_name"].str.contains("mission", case=False), "activity_type"] = "MSN"
    df.loc[df["activity_name"].str.contains("contract", case=False), "activity_type"] = "CRW"
    df.loc[df["cost_center_id"].str.contains("off", case=False), "activity_type"] = "OFF"
    df["activity_type"].fillna("OTH", inplace=True)
    df["month"] = df["date"].astype(str).str[4:6]
    df["year"] = df["date"].astype(str).str[0:4]
    df.drop("date", axis=1, inplace=True)
    df["date"] = df["year"] + " - " + df["month"]
    df["total_basic"] = df["basic"] + df["mission"]
    df["total"] = df["total_basic"] + df["over_time"]
    df["net_working"] = df["total_basic"] - df["off_time"] + df["over_time"]

    st.session_state["acts"] = ["DSH", "ITC", "MRQ", "TCL", "TBE", "POR", "VDR", "MTG", "CRD", "MSN", "OFF", "CRW", "OTH"]
    
    return df

opts = {"Last 3 months": 0, "Last 6 months": 1, "Overall": 2}
base_date = JalaliDate.today().strftime("%d%m%Y")

def set_ss():

    st.session_state["ss_month_range"] = st.session_state["ms_month_range"]
    st.session_state["ss_act_range"] = st.session_state["ms_act_range"]
    st.session_state["ss_prj_range"] = st.session_state["ms_prj_range"]

def set_sb_ss():
    st.session_state["ss_range"] = opts[st.session_state["ms_range"]]

def opts_to_df(df, col, opt):
    if opt == 0:
        try:
            unique_col = list(sorted(df[col].unique()))
            return df[df[col].isin(unique_col[-3:])]
        except:
            return df
    elif opt == 1:
        try:
            unique_col = list(sorted(df[col].unique()))
            return df[df[col].isin(unique_col[-6:])]
        except:
            return df
    else:
        return df

if "ss_month_range" not in st.session_state:
    st.session_state["ss_month_range"] = []

if "ss_act_range" not in st.session_state:
    st.session_state["ss_act_range"] = []

if "ss_prj_range" not in st.session_state:
    st.session_state["ss_prj_range"] = []

if "ss_range" not in st.session_state:
    st.session_state["ss_range"] = 0


if "dataframe" and "df0" in st.session_state:

    st.selectbox(label="Duration", options=list(opts.keys()), index=st.session_state["ss_range"], key="ms_range", on_change=set_sb_ss)
    st.session_state["dataframe"] = opts_to_df(st.session_state["df0"] , "date", opts[st.session_state["ms_range"]])
    df = st.session_state["dataframe"]
    st.success("Database has been successfully retrieved.", icon="✔️")

else:

    header = st.empty()
    header.markdown('<h3 style="text-align: center;">Timesheet data is loading, please wait.</h3><br>', 
                    unsafe_allow_html=True)

    with st.spinner('Retrieving data ...'):
        
        con = pyodbc.connect("Driver={SQL Server Native Client 11.0};"
                  "Server=avevasql.main.com;"
                  "Database=EngineeringSystems;"
                  "UID=UDAMaster;"
                  "PWD=UDAMaster;", 
                  autocommit=True)

        df = connect_to_db(con, base_date)
        header.empty()

    if  set(default_names).issubset(set(df.columns)):
        st.success("Database has been successfully retrieved.", icon="✔️")
        df0 = clean_and_categorize(df)
        st.session_state["df0"] = df0
        st.selectbox(label="Duration", options=list(opts.keys()), index=st.session_state["ss_range"], key="ms_range", on_change=set_sb_ss)
        st.session_state["dataframe"] = opts_to_df(df0, "date", opts[st.session_state["ms_range"]])
        df = st.session_state["dataframe"]

    else:
        st.error("There was an error retrieving the database.", icon="❌")

try:

    months = list(sorted(df["date"].unique(), reverse=True))
    prjs = list(sorted(df["cost_center"].unique()))
    prj_ids = list(sorted(df["cost_center_id"].unique()))
    acts = ["DSH", "ITC", "MRQ", "TCL", "TBE", "POR", "VDR", "MTG", "CRD", "MSN", "OFF", "CRW", "OTH"]
    act_hex = ["#ff3a15", "#d42200", "#951700", "#4e8ef1", "#115fd8", "#0b3d8a", "#29AB87", "#FFA52C", "#FF69B4", "#ffff1a", "#FFFFCC", "#A689E1", "#D3D3D3"]

    dc = distinctipy.get_colors(len(prj_ids))
    hex_code = [distinctipy.get_hex(c) for c in dc]


    with st.sidebar:
        with st.form("Exclude"):

            st.multiselect("Months", months, default=st.session_state["ss_month_range"], key="ms_month_range")
            st.multiselect("Activities", acts, default=st.session_state["ss_act_range"], key="ms_act_range")
            st.multiselect("Projects", prjs, default=st.session_state["ss_prj_range"], key="ms_prj_range")

            filtered = st.form_submit_button("Exclude", on_click=set_ss)
            
    v1, v2, v3 = st.columns([1, 1, 1])
    with v2:
        st.metric("Overall Man-Hour (h)", round(df[~df["date"].isin(st.session_state["ss_month_range"]) & 
                                    ~df["cost_center"].isin(st.session_state["ss_prj_range"]) &
                                    ~df["activity_type"].isin(st.session_state["ss_act_range"])]["total"].sum()))
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.vega_lite_chart(df[~df["date"].isin(st.session_state["ss_month_range"]) & 
                        ~df["cost_center"].isin(st.session_state["ss_prj_range"]) &
                        ~df["activity_type"].isin(st.session_state["ss_act_range"])].groupby(["activity_type"]).sum().reset_index(), {
        "transform": [{"joinaggregate": [{"op": "sum", "field": "total", "as": "sumoftotal"}]},
                    {"calculate": "datum.total/datum.sumoftotal * 100", "as": "percent"}],
        "width": "container",
        "height": 400,
        "title": {"text": "OVERALL BREAKDOWN - ACTIVITIES", "offset": 30, "fontSize": "16", "anchor": "middle"},
        "mark":{"type": "arc", "innerRadius": 75, "stroke": "#fff", 
                "tooltip": {"signal": "{'Total (h)': round(datum.total), 'Percent (%)': round(datum.percent), 'Activity': datum.activity_type}"}},
        "encoding": {
            "theta": {"field": "percent", "type": "quantitative"},
            "color": {"field": "activity_type", "type": "quantitative", "type": "nominal", "scale": {"domain": acts, "range": act_hex}}},
         "config": {"legend": {"orient": "right", "layout": {"right": {"anchor": "middle"}}}}           
         }, use_container_width=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.vega_lite_chart(df[~df["date"].isin(st.session_state["ss_month_range"]) &
                        ~df["cost_center"].isin(st.session_state["ss_prj_range"]) &
                        ~df["activity_type"].isin(st.session_state["ss_act_range"])].groupby(["cost_center_id", "cost_center"]).sum().reset_index(), {
        "transform": [{"joinaggregate": [{"op": "sum", "field": "total", "as": "sumoftotal"}]},
                    {"calculate": "datum.total/datum.sumoftotal * 100", "as": "percent"}],
        "width": "container",
        "height": 500,
        "title": {"text": "OVERALL BREAKDOWN - PROJECTS", "offset": 20, "fontSize": "16", "anchor": "middle"},
        "mark":{"type": "bar", "stroke": "#fff", 
                "tooltip": {"signal": "{'Total (h)': round(datum.total), 'Percent (%)': round(datum.percent), 'Cost Center': datum.cost_center, 'Cost Center ID': datum.cost_center_id}"}},
        "encoding": {
            "x": {"field": "cost_center_id", "type": "nominal", "sort": "-y"},
            "y": {"field": "percent", "type": "quantitative"},
            "color": {"field": "cost_center_id", "type": "nominal", "scale": {"domain": prj_ids, "range": hex_code}}},
         "config": {"legend": {"orient": "right", "layout": {"right": {"anchor": "middle"}}},
                    "view": {"stroke": ""}}           
         }, use_container_width=True)

except NameError:
    pass