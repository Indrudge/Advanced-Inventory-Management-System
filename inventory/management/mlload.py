import pandas as pd
import numpy as np
from joblib import load
import random
from datetime import timedelta
from pymongo import MongoClient
from datetime import datetime

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")  # Update with your actual MongoDB connection string if needed
db = client["bhavi"]

# Load model and encoder
model = load(r"C:\Volume_d\sem6BCA\MajorP2\projest\Major2\inventory\management\ridge_model_daily.pkl")
le = load(r"C:\Volume_d\sem6BCA\MajorP2\projest\Major2\inventory\management\label_encoder_daily.pkl")

# Function to handle different date formats
def parse_date(date):
    try:
        # Try parsing the old date format (e.g., 24/02/17 13:10)
        return pd.to_datetime(date, format='%d/%m/%y %H:%M', errors='coerce')
    except ValueError:
        try:
            # Try parsing the new date format (e.g., 2025-05-02T14:26:39.889293+00:00)
            return pd.to_datetime(date, errors='coerce')
        except ValueError:
            # If both fail, return NaT (Not a Time)
            return pd.NaT

# Fetch orders and items from MongoDB
orders_cursor = db["orders"].find()
items_cursor = db["items"].find()

orders = pd.DataFrame(list(orders_cursor))
items = pd.DataFrame(list(items_cursor))

# Parse the 'date' field according to the format
orders['timestamp'] = orders['date'].apply(parse_date)

# Drop rows with invalid dates (NaT)
orders = orders.dropna(subset=['timestamp'])

# Extract date and day_of_week from valid timestamps
orders['date'] = orders['timestamp'].dt.date
orders['day_of_week'] = orders['timestamp'].dt.dayofweek

# Merge with items data
orders = orders.merge(items, on='item_id', how='left')

# Daily aggregation
daily_df = orders.groupby(['date', 'day_of_week', 'item_id']).size().reset_index(name='quantity')

# Sort and add time-series features
daily_df = daily_df.sort_values(by=['item_id', 'date'])
daily_df['lag1'] = daily_df.groupby('item_id')['quantity'].shift(1)
daily_df['rolling_mean_3'] = daily_df.groupby('item_id')['quantity'].shift(1).rolling(window=3).mean()
daily_df['rolling_std_3'] = daily_df.groupby('item_id')['quantity'].shift(1).rolling(window=3).std()

# Drop rows without enough history
daily_df.dropna(inplace=True)

# Find latest valid date per item
latest_valid_dates = daily_df.groupby('item_id')['date'].max().reset_index()
latest_data = daily_df.merge(latest_valid_dates, on=['item_id', 'date'], how='inner')

# Set next day info
latest_data['day_of_week'] = (latest_data['day_of_week'] + 1) % 7
latest_data['item_encoded'] = le.transform(latest_data['item_id'])

# Model input
X_input = latest_data[['day_of_week', 'item_encoded', 'lag1', 'rolling_mean_3', 'rolling_std_3']]

# Predict
predictions = model.predict(X_input)
latest_data['predicted_quantity'] = predictions

# Add noise and create final predictions
final_preds = []
for item_id, pred in zip(latest_data['item_id'], predictions):
    noise = random.randint(1, 8)
    adjusted = max(0, round(pred - noise))
    final_preds.append({"item_id": item_id, "predicted_quantity": adjusted})

# Clear previous predictions in the 'prediction' collection
db["prediction"].delete_many({})

# Store new predictions in MongoDB
db["prediction"].insert_many(final_preds)

print("Predictions successfully stored in MongoDB 'prediction' collection.")
