import sqlite3
import pandas as pd
from datetime import datetime, date

DB_NAME = "kaspa_data.db"

def init_db():
    """Initializes the SQLite database and creates the prices table."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kaspa_prices (
            date TEXT PRIMARY KEY,
            price REAL,
            price_eur REAL
        )
    ''')
    
    # Migration: Add price_eur column if it doesn't exist
    cursor.execute("PRAGMA table_info(kaspa_prices)")
    columns = [info[1] for info in cursor.fetchall()]
    if "price_eur" not in columns:
        cursor.execute("ALTER TABLE kaspa_prices ADD COLUMN price_eur REAL")
        
    conn.commit()
    conn.close()

def get_prices_from_db(start_date, end_date):
    """Retrieves prices from the database within a date range."""
    conn = sqlite3.connect(DB_NAME)
    # Select both prices
    query = "SELECT date, price, price_eur FROM kaspa_prices WHERE date >= ? AND date <= ?"
    df = pd.read_sql_query(query, conn, params=(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    conn.close()
    
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df

def save_prices_to_db(price_data):
    """Saves a list of (date, price, price_eur) tuples or a DataFrame to the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if isinstance(price_data, pd.DataFrame):
        data_to_insert = []
        for _, row in price_data.iterrows():
            # Ensure date is string YYYY-MM-DD
            ts = row['timestamp']
            if isinstance(ts, pd.Timestamp):
                d = ts.strftime("%Y-%m-%d")
            elif isinstance(ts, (datetime, date)):
                d = ts.strftime("%Y-%m-%d")
            else:
                d = str(ts).split(' ')[0] # Fallback
            
            # Ensure price is float
            try:
                p_usd = float(row['price'])
            except:
                p_usd = None
            
            try:
                p_eur = float(row.get('price_eur')) if pd.notnull(row.get('price_eur')) else None
            except:
                p_eur = None
                
            if p_usd is not None or p_eur is not None:
                data_to_insert.append((d, p_usd, p_eur))
    else:
        # Expecting list of (date, price_usd, price_eur)
        data_to_insert = price_data

    # Use UPSERT logic (SQLite 3.24+) to update existing records if we have new info (e.g. adding EUR to existing USD)
    # But standard INSERT OR IGNORE ignores updates.
    # We want to update if we have new data.
    # Let's use INSERT OR REPLACE? No, that deletes and re-inserts.
    # Let's use ON CONFLICT DO UPDATE
    
    cursor.executemany('''
        INSERT INTO kaspa_prices (date, price, price_eur) VALUES (?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            price = COALESCE(excluded.price, price),
            price_eur = COALESCE(excluded.price_eur, price_eur)
    ''', data_to_insert)
    
    conn.commit()
    conn.close()

def get_missing_dates(start_date, end_date):
    """Identifies dates with missing prices in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Generate full range of dates
    full_range = pd.date_range(start=start_date, end=end_date)
    
    # Get existing dates
    cursor.execute("SELECT date FROM kaspa_prices WHERE date >= ? AND date <= ?", 
                   (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    existing_dates = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    missing = []
    for d in full_range:
        d_str = d.strftime("%Y-%m-%d")
        if d_str not in existing_dates:
            missing.append(d)
            
    return missing

def get_dates_missing_currency(start_date, end_date, currency="eur"):
    """Identifies dates where the specified currency price is missing (NULL)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    col_name = "price_eur" if currency == "eur" else "price"
    
    # We want dates that exist in the DB but have NULL for the currency
    # OR dates that don't exist at all (though get_missing_dates handles the latter, 
    # this function focuses on "we have a row but missing this specific price")
    # Actually, let's just return dates in range where col is NULL or row missing.
    
    # But for efficiency, let's just find rows where date is in range AND col IS NULL
    query = f"SELECT date FROM kaspa_prices WHERE date >= ? AND date <= ? AND {col_name} IS NULL"
    cursor.execute(query, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    
    missing_dates = []
    for row in cursor.fetchall():
        missing_dates.append(pd.to_datetime(row[0]))
        
    conn.close()
    return missing_dates

def import_prices_from_excel(file_path):
    """Imports price data from the 'kas price' sheet of an Excel file."""
    try:
        df = pd.read_excel(file_path, sheet_name='kas price')
        # Ensure columns match expectations
        if 'Date' in df.columns and 'Kas Price' in df.columns:
            df = df.rename(columns={'Date': 'timestamp', 'Kas Price': 'price'})
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            save_prices_to_db(df)
            return True, f"Successfully imported {len(df)} records."
        else:
            return False, "Columns 'Date' and 'Kas Price' not found in Excel."
    except Exception as e:
        return False, str(e)
