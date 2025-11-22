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
            price REAL
        )
    ''')
    conn.commit()
    conn.close()

def get_prices_from_db(start_date, end_date):
    """Retrieves prices from the database within a date range."""
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT date, price FROM kaspa_prices WHERE date >= ? AND date <= ?"
    df = pd.read_sql_query(query, conn, params=(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    conn.close()
    
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df

def save_prices_to_db(price_data):
    """Saves a list of (date, price) tuples or a DataFrame to the database."""
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
                p = float(row['price'])
            except:
                continue # Skip invalid prices
                
            data_to_insert.append((d, p))
    else:
        data_to_insert = price_data

    cursor.executemany('''
        INSERT OR IGNORE INTO kaspa_prices (date, price) VALUES (?, ?)
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
