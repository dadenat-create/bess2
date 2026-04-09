import streamlit as st
import pandas as pd
import pulp
import math
import plotly.graph_objects as go

st.set_page_config(page_title="Ora Energy BESS Optimizer", layout="wide")

# =========================
# FUNZIONE OTTIMIZZAZIONE
# =========================
def optimize_bess(prices, params):

    T = len(prices)
    eta = math.sqrt(params["eta_rt"])

    model = pulp.LpProblem("BESS", pulp.LpMaximize)

    charge = pulp.LpVariable.dicts("charge", range(T), lowBound=0)
    discharge = pulp.LpVariable.dicts("discharge", range(T), lowBound=0)
    soc = pulp.LpVariable.dicts("soc", range(T),
                               lowBound=params["SoC_min"],
                               upBound=params["SoC_max"])

    model += pulp.lpSum([
        prices[t]*discharge[t] - prices[t]*charge[t] - params["c_deg"]*discharge[t]
        for t in range(T)
    ])

    for t in range(T):
        model += charge[t] <= params["P_charge_max"]
        model += discharge[t] <= params["P_discharge_max"]

        if t == 0:
            model += soc[t] == params["SoC_0"] + eta*charge[t] - discharge[t]/eta
        else:
            model += soc[t] == soc[t-1] + eta*charge[t] - discharge[t]/eta

    model += soc[T-1] == params["SoC_0"]

    model.solve(pulp.PULP_CBC_CMD(msg=0))

    df = pd.DataFrame({
        "Prezzo": prices,
        "Carica": [charge[t].varValue for t in range(T)],
        "Scarica": [discharge[t].varValue for t in range(T)],
        "SoC": [soc[t].varValue for t in range(T)]
    })

    df["Profitto"] = df["Prezzo"]*df["Scarica"] - df["Prezzo"]*df["Carica"]

    return df


# =========================
# SIDEBAR PARAMETRI
# =========================
st.sidebar.header("⚙️ Parametri BESS")

params = {
    "C_max": st.sidebar.number_input("Capacità", value=5.0),
    "SoC_0": st.sidebar.number_input("SoC iniziale", value=0.25),
    "SoC_min": st.sidebar.number_input("SoC min", value=0.25),
    "SoC_max": st.sidebar.number_input("SoC max", value=4.75),
    "P_charge_max": st.sidebar.number_input("P carica", value=2.5),
    "P_discharge_max": st.sidebar.number_input("P scarica", value=2.5),
    "eta_rt": st.sidebar.number_input("Efficienza (%)", value=90.0)/100,
    "c_deg": st.sidebar.number_input("Costo degradazione", value=0.0)
}

# =========================
# FILE INPUT
# =========================
st.title("⚡ Ora Energy BESS Optimizer")

uploaded_file = st.file_uploader("Carica file prezzi annuale", type=["xlsx"])

if uploaded_file:
    df_raw = pd.read_excel(uploaded_file)

    prices = pd.to_numeric(df_raw.iloc[:,0], errors="coerce")
    prices = prices.dropna().astype(float).tolist()

   df = df.reset_index(drop=True)
df["Datetime"] = pd.date_range(
    start="2025-01-01",
    periods=len(df),
    freq="H"
)

    df = pd.DataFrame({"Datetime": dates, "Prezzo": prices})
    df["Data"] = df["Datetime"].dt.date
    df["Mese"] = df["Datetime"].dt.to_period("M")

    # =========================
    # OTTIMIZZAZIONE GIORNALIERA
    # =========================
    results_list = []

    for day, group in df.groupby("Data"):
        res = optimize_bess(group["Prezzo"].tolist(), params)
        res["Datetime"] = group["Datetime"].values
        results_list.append(res)

    df_res = pd.concat(results_list)

    df_res["Data"] = pd.to_datetime(df_res["Datetime"]).dt.date
    df_res["Mese"] = pd.to_datetime(df_res["Datetime"]).dt.to_period("M")

    # =========================
    # KPI
    # =========================
    daily = df_res.groupby("Data").agg({
        "Profitto":"sum",
        "Prezzo":["max","min"]
    })

    daily.columns = ["Profitto","Pmax","Pmin"]
    daily["Spread"] = daily["Pmax"] - daily["Pmin"]

    monthly = df_res.groupby("Mese")["Profitto"].sum()

    # =========================
    # DASHBOARD
    # =========================
    st.header("📊 Dashboard")

    col1, col2 = st.columns(2)

    col1.metric("💰 Ricavo totale anno (€)", round(df_res["Profitto"].sum(),2))
    col2.metric("📅 Ricavo medio giornaliero (€)", round(daily["Profitto"].mean(),2))

    # =========================
    # GRAFICI DASHBOARD
    # =========================

    fig_month = go.Figure()
    fig_month.add_trace(go.Bar(x=monthly.index.astype(str), y=monthly.values))
    fig_month.update_layout(title="Ricavi mensili")
    st.plotly_chart(fig_month, use_container_width=True)

    fig_spread = go.Figure()
    fig_spread.add_trace(go.Scatter(y=daily["Spread"]))
    fig_spread.update_layout(title="Spread giornaliero")
    st.plotly_chart(fig_spread, use_container_width=True)

    # =========================
    # SELEZIONE MESE
    # =========================
    selected_month = st.selectbox("Seleziona mese", monthly.index.astype(str))

    df_month = df_res[df_res["Mese"].astype(str) == selected_month]

    st.subheader(f"📅 Dettaglio mese: {selected_month}")

    # =========================
    # GRAFICO MESE
    # =========================
    fig_m = go.Figure()
    fig_m.add_trace(go.Scatter(y=df_month["Prezzo"], name="Prezzo"))
    fig_m.add_trace(go.Bar(y=df_month["Carica"], name="Carica"))
    fig_m.add_trace(go.Bar(y=df_month["Scarica"], name="Scarica"))
    st.plotly_chart(fig_m, use_container_width=True)

    # =========================
    # SELEZIONE GIORNO
    # =========================
    selected_day = st.selectbox("Seleziona giorno", df_month["Data"].unique())

    df_day = df_res[df_res["Data"] == selected_day]

    st.subheader(f"📆 Giorno: {selected_day}")

    # =========================
    # GRAFICI GIORNO
    # =========================

    fig_day = go.Figure()
    fig_day.add_trace(go.Scatter(y=df_day["Prezzo"], name="Prezzo"))
    fig_day.add_trace(go.Bar(y=df_day["Carica"], name="Carica"))
    fig_day.add_trace(go.Bar(y=df_day["Scarica"], name="Scarica"))
    st.plotly_chart(fig_day, use_container_width=True)

    fig_soc = go.Figure()
    fig_soc.add_trace(go.Scatter(y=df_day["SoC"], name="SoC"))
    fig_soc.update_layout(title="SoC 24h")
    st.plotly_chart(fig_soc, use_container_width=True)

else:
    st.info("Carica un file Excel per iniziare")
