from celery import shared_task
import pandas as pd
import json
import redis
from channels.layers import get_channel_layer
import asyncio
from mainapp.models import StockDetail,LimitOrder
from decimal import Decimal
from .order_utils import buy_stock, sell_stock 


# Redis Connection
redis_conn = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

# Path to CSV file
CSV_FILE_PATH ="mainapp/multi_stock_data.csv"
df = pd.read_csv(CSV_FILE_PATH)

# Track index for each stock
stock_indices = {ticker: 0 for ticker in df["ticker"].unique()}

def fetch_stock_data_from_csv(selected_stocks):
    """Fetch stock data from CSV and store in Redis in a standardized format."""
    global stock_indices
    data = {}

    for ticker in selected_stocks:
        stock_data = df[df["ticker"] == ticker]
        index = stock_indices.get(ticker, 0)
        if index >= len(stock_data):
            index = 0

        row = stock_data.iloc[index] # .iloc is used to get a row by index 
        stock_indices[ticker] = index + 1  # Move index forward

        # Standardized data format
        stock_entry = {
            "time": row["date"],  # Ensure this is a string or timestamp
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        }

        # Store data in Redis
        redis_key = f"candlestick_data:{ticker}"
        history = redis_conn.get(redis_key) 
        if history:
            history = json.loads(history) # Convert JSON string to Python list
            
            if len(history) < 1000:  # Keep only last 1000 candles
                history.append(stock_entry) # Append new stock entry
        else:
            history = [stock_entry] 

        redis_conn.set(redis_key, json.dumps(history)) # Save updated history in Redis , convert Python list to JSON string
        data[ticker] = stock_entry

    return data

@shared_task
def update_stock(selected_stocks=None):
    """Fetch stock data, and send WebSocket updates."""
     # if no stocks are provided, fetch from the database
    selected_stocks = ['MSFT','AAPL','GOOGL','AMZN','TSLA','NVDA','NFLX','META'] # example of output ['AAPL', 'GOOGL']
    if not selected_stocks:
        print("No stocks selected.")
        return

    data = fetch_stock_data_from_csv(selected_stocks)
    print("Updated Stock Data:", data)

    # Send update to WebSocket
    channel_layer = get_channel_layer()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(channel_layer.group_send("stock_track", {
        "type": "send_stock_update",
        "message": data,
    }))
    loop.close()
    
    


@shared_task
def process_limit_orders():
    """Check and execute limit orders."""

    for order in LimitOrder.objects.all():
        redis_key = f"candlestick_data:{order.stock}"
        data = redis_conn.get(redis_key)

        if not data:
            print(f"No data found for stock: {order.stock}")
            continue

        latest_data = json.loads(data)[-1]  # Get the latest candlestick data
        market_price = Decimal(latest_data["close"])

        print(f"Checking limit order: {order} | Market Price: {market_price}")

        if (order.order_type == "BUY" and market_price <= order.price) or \
           (order.order_type == "SELL" and market_price >= order.price):
            # Execute the order
            if order.order_type == "BUY":
                result = buy_stock(order.user, order.stock, order.quantity, order.price, order_type='LIMIT')
            else:
                result = sell_stock(order.user, order.stock, order.quantity, order.price, order_type='LIMIT')

            if "error" in result:
                print(f"Error executing limit order: {result['error']}")
            else:
                print(f"Executed limit order: {order}")
                order.delete()  # Remove the limit order after execution