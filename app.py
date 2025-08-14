
import streamlit as st
import pandas as pd
import numpy as np
import math
from datetime import date

st.set_page_config(page_title="ILP Planner — GLA4-first", layout="wide")

def thousands(x):
    try:
        return f"{x:,.0f}"
    except Exception:
        return x

st.title("ILP Projection Planner (GE GLA4-first)")

with st.sidebar:
    st.header("Product")
    product = st.selectbox("Pick product", ["Great Eastern — GREAT Life Advantage 4 (default)", "Custom ILP"])
    st.caption("Defaults are prefilled for GLA4. You can override anything below.")

    st.markdown("---")
    st.header("Client & Policy")
    colA, colB = st.columns(2)
    with colA:
        curr_age = st.number_input("Current age (next birthday)", min_value=0, max_value=99, value=27, step=1)
        gender = st.selectbox("Gender", ["Male", "Female"])
    with colB:
        smoker = st.selectbox("Smoker status", ["Non-smoker", "Smoker"])
        start_month = st.number_input("Policy start month", min_value=1, max_value=12, value=8, step=1)
    start_year = st.number_input("Policy start year (YYYY)", min_value=1900, max_value=2100, value=2025, step=1)
    annual_premium = st.number_input("Annual premium (S$)", min_value=0.0, value=2379.0, step=100.0, format="%.2f")
    curr_av = st.number_input("Current account value (S$)", min_value=0.0, value=0.0, step=100.0, format="%.2f")

    st.markdown("---")
    st.header("Coverage (Sum Assured)")
    base_sa = st.number_input("Death/TPD base Sum Assured (S$)", min_value=0.0, value=100000.0, step=10000.0, format="%.0f")
    ci_sa = st.number_input("CI Rider (late stage) Sum Assured (S$)", min_value=0.0, value=100000.0, step=10000.0, format="%.0f")
    eci_sa = st.number_input("ECI Rider (early/intermediate/late) Sum Assured (S$)", min_value=0.0, value=100000.0, step=10000.0, format="%.0f")

    st.markdown("---")
    st.header("Funding")
    holiday_year = st.number_input("Premium holiday: stop after policy year", min_value=0, max_value=99, value=0, step=1, help="0 = no holiday (lifetime pay). When set >0, premiums stop after that policy anniversary.")
    iir = st.slider("Illustrated investment return (net of fund fees) % p.a.", min_value=-5.0, max_value=10.0, value=4.0, step=0.5)

st.subheader("Charges & Rules (prefilled from GLA4 — editable)")

with st.expander("Premium charges & rewards", expanded=True):
    st.write("Premium charge on basic premium (as % of annual basic premium)")
    default_sched = pd.DataFrame({
        "policy_year_from":[1,2,3,4,7],
        "policy_year_to":[1,2,3,6,200],
        "premium_charge_pct":[76.0,51.0,26.0,4.0,0.0]
    })
    charges_df = st.data_editor(default_sched, num_rows="dynamic", use_container_width=True)
    reward_pct = st.number_input("Premium reward from year 10 onward (% of premium)", min_value=0.0, value=2.0, step=0.5)
    reward_requires_9yrs = st.checkbox("Require first 9 years fully paid before reward applies", value=True)

with st.expander("Policy fees & non-lapse", expanded=True):
    policy_fee_monthly = st.number_input("Policy fee (S$ per month)", min_value=0.0, value=5.0, step=1.0)
    nlg_first_10yrs = st.checkbox("Non-lapse guarantee active (first 10 policy years if premiums paid & no withdrawal)", value=True)
    ph_charge_first2 = st.checkbox("Premium-holiday charge in first 2 policy years = Annualised Premium (deducted via units)", value=True)

with st.expander("Cost of Insurance (COI) tables", expanded=True):
    st.caption("Upload CSVs to override defaults. Columns: age,male_nonsmoker,male_smoker,female_nonsmoker,female_smoker")
    base_file = st.file_uploader("Base plan COI table (per $1,000 Net Sum Assured, per annum)", type=["csv"], key="basecoi")
    ci_file = st.file_uploader("CI Advantage Rider COI (per $1,000 SA, per annum)", type=["csv"], key="cicoi")
    eci_file = st.file_uploader("CI Advantage Plus Rider COI (per $1,000 SA, per annum)", type=["csv"], key="ecicoi")

    def load_default(name):
        return pd.read_csv(name)
    if base_file is not None:
        base_coi = pd.read_csv(base_file)
    else:
        base_coi = load_default("gla4_base_coi_sample.csv")

    if ci_file is not None:
        ci_coi = pd.read_csv(ci_file)
    else:
        ci_coi = load_default("rider_ci_adv_sample.csv")

    if eci_file is not None:
        eci_coi = pd.read_csv(eci_file)
    else:
        eci_coi = load_default("rider_ci_adv_plus_sample.csv")

    st.write("Base COI sample (edit externally to use full table):")
    st.dataframe(base_coi.head(12), use_container_width=True)

def lookup_rate(age, table, gender, smoker):
    col = f"{gender.lower()}_{'smoker' if smoker=='Smoker' else 'nonsmoker'}"
    if age in table["age"].values:
        return float(table.loc[table["age"]==age, col].iloc[0])
    ages = table["age"].values
    if age < ages.min():
        return float(table.loc[table["age"]==ages.min(), col].iloc[0])
    if age > ages.max():
        return float(table.loc[table["age"]==ages.max(), col].iloc[0])
    lower = ages[ages<=age].max()
    upper = ages[ages>=age].min()
    r_low = float(table.loc[table["age"]==lower, col].iloc[0])
    r_up = float(table.loc[table["age"]==upper, col].iloc[0])
    if upper==lower:
        return r_low
    return r_low + (r_up-r_low)*(age-lower)/(upper-lower)

def premium_charge_pct_for_year(py, schedule_df):
    row = schedule_df[(schedule_df["policy_year_from"]<=py) & (schedule_df["policy_year_to"]>=py)]
    if row.empty:
        return 0.0
    return float(row["premium_charge_pct"].iloc[0])

run = st.button("Run projection")
if run:
    start_age = curr_age - (date.today().year - start_year)
    if start_age < 0 or start_age > curr_age:
        start_age = curr_age

    rows = []
    account_value = curr_av
    debt = 0.0
    paid_years = 0
    for py in range(1, 121):
        age = start_age + (py-1)
        if age > 100:
            break

        pay_premium = (holiday_year==0) or (py <= holiday_year)
        gross_prem = annual_premium if pay_premium else 0.0

        charge_pct = premium_charge_pct_for_year(py, charges_df)
        prem_charge = gross_prem * charge_pct/100.0
        reward = 0.0
        if reward_pct>0 and py>=10 and (not reward_requires_9yrs or paid_years>=9):
            reward = gross_prem * reward_pct/100.0
        net_alloc = gross_prem - prem_charge + reward

        policy_fee_annual = policy_fee_monthly * 12.0
        ph_charge = 0.0
        if ph_charge_first2 and (py in [1,2]) and not pay_premium:
            ph_charge = annual_premium

        net_sa = max(base_sa - max(account_value,0.0), 0.0)
        base_rate = lookup_rate(age, base_coi, gender, smoker)
        base_coi_annual = net_sa/1000.0 * base_rate

        ci_rate = lookup_rate(age, ci_coi, gender, smoker) if ci_sa>0 else 0.0
        eci_rate = lookup_rate(age, eci_coi, gender, smoker) if eci_sa>0 else 0.0
        ci_coi_annual = (ci_sa/1000.0)*ci_rate
        eci_coi_annual = (eci_sa/1000.0)*eci_rate

        total_charges = policy_fee_annual + ph_charge + base_coi_annual + ci_coi_annual + eci_coi_annual

        invest_base = account_value + 0.5*net_alloc - 0.5*total_charges
        growth = invest_base * (iir/100.0)

        end_av = account_value + net_alloc - total_charges + growth

        lapsed = False
        if end_av <= 0:
            if nlg_first_10yrs and py<=10 and pay_premium:
                debt += -end_av
                end_av = 0.0
            else:
                lapsed = True
                end_av = 0.0

        rows.append({
            "Policy Year": py,
            "Age": age,
            "Premium In": gross_prem,
            "Prem Charge": prem_charge,
            "Reward": reward,
            "Policy Fee": policy_fee_annual,
            "Holiday Charge": ph_charge,
            "Base COI": base_coi_annual,
            "CI COI": ci_coi_annual,
            "ECI COI": eci_coi_annual,
            "Total Charges": total_charges,
            "Net Alloc": net_alloc,
            "Net Growth": growth,
            "End Account Value": end_av,
            "Net Debt (NLG)": debt,
            "Lapsed?": lapsed
        })

        if lapsed:
            break
        account_value = end_av
        if pay_premium and gross_prem>0:
            paid_years += 1

    df = pd.DataFrame(rows)
    money_cols = ["Premium In","Prem Charge","Reward","Policy Fee","Holiday Charge","Base COI","CI COI","ECI COI","Total Charges","Net Alloc","Net Growth","End Account Value","Net Debt (NLG)"]
    styled = df.style.format({c: "{:,.0f}".format for c in money_cols})
# Hide the index (new + old pandas compatible)
try:
    styled = styled.hide(axis="index")       # pandas >= 1.4
except Exception:
    try:
        styled = styled.hide_index()         # older pandas fallback
    except Exception:
        pass

    st.subheader("Yearly Projection")
    st.dataframe(styled, use_container_width=True, height=520)

    csv = df.to_csv(index=False)
    st.download_button("Download projection CSV", data=csv, file_name="ilp_projection.csv", mime="text/csv")

st.markdown("---")
st.caption("Tip: Upload full COI CSVs for base and riders to get accurate charges. The bundled files are samples for demo and interpolation.")
