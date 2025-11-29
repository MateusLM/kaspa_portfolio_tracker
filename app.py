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
COINSTATS_API_BASE = "https://openapiv1.coinstats.app"
COINSTATS_API_KEY = st.secrets["COINSTATS_API_KEY"]

# --- Helper Functions ---

@st.cache_data(ttl=300)
def get_transactions(address):
    """Fetches full transaction history for a Kaspa address."""
    url = f"{KASPA_API_BASE}/addresses/{address}/full-transactions"
    params = {"limit": 500, "resolve_previous_outpoints": "light"} # Fetching up to 500
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

def fetch_prices_coinstats(start_date, end_date):
    """Fetches price history from CoinStats."""
    # CoinStats uses 'period' (1m, 3m, 6m, 1y, all)
    # Determine best period
    delta = datetime.now() - start_date
    if delta.days <= 30:
        period = "1m"
    elif delta.days <= 90:
        period = "3m"
    elif delta.days <= 180:
        period = "6m"
    elif delta.days <= 365:
        period = "1y"
    else:
        period = "all"
        
    url = f"{COINSTATS_API_BASE}/coins/kaspa/charts"
    headers = {"X-API-KEY": COINSTATS_API_KEY}
    params = {"period": period}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        # Data is a list of [timestamp, price, ...]
        if isinstance(data, list):
            prices = []
            for item in data:
                ts = item[0]
                price = item[1]
                prices.append({"timestamp": ts * 1000, "price": price}) # Convert to ms for consistency
            return prices
        return []
    except Exception as e:
        st.error(f"Error fetching prices from CoinStats: {e}")
        return []

def fetch_prices_coingecko(fetch_start, fetch_end, currency="usd"):
    """Fetches price history from CoinGecko."""
    # CoinGecko expects UNIX timestamp for range
    from_ts = int(fetch_start.timestamp())
    to_ts = int((fetch_end + timedelta(days=1)).timestamp()) # +1 day to ensure coverage
    
    url = f"{COINGECKO_API_BASE}/coins/kaspa/market_chart/range"
    params = {
        "vs_currency": currency,
        "from": from_ts,
        "to": to_ts
    }
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 429:
            st.error("CoinGecko API rate limit exceeded. Please wait a minute.")
            return []
        elif response.status_code == 400 or response.status_code == 401:
             st.error(f"CoinGecko API Error: {response.json().get('error', 'Unknown error')}")
             return []
        else:
            response.raise_for_status()
            data = response.json()
            return data.get("prices", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching price history from CoinGecko: {e}")
        return []

@st.cache_data(ttl=3600)
def get_kaspa_price_history(start_date, end_date, source="CoinGecko"):
    """Fetches Kaspa price history, using DB cache and filling gaps from API."""
    
    # 1. Check DB for existing data
    df_db = database.get_prices_from_db(start_date, end_date)
    
    # 2. Identify missing dates
    # Dates completely missing from DB
    missing_dates_all = database.get_missing_dates(start_date, end_date)
    
    # Dates present but missing specific currency
    missing_dates_usd = database.get_dates_missing_currency(start_date, end_date, currency="usd")
    missing_dates_eur = database.get_dates_missing_currency(start_date, end_date, currency="eur")
    
    # Combine fetch needs
    # We need USD for 'missing_dates_all' + 'missing_dates_usd'
    # We need EUR for 'missing_dates_all' + 'missing_dates_eur'
    
    dates_needed_usd = set(missing_dates_all) | set(missing_dates_usd)
    dates_needed_eur = set(missing_dates_all) | set(missing_dates_eur)
    
    fetch_needed = False
    if dates_needed_usd or dates_needed_eur:
        fetch_needed = True
        
    if fetch_needed:
        prices_usd = []
        prices_eur = []
        
        # Fetch USD
        if dates_needed_usd:
            fetch_start_usd = min(dates_needed_usd)
            fetch_end_usd = max(dates_needed_usd)
            
            if source == "CoinStats":
                st.info(f"Fetching missing USD price data from CoinStats ({fetch_start_usd.date()} to {fetch_end_usd.date()})...")
                prices_usd = fetch_prices_coinstats(fetch_start_usd, fetch_end_usd)
            else:
                # CoinGecko Logic for USD
                limit_date = datetime.now() - timedelta(days=365)
                if fetch_start_usd < limit_date:
                    st.warning(f"Note: Price history older than 365 days is not available on the free CoinGecko plan. Fetching available data from {limit_date.date()}.")
                    fetch_start_usd = max(fetch_start_usd, limit_date)
                
                if fetch_start_usd <= fetch_end_usd:
                    st.info(f"Fetching missing USD price data from CoinGecko ({fetch_start_usd.date()} to {fetch_end_usd.date()})...")
                    prices_usd = fetch_prices_coingecko(fetch_start_usd, fetch_end_usd, "usd")

        # Fetch EUR
        if dates_needed_eur:
            fetch_start_eur = min(dates_needed_eur)
            fetch_end_eur = max(dates_needed_eur)
            
            limit_date = datetime.now() - timedelta(days=365)
            if fetch_start_eur < limit_date:
                 fetch_start_eur = max(fetch_start_eur, limit_date)
            
            if fetch_start_eur <= fetch_end_eur:
                st.info(f"Fetching missing EUR price data from CoinGecko ({fetch_start_eur.date()} to {fetch_end_eur.date()})...")
                prices_eur = fetch_prices_coingecko(fetch_start_eur, fetch_end_eur, "eur")

        # Merge and Save
        # We need to handle cases where we might have only fetched EUR, or only USD, or both.
        
        # Create base DF from whatever we have
        df_new = pd.DataFrame()
        
        if prices_usd:
            df_usd = pd.DataFrame(prices_usd, columns=["timestamp", "price"])
            df_usd["timestamp"] = pd.to_datetime(df_usd["timestamp"], unit="ms").dt.normalize()
            df_new = df_usd
            
        if prices_eur:
            df_eur = pd.DataFrame(prices_eur, columns=["timestamp", "price_eur"])
            df_eur["timestamp"] = pd.to_datetime(df_eur["timestamp"], unit="ms").dt.normalize()
            
            if not df_new.empty:
                df_new = pd.merge(df_new, df_eur, on="timestamp", how="outer")
            else:
                df_new = df_eur
                
        if not df_new.empty:
            # Ensure columns exist
            if "price" not in df_new.columns:
                df_new["price"] = None
            if "price_eur" not in df_new.columns:
                df_new["price_eur"] = None
                
            # Save to DB
            database.save_prices_to_db(df_new)
            
            # Re-query DB to get the complete dataset
            df_db = database.get_prices_from_db(start_date, end_date)
            
    # Rename columns to match expected format
    if not df_db.empty:
        df_db = df_db.rename(columns={"date": "timestamp"})
        
    return df_db

def get_current_price(source="CoinGecko"):
    """Fetches the current live price of Kaspa. Returns a dict with 'usd' and 'eur' keys."""
    if source == "CoinStats":
        url = f"{COINSTATS_API_BASE}/coins/kaspa"
        headers = {"X-API-KEY": COINSTATS_API_KEY}
        # Fetch USD
        response_usd = requests.get(url, headers=headers)
        response_usd.raise_for_status()
        data_usd = response_usd.json()
        price_usd = data_usd.get("price")
        if price_usd is None:
             raise ValueError("Price data missing from CoinStats response")
             
        # Fetch EUR
        params_eur = {"currency": "EUR"}
        response_eur = requests.get(url, headers=headers, params=params_eur)
        response_eur.raise_for_status()
        data_eur = response_eur.json()
        price_eur = data_eur.get("price")
        if price_eur is None:
             # Fallback or raise? User prefers errors, but maybe we can tolerate missing EUR if USD worked?
             # Let's return 0 if EUR fails but USD worked, or raise if strict.
             # Given user preference "prefer to raise an error", let's raise.
             raise ValueError("EUR Price data missing from CoinStats response")
        
        return {"usd": price_usd, "eur": price_eur} 
    else:
        url = f"{COINGECKO_API_BASE}/simple/price"
        params = {
            "ids": "kaspa",
            "vs_currencies": "usd,eur"
        }
        # Let requests raise errors
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        kaspa_data = data.get("kaspa", {})
        if not kaspa_data:
             raise ValueError("Price data missing from CoinGecko response")
             
        return {
            "usd": kaspa_data.get("usd", 0),
            "eur": kaspa_data.get("eur", 0)
        }

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
        # if net_amount == 0:
        #     continue

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
    
    st.subheader("Data Source")
    data_source = st.radio("Select Price Source:", ["CoinGecko", "CoinStats"], index=1) # Default to CoinStats as requested
    
    st.subheader("Currency")
    currency_select = st.radio("Select Currency:", ["USD", "EUR"], index=0)

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
                        
                        with st.spinner(f"Checking and updating price database ({data_source})..."):
                            price_df = get_kaspa_price_history(min_date, max_date, source=data_source)
                        
                        df = process_data(transactions, addr, price_df)
                        
                        if not df.empty:
                            # Summary Stats
                            # Summary Stats
                            current_balance = df.iloc[-1]["Balance"]
                            
                            # Fetch live price for the "Current Value" display
                            # We always need USD for the base calculation, but we might need EUR for display
                            try:
                                live_prices = get_current_price(source=data_source)
                                live_price_usd = live_prices.get("usd", 0)
                                live_price_eur = live_prices.get("eur", 0)
                            except Exception as e:
                                st.error(f"Failed to fetch current price from {data_source}: {e}")
                                st.stop()
                            
                            # Determine Currency Symbol and Rate
                            currency_symbol = "$"
                            exchange_rate = 1.0
                            
                            if currency_select == "EUR":
                                currency_symbol = "€"
                                if live_price_eur > 0 and live_price_usd > 0:
                                     exchange_rate = live_price_eur / live_price_usd
                                elif live_price_usd > 0:
                                     # Fallback if EUR not returned (e.g. CoinStats)
                                     # Try to fetch EUR rate separately if really needed, or just use 1.0?
                                     # For now, let's try to fetch EUR from CoinGecko if we are on CoinStats and missing EUR
                                     if live_price_eur == 0:
                                         try:
                                             url = f"{COINGECKO_API_BASE}/simple/price"
                                             params = {"ids": "kaspa", "vs_currencies": "eur"}
                                             r = requests.get(url, params=params)
                                             r.raise_for_status()
                                             d = r.json()
                                             live_price_eur = d.get("kaspa", {}).get("eur", 0)
                                             if live_price_eur > 0:
                                                 exchange_rate = live_price_eur / live_price_usd
                                         except Exception as e:
                                             st.warning(f"Could not fetch EUR rate: {e}. Using USD.")
                            
                            # Apply Conversion
                            current_value = current_balance * live_price_usd * exchange_rate
                            live_price_display = live_price_usd * exchange_rate
                            
                            # Convert Historical Data for Display
                            # If we have 'price_eur' in DB, use it. Otherwise convert.
                            if currency_select == "EUR" and "price_eur" in df.columns:
                                # Use price_eur where available, fallback to USD * rate
                                df["Price (Display)"] = df["price_eur"].fillna(df["Price"] * exchange_rate)
                                df["Value (Display)"] = df["Balance"] * df["Price (Display)"]
                            else:
                                df["Price (Display)"] = df["Price"] * exchange_rate
                                df["Value (Display)"] = df["Value (USD)"] * exchange_rate
                            
                            total_received = df["Received Amount"].sum()
                            total_sent = df["Sent Amount"].sum()
                            
                            # --- Advanced Metrics ---
                            # Ensure no NaNs for calculation
                            df_calc = df.fillna(0)
                            
                            # Calculate Total Inflow/Outflow using the Display Price (which is EUR if selected)
                            # This is more accurate than converting the sum if we have historical EUR prices
                            total_in = (df_calc["Received Amount"] * df_calc["Price (Display)"]).sum()
                            total_out = (df_calc["Sent Amount"] * df_calc["Price (Display)"]).sum()
                            
                            # Avg Buy Price (Weighted Average of all Receives)
                            if total_received > 0:
                                avg_buy_price = total_in / total_received
                            else:
                                avg_buy_price = 0
                                
                            # Net Cost = Total Invested - Total Cashed Out
                            net_cost = total_in - total_out
                            
                            # Profit / Loss = Current Value - Net Cost
                            profit_loss = current_value - net_cost
                            
                            if net_cost != 0:
                                if total_in > 0:
                                    profit_loss_pct = (profit_loss / total_in) * 100
                                else:
                                    profit_loss_pct = 0
                            else:
                                profit_loss_pct = 0

                            # Row 1
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Current Balance", f"{current_balance:,.2f} KAS")
                            c2.metric(f"Current Value ({currency_select})", f"{currency_symbol}{current_value:,.2f}")
                            c3.metric(f"Current Price ({currency_select})", f"{currency_symbol}{live_price_display:.4f}")
                            c4.metric(f"Avg Buy Price ({currency_select})", f"{currency_symbol}{avg_buy_price:.4f}")
                            
                            # Row 2
                            c5, c6, c7, c8 = st.columns(4)
                            c5.metric("Total Received", f"{total_received:,.2f} KAS")
                            c6.metric("Total Sent", f"{total_sent:,.2f} KAS")
                            c7.metric(f"Net P/L ({currency_select})", f"{currency_symbol}{profit_loss:,.2f}", delta=f"{profit_loss_pct:.2f}%")
                            
                            # Calculate Break Even %
                            if net_cost > 0:
                                if current_value > 0:
                                    break_even_pct = ((net_cost - current_value) / current_value) * 100
                                    c7.caption(f"{break_even_pct:+.2f}% to Break Even")
                                else:
                                    c7.caption("Total Loss")
                            else:
                                c7.caption("Profit Secured")

                            c8.metric(f"Net Cost ({currency_select})", f"{currency_symbol}{net_cost:,.2f}", help=f"Total {currency_select} In - Total {currency_select} Out")
                            
                            # Graphs
                            st.subheader("Portfolio Value Over Time")
                            fig_val = go.Figure()
                            fig_val.add_trace(go.Scatter(x=df["Date"], y=df["Value (Display)"], mode='lines', name=f'Value ({currency_select})'))
                            st.plotly_chart(fig_val, use_container_width=True)
                            
                            st.subheader("Balance & Price Over Time")
                            fig_bal = go.Figure()
                            fig_bal.add_trace(go.Scatter(x=df["Date"], y=df["Balance"], mode='lines', name='Balance (KAS)', yaxis='y1'))
                            fig_bal.add_trace(go.Scatter(x=df["Date"], y=df["Price (Display)"], mode='lines', name=f'Price ({currency_select})', yaxis='y2', line=dict(dash='dot')))
                            
                            fig_bal.update_layout(
                                yaxis=dict(title="Balance (KAS)"),
                                yaxis2=dict(title=f"Price ({currency_select})", overlaying='y', side='right')
                            )
                            st.plotly_chart(fig_bal, use_container_width=True)
                            
                            # Data Table
                            st.subheader("Transaction History")
                            # Show display columns in table
                            df_display = df.copy()
                            df_display[f"Price ({currency_select})"] = df_display["Price (Display)"]
                            df_display[f"Value ({currency_select})"] = df_display["Value (Display)"]
                            st.dataframe(df_display[["Date", "Sent Amount", "Received Amount", "Balance", f"Price ({currency_select})", f"Value ({currency_select})", "Transaction ID"]].sort_values("Date", ascending=False))
                            
                            # Download
                            csv = df_display.to_csv(index=False).encode('utf-8')
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
