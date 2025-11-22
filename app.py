import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- Configuration ---
st.set_page_config(page_title="Kaspa Tracker", layout="wide")
KASPA_API_BASE = "https://api.kaspa.org"
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"

# --- Helper Functions ---

@st.cache_data(ttl=300)
def get_transactions(address):
    """Fetches full transaction history for a Kaspa address."""
    url = f"{KASPA_API_BASE}/addresses/{address}/full-transactions"
    params = {"limit": 500, "resolve_previous_outpoints": "light"} # Fetching up to 500 for now
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching transactions: {e}")
        return []

import database

# Initialize DB
database.init_db()

@st.cache_data(ttl=3600)
def get_kaspa_price_history(start_date, end_date):
    """Fetches Kaspa price history, using DB cache and filling gaps from API."""
    
    # 1. Check DB for existing data
    df_db = database.get_prices_from_db(start_date, end_date)
    
    # 2. Identify missing dates
    missing_dates = database.get_missing_dates(start_date, end_date)
    
    if missing_dates:
        # CoinGecko Free Tier Limit: 365 days
        limit_date = datetime.now() - timedelta(days=365)
        
        fetch_start = min(missing_dates)
        fetch_end = max(missing_dates)
        
        if fetch_start < limit_date:
            # Check if we actually have data in DB for this range (maybe imported from Excel)
            # The get_missing_dates function already checks DB. 
            # So if we are here, it means we are TRULY missing data in DB for dates < 365 days ago.
            
            # However, get_missing_dates returns a list of specific missing days.
            # If we have gaps in the old history that Excel didn't cover, we can't fetch them from API.
            
            st.warning(f"Note: Price history older than 365 days is not available on the free CoinGecko plan and was not found in the Excel backup. Fetching available data from {limit_date.date()}.")
            fetch_start = limit_date
            
        # If after clamping, start is after end (i.e. all missing dates are too old), skip fetch
        if fetch_start > fetch_end:
            st.info("All missing dates are older than 365 days. Skipping price fetch.")
        else:
            st.info(f"Fetching missing price data from {fetch_start.date()} to {fetch_end.date()}...")
            
            # CoinGecko expects UNIX timestamp for range
            from_ts = int(fetch_start.timestamp())
            to_ts = int((fetch_end + timedelta(days=1)).timestamp()) # +1 day to ensure coverage
            
            url = f"{COINGECKO_API_BASE}/coins/kaspa/market_chart/range"
            params = {
                "vs_currency": "usd",
                "from": from_ts,
                "to": to_ts
            }
            
            try:
                response = requests.get(url, params=params)
                if response.status_code == 429:
                    st.error("CoinGecko API rate limit exceeded. Please wait a minute.")
                elif response.status_code == 400 or response.status_code == 401: # Handle specific API errors
                     st.error(f"CoinGecko API Error: {response.json().get('error', 'Unknown error')}")
                else:
                    response.raise_for_status()
                    data = response.json()
                    prices = data.get("prices", [])
                    
                    if prices:
                        df_new = pd.DataFrame(prices, columns=["timestamp", "price"])
                        df_new["timestamp"] = pd.to_datetime(df_new["timestamp"], unit="ms").dt.normalize()
                        
                        # Save to DB
                        database.save_prices_to_db(df_new)
                        
                        # Re-query DB to get the complete dataset (cleanest way to merge)
                        df_db = database.get_prices_from_db(start_date, end_date)
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching price history: {e}")
            
    # Rename columns to match expected format
    if not df_db.empty:
        df_db = df_db.rename(columns={"date": "timestamp"})
        
    return df_db

def get_current_price():
    """Fetches the current live price of Kaspa."""
    url = f"{COINGECKO_API_BASE}/simple/price"
    params = {
        "ids": "kaspa",
        "vs_currencies": "usd"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("kaspa", {}).get("usd", 0)
    except:
        return 0

def process_data(transactions, address, price_df):
    """Processes transactions to calculate balance and merge with price."""
    if not transactions:
        return pd.DataFrame()

    tx_list = []
    for tx in transactions:
        timestamp = tx.get("block_time")
        if timestamp:
            dt = datetime.fromtimestamp(timestamp / 1000)
        else:
            continue # Skip if no timestamp

        tx_id = tx.get("transaction_id")
        
        # Calculate Net Amount for the address
        sent = 0
        received = 0
        
        # Check Inputs (Sent)
        if "inputs" in tx:
            for inp in tx["inputs"]:
                if inp.get("previous_outpoint_address") == address:
                    sent += inp.get("previous_outpoint_amount", 0)
        
        # Check Outputs (Received)
        if "outputs" in tx:
            for out in tx["outputs"]:
                if out.get("script_public_key_address") == address:
                    received += out.get("amount", 0)
        
        # Convert Sompi to KAS
        sent_kas = sent / 100_000_000
        received_kas = received / 100_000_000
        net_amount = received_kas - sent_kas
        
        # Skip if net change is 0
        if net_amount == 0:
            continue

        # Determine Sent vs Received for the report format
        # If Net < 0, it's a Send (we lost balance). 
        # If Net > 0, it's a Receive (we gained balance).
        
        sent_val = 0
        received_val = 0
        
        if net_amount < 0:
            sent_val = abs(net_amount)
        else:
            received_val = net_amount

        tx_list.append({
            "Date": dt,
            "Amount": net_amount, # Keep for calculation
            "Sent Amount": sent_val if sent_val > 0 else None,
            "Received Amount": received_val if received_val > 0 else None,
            "Transaction ID": tx_id
        })

    df_tx = pd.DataFrame(tx_list)
    if df_tx.empty:
        return df_tx

    # Sort by Date Ascending to calculate running balance
    df_tx = df_tx.sort_values("Date", ascending=True).reset_index(drop=True)
    df_tx["Balance"] = df_tx["Amount"].cumsum()
    
    # Merge with Price Data
    # Create a 'DateOnly' column for merging
    df_tx["DateOnly"] = df_tx["Date"].dt.normalize()
    
    if not price_df.empty:
        df_merged = pd.merge_asof(df_tx, price_df.sort_values("timestamp"), left_on="Date", right_on="timestamp", direction="nearest")
        df_merged["Price"] = df_merged["price"]
        df_merged["Value (USD)"] = df_merged["Balance"] * df_merged["Price"]
        # Drop extra columns
        df_merged = df_merged.drop(columns=["timestamp", "price", "DateOnly"])
    else:
        df_merged = df_tx
        df_merged["Price"] = 0
        df_merged["Value (USD)"] = 0
        
    # Reorder columns for better report
    cols = ["Date", "Sent Amount", "Received Amount", "Balance", "Price", "Value (USD)", "Transaction ID"]
    # Filter to only existing columns (in case some are missing logic)
    cols = [c for c in cols if c in df_merged.columns]
    df_merged = df_merged[cols]

    return df_merged

# --- Main UI ---

st.title("Kaspa Address Tracker")
st.markdown("Track your Kaspa transactions and portfolio value.")

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    address_input = st.text_area("Enter Kaspa Address:", height=200)
    # days_history = st.slider("Price History (Days)", 30, 365, 90) # Deprecated: Auto-calculated
    generate_btn = st.button("Generate Report")

if generate_btn or address_input:
    if address_input:
        addresses = [a.strip() for a in address_input.split('\n') if a.strip()]
        
        for addr in addresses:
            st.divider()
            st.subheader(f"Address: {addr}")
            
            with st.spinner(f"Fetching transactions for {addr}..."):
                transactions = get_transactions(addr)
                
                if transactions:
                    # 1. Process transactions first to find the date range
                    # We need a temporary processing to get dates, or we can extract dates from raw txs
                    # Let's extract dates efficiently
                    tx_dates = []
                    for tx in transactions:
                        ts = tx.get("block_time")
                        if ts:
                            tx_dates.append(datetime.fromtimestamp(ts / 1000))
                    
                    if tx_dates:
                        min_date = min(tx_dates)
                        max_date = datetime.now()
                        
                        # Ensure we cover at least the requested history if it's longer than tx history
                        # But user asked for "since 1st transaction"
                        # Let's stick to 1st tx date as start
                        
                        with st.spinner("Checking and updating price database..."):
                            price_df = get_kaspa_price_history(min_date, max_date)
                        
                        df = process_data(transactions, addr, price_df)
                        
                        if not df.empty:
                            # Summary Stats
                            current_balance = df.iloc[-1]["Balance"]
                            
                            # Fetch live price for the "Current Value" display
                            live_price = get_current_price()
                            
                            if live_price > 0:
                                current_value = current_balance * live_price
                                current_price_display = f"${live_price:.4f}"
                            else:
                                # Fallback to last historical price
                                current_value = df.iloc[-1]["Value (USD)"]
                                last_price = df.iloc[-1]["Price"]
                                current_price_display = f"${last_price:.4f}"

                            total_received = df["Received Amount"].sum()
                            total_sent = df["Sent Amount"].sum()
                            
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Current Balance", f"{current_balance:,.2f} KAS")
                            c2.metric("Current Value (USD)", f"${current_value:,.2f}", delta=current_price_display)
                            c3.metric("Total Received", f"{total_received:,.2f} KAS")
                            c4.metric("Total Sent", f"{total_sent:,.2f} KAS")
                            
                            # Graphs
                            st.subheader("Portfolio Value Over Time")
                            fig_val = go.Figure()
                            fig_val.add_trace(go.Scatter(x=df["Date"], y=df["Value (USD)"], mode='lines', name='Value (USD)'))
                            st.plotly_chart(fig_val, use_container_width=True)
                            
                            st.subheader("Balance & Price Over Time")
                            fig_bal = go.Figure()
                            fig_bal.add_trace(go.Scatter(x=df["Date"], y=df["Balance"], mode='lines', name='Balance (KAS)', yaxis='y1'))
                            fig_bal.add_trace(go.Scatter(x=df["Date"], y=df["Price"], mode='lines', name='Price (USD)', yaxis='y2', line=dict(dash='dot')))
                            
                            fig_bal.update_layout(
                                yaxis=dict(title="Balance (KAS)"),
                                yaxis2=dict(title="Price (USD)", overlaying='y', side='right')
                            )
                            st.plotly_chart(fig_bal, use_container_width=True)
                            
                            # Data Table
                            st.subheader("Transaction History")
                            st.dataframe(df.sort_values("Date", ascending=False))
                            
                            # Download
                            csv = df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "Download Report (CSV)",
                                csv,
                                f"kaspa_report_{addr}.csv",
                                "text/csv",
                                key=f'download-csv-{addr}'
                            )
                            
                        else:
                            st.warning("No relevant transactions found for this address.")
                    else:
                            df_display["Amount"] = df_display["Amount"].round(0)
                            styled_df = df_display.style.applymap(color_amount, subset=["Amount"])
                            st.dataframe(styled_df)
                            # Download
                            csv = df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "Download Report (CSV)",
                                csv,
                                f"kaspa_report_{addr}.csv",
                                "text/csv",
                                key=f'download-csv-{addr}'
                            )
                else:
                    st.warning("No transactions found or API error.")
    else:
        st.info("Please enter a Kaspa address to start.")

