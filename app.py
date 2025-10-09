import requests, pandas as pd, numpy as np, plotly.graph_objects as go
import streamlit as st
from datetime import date

# ---------------- CONFIG ----------------
LOCATION_ID   = "f37fb2ae-bf24-44f1-9b81-61e6c0784840"     # Peakz Zeehaenkade
PLAYING_TIMES = [60, 90, 120]
URL = "https://api.foys.io/court-booking/public/api/v1/locations/search"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "x-federationid": "df82f4dd-fd87-4af5-9c2f-656fe1a44357",
    "x-organisationid": "df82f4dd-fd87-4af5-9c2f-656fe1a44357",
}

# ---------- UI ----------
st.set_page_config(page_title="Beachvolleybal Availability", layout="wide")
st.title("🏐 Beachvolleybal Availability (30-min blocks)")

chosen_date = st.date_input("Date", value=date.today())
indoor_only = st.checkbox("Indoor only", True)
name_filter = st.text_input("Name filter", "Beachvolleybal")

@st.cache_data(ttl=300)
def fetch_slots(d: date) -> pd.DataFrame:
    params = {
        "reservationTypeId": "6",
        "locationId": LOCATION_ID,
        "playingTimes[]": PLAYING_TIMES,
        "date": f"{d.isoformat()}T00:00:00.000Z",
    }
    r = requests.get(URL, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    df_raw = pd.json_normalize(r.json())
    inv_col = next((c for c in ("inventoryItemsTimeSlots", "inventorytimeslots") if c in df_raw.columns), None)
    if not inv_col:
        return pd.DataFrame()

    inv = [item for lst in df_raw[inv_col].dropna() for item in lst]
    slots = pd.DataFrame(inv).explode("timeSlots", ignore_index=True)
    slots = pd.concat([slots.drop(columns=["timeSlots"]), slots["timeSlots"].apply(pd.Series)], axis=1)
    slots["startTime"] = pd.to_datetime(slots["startTime"], errors="coerce")
    slots["endTime"]   = pd.to_datetime(slots["endTime"],   errors="coerce")
    slots["court"]     = slots["name"].fillna(slots["id"].astype(str))
    return slots

def plot(slots: pd.DataFrame, d: date):
    df = slots[slots["isAvailable"] == True].copy()
    if name_filter:
        df = df[df["name"].str.contains(name_filter, case=False, na=False)]
    if indoor_only:
        df = df[df["type"].str.contains("indoor", case=False, na=False)]
    if df.empty:
        st.info(f"No availability for {d}.")
        return

    def floor_30(ts):
        return ts - pd.to_timedelta(ts.minute % 30, "m") - pd.to_timedelta(ts.second, "s") - pd.to_timedelta(ts.microsecond, "us")

    t_open  = floor_30(df["startTime"].min())
    t_close = df["startTime"].min().normalize() + pd.Timedelta(hours=23)
    bins    = pd.date_range(t_open, t_close, freq="30min")
    if bins[-1] != t_close:
        bins = bins.append(pd.DatetimeIndex([t_close]))
    bin_st, bin_end = bins[:-1], bins[1:]
    courts = df["court"].unique()
    avail  = pd.DataFrame(False, index=courts, columns=bin_st)

    for _, r in df.iterrows():
        s, dur, c = r["startTime"], int(r.get("duration", 0)), r["court"]
        for k in range(int(np.ceil(dur / 30))):
            b = s + pd.Timedelta(minutes=30 * k)
            if b in avail.columns and b < t_close:
                avail.loc[c, b] = True

    bin_w = pd.Timedelta(minutes=30)
    x_centers = bin_st + bin_w / 2
    start_m = np.tile(bin_st.values, (len(avail.index), 1))
    end_m = np.tile((bin_st + bin_w).values, (len(avail.index), 1))
    custom = np.dstack([start_m, end_m])
    z = avail.astype(int).values

    fig = go.Figure(go.Heatmap(
        z=z, x=x_centers, y=avail.index,
        colorscale=[[0.0, "#d9dde6"], [1.0, "#2ecc71"]],
        showscale=False, zmin=0, zmax=1, xgap=0, ygap=1,
        customdata=custom,
        hovertemplate="<b>%{y}</b><br>%{customdata[0]|%H:%M}–%{customdata[1]|%H:%M}<extra></extra>"
    ))
    for x in pd.date_range(bin_st.min(), bin_end.max(), freq="60min"):
        fig.add_vline(x=x, line_width=1, line_color="#e6e9ef", opacity=0.7)
    fig.update_layout(
        title=f"Beachvolleybal availability — {d}",
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="#f7f8fa",
        font=dict(family="Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif", size=14),
        margin=dict(l=90, r=30, t=60, b=40),
        height=520
    )
    fig.update_xaxes(title="Time", tickformat="%H:%M", dtick=60 * 60 * 1000)
    fig.update_yaxes(title="Court", autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

with st.spinner("Loading…"):
    plot(fetch_slots(chosen_date), chosen_date)