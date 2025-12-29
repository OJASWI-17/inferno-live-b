from django.shortcuts import render, get_object_or_404 ,redirect
from django.http import HttpResponse, JsonResponse
import pandas as pd
from .tasks import update_stock
from asgiref.sync import sync_to_async
import redis
import json
from django.contrib.auth.decorators import login_required
from django.db.models import Sum  # Import Sum for aggregation
from .models import UserProfile, StockDetail ,UserStock,LimitOrder,Transaction# Import your models
from django.views.decorators.http import require_POST
from decimal import Decimal

from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from .order_utils import buy_stock, sell_stock  
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth import authenticate,login,logout 
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie ,csrf_protect
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, reverse
from urllib.parse import urlencode

import jwt
from django.conf import settings
from django.utils.timezone import now, timedelta
# csrf_exempt is used to exempt the view from CSRF verification means that the view will not check for CSRF token in the request
from threading import Thread

import os



def generate_jwt_token(user):
    payload = {
        'user_id': user.id,
        'username': user.username,
        'exp': now() + timedelta(seconds=settings.JWT_EXP_DELTA_SECONDS),
        'iat': now(),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token


@csrf_exempt
def verifyotp(request):
    if request.method == "POST":
        data = json.loads(request.body)
        useotp = data.get('useotp')
        username = data.get('username')

        if not username or not useotp:
            return JsonResponse({'error': 'Username and OTP are required'}, status=400)

        # Fetch OTP from cache
        cached_otp = cache.get(f'otp_{username}')
        if not cached_otp:
            return JsonResponse({'error': 'OTP expired or invalid'}, status=400)

        if str(cached_otp) != str(useotp):
            return JsonResponse({'error': 'Incorrect OTP'}, status=400)

        # OTP is correct, issue JWT
        user = User.objects.get(username=username)
        token = generate_jwt_token(user)

        # Optionally, delete OTP after successful verification
        cache.delete(f'otp_{username}')

        return JsonResponse({'message': 'Login successful', 'token': token}, status=200)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


import random
from django.core.cache import cache
from django.core.mail import send_mail

def send_otp_email(subject, message, from_email, recipient_list):
    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
    except Exception as e:
        print("Email error:", e)


@csrf_exempt
def login_page(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            user = authenticate(username=username, password=password)
            if not user:
                return JsonResponse({'error': 'Invalid credentials'}, status=400)

            otp = random.randint(100000, 999999)
            cache.set(f'otp_{user.username}', otp, timeout=300)
            
            send_otp_email('Your OTP Code',f'Your OTP code is {otp}',settings.DEFAULT_FROM_EMAIL,[user.email],)


            
            
            return JsonResponse({'message': 'OTP sent successfully'})
            
        except Exception as e:
            print(f"Error: {str(e)}")  # Debugging
            return JsonResponse({'error': str(e)}, status=500)
    

def jwt_required(view_func):
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Authorization header missing or invalid'}, status=401)

        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user = User.objects.get(id=payload['user_id'])
            request.user = user  # Attach user to request
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist):
            return JsonResponse({'error': 'Invalid or expired token'}, status=401)

        return view_func(request, *args, **kwargs)
    return wrapper



        

@csrf_exempt
def register(request):
    if request.method == "POST":
        try:
            print("Received a POST request for registration")  # Debugging statement

            data = json.loads(request.body)
            print("Received Data:", data)  # Print incoming JSON data

            first_name = data.get('first_name')
            last_name = data.get('last_name')
            username = data.get('username')
            email = data.get('email')
            password = data.get('password')

            print(f"Extracted Data -> First Name: {first_name}, Last Name: {last_name}, Username: {username}, Email: {email}")

            if User.objects.filter(username=username).exists():
                print("Username is already taken")  # Debugging statement
                return JsonResponse({'error': 'Username is already taken'}, status=400)

            user = User.objects.create(
                first_name=first_name,
                last_name=last_name,
                username=username,
                email=email
            )
            user.set_password(password)
            user.save()

            print(f"User {username} created successfully!")  # Debugging statement

            return JsonResponse({'message': 'Account created successfully', 'redirect': '/login/'})
        
        except json.JSONDecodeError:
            print("Error: Invalid JSON data received")  # Debugging statement
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    print("Error: Method not allowed")  # Debugging statement
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt

def logout_page(request):
    if request.method == "POST":
        logout(request)
        return JsonResponse({'message': 'Logout successful'})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405) 

# Path to CSV file
CSV_FILE_PATH = os.path.join(
    settings.BASE_DIR,
    "mainapp",
    "multi_stock_data.csv"
)


# Load CSV into a DataFrame
df = pd.read_csv(CSV_FILE_PATH)

# Dictionary to store current index for each stock
stock_indices = {ticker: 0 for ticker in df["ticker"].unique()} # output will be {'AAPL': 0, 'GOOGL': 0, 'MSFT': 0, 'AMZN': 0, 'TSLA': 0} , here 0 is the index of the stock

# views.py
from django.http import JsonResponse
from django.middleware.csrf import get_token

def get_csrf(request):
    return JsonResponse({'csrfToken': get_token(request)})

def get_stock_updates(selected_stocks):
    """Fetch stock data from CSV and simulate real-time updates."""
    global stock_indices 
    data = {}

    for ticker in selected_stocks:
        stock_data = df[df["ticker"] == ticker] 
        index = stock_indices.get(ticker, 0)  # .get is used to get the value of the key from the dictionary, if the key does not exist then it will return the default value which is 0 , example stock_indices.get('AAPL',0) will return 0 as AAPL is not present in the dictionary

        # If we reach the end of the dataset, loop back to the beginning
        if index >= len(stock_data):
            index = 0

        row = stock_data.iloc[index]# iloc is used to get the data from the index

        data[ticker] = {
            "time": row["date"],  # Ensure this is a string or timestamp
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        }

        # Move to the next index for the next call
        stock_indices[ticker] = index + 1

    return data



# urlencode is used to encode the url parameters
@jwt_required
def stockPicker(request):
    print("Authenticated user:", request.user) 
    auth_header = request.headers.get('Authorization')
    if auth_header:
        token = auth_header.split(' ')[1]  # Extract the token part
        print("JWT Token from request header:", token)
    
    """Return JSON list of default stocks instead of redirecting"""
    try:
        default_stocks = df["ticker"].unique().tolist()[:]  # Get first 5 stocks
        return JsonResponse({
            "stocks": default_stocks,
            "tracker_url": f"{reverse('stocktracker')}?{urlencode([('stock_picker', stock) for stock in default_stocks], doseq=True)}"
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@sync_to_async
def checkAuthenticated(request):
    return bool(request.user.is_authenticated)

from django.http import JsonResponse


async def stockTracker(request):
    # Get token from the "Authorization" header
    # auth_header = request.headers.get('Authorization')
    # if not auth_header:
    #     return JsonResponse({'error': 'Authorization header missing'}, status=401)

    # try:
    #     token = auth_header.split(' ')[1]
    #     payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    #     user = await sync_to_async(User.objects.get)(id=payload['user_id'])
    # except Exception as e:
    #     print("JWT error:", e)
    #     return JsonResponse({'error': 'Invalid or expired token'}, status=401)

    # ✅ Now you have `user`, continue
    selected_stocks = request.GET.getlist("stock_picker")
    if not selected_stocks:
        return JsonResponse({"error": "No stocks selected"}, status=400)

    initial_data = get_stock_updates(selected_stocks)
    update_stock.delay(selected_stocks)

    return JsonResponse({"data": initial_data}, status=200)





redis_conn = redis.from_url(
    os.environ.get("REDIS_URL"),
    decode_responses=True
)

def stock_chart_data(request, stock_symbol):
    """Fetch stock data from Redis and return it in JSON format."""
    redis_key = f"candlestick_data:{stock_symbol}"
    data = redis_conn.get(redis_key)  

    if not data:
        return JsonResponse({"error": "No data found"}, status=404)

    df = pd.DataFrame(json.loads(data))

    # Ensure the 'time' column is correctly converted to a Unix timestamp
    df["time"] = pd.to_datetime(df["time"]).astype("int64") // 10**9  
 

    # Convert DataFrame to JSON format expected by React Chart
    chart_data = df[["time", "open", "high", "low", "close", "volume"]].to_dict(orient="records")  
    
    return JsonResponse(chart_data, safe=False)




# Connect to Redis

def fetch_stock_data(selected_stock):
    """Fetch latest candlestick data from Redis."""
    redis_key = f"candlestick_data:{selected_stock}"
    data = redis_conn.get(redis_key) 

    if not data:
        return JsonResponse({"error": "No data found for stock"}, status=404)

    return JsonResponse(json.loads(data), safe=False)

def chart_view(request):
    """Fetch stocks selected by the logged-in user."""
    
    if request.user.is_authenticated:
        # Convert the QuerySet to a list of stock symbols
        selected_stocks = list(StockDetail.objects.filter(user=request.user).values_list("stock", flat=True))
        user_profile, _ = UserProfile.objects.get_or_create(user=request.user) 
        balance = user_profile.balance
        user_data = {
            "username": request.user.username,
            "email": request.user.email,
            "id": request.user.id
        }
    else:
        selected_stocks = []
        balance = 0
        user_data = None

    return JsonResponse({
        "available_stocks": selected_stocks,
        "user": user_data,
        "balance": float(balance)  # Convert Decimal to float for JSON serialization
    }, status=200)



import logging
logger = logging.getLogger(__name__)

# @login_required # Ensure user is logged in


@csrf_exempt 
@require_POST
@jwt_required
def place_order(request):
    # print("CSRF Token from Cookie:", request.COOKIES.get('csrftoken'))
    # print("CSRF Token:", request.META.get('CSRF_COOKIE')) # CSRF token from request headers
    # print("Headers:", request.headers) # Print all headers to check if CSRF token is present
    if request.user.is_authenticated:
        print("Authenticated user")
        user_profile, _ = UserProfile.objects.get_or_create(user=request.user) 
    
    if not request.user.is_authenticated:
        print("not authenticated")
        return JsonResponse({"error": "User not authenticated"}, status=401)

    try:
        # For form-urlencoded data (what your frontend is sending)
        stock_symbol = request.POST.get("stock_symbol") # request.POST.get is used to get the value of the key from the request body
        quantity = int(request.POST.get("quantity"))
        order_type = request.POST.get("order_type")
        price = float(request.POST.get("price")) if order_type == "limit" else None
        action = request.POST.get("action")
        
        
        

        # Fetch current market price from Redis
        redis_key = f"candlestick_data:{stock_symbol}"
        data = redis_conn.get(redis_key)

        if not data:
            return JsonResponse({"error": "No data found for the selected stock"}, status=404)

        latest_data = json.loads(data)[-1]  # Get the latest candlestick data
        market_price = Decimal(latest_data["close"])  # Use the closing price as the market price

        # Validate sell orders
        if action == "sell":
            # Check if the user owns the stock
            user_stock = UserStock.objects.filter(user=request.user, stock=stock_symbol).first()
            if not user_stock:
                return JsonResponse({"error": "You do not own this stock"}, status=400)

            # Check if the user has enough shares to sell
            if user_stock.quantity < quantity:
                return JsonResponse({"error": "Not enough holding shares"}, status=400)

        if order_type == "market":
            # Execute market order immediately
            if action == "buy":
                result = buy_stock(request.user, stock_symbol, quantity, market_price)
            elif action == "sell":
                result = sell_stock(request.user, stock_symbol, quantity, market_price)
            else:
                return JsonResponse({"error": "Invalid action"}, status=400)

            if "error" in result:
                return JsonResponse({"error": result["error"]}, status=400)

            return JsonResponse({
                "message": result.get("message", "Trade successful"),
                "balance": result["balance"],
                "stock": stock_symbol,
                "quantity": quantity,
                "price": float(result["price"]),  # Market price used for the order
            })
        elif order_type == "limit":
            # Create a limit order
            if not price:
                return JsonResponse({"error": "Price is required for limit orders"}, status=400)

            limit_price = Decimal(price)
            
            
            LimitOrder.objects.create( # create a new limit order
                user=request.user,
                stock=stock_symbol,
                quantity=quantity,
                price=limit_price,
                order_type="BUY" if action == "buy" else "SELL",
            )
            user_profile = UserProfile.objects.get(user=request.user)
            balance= user_profile.balance
            return JsonResponse({
                "success": True,
                "message": f"Limit order placed for {quantity} shares of {stock_symbol} at ${limit_price}",
                "balance":float(balance),
            })
        else:
            return JsonResponse({"error": "Invalid order type"}, status=400)
    
    except Exception as e:
        # logger.error(f"Error processing order: {str(e)}", exc_info=True)
        return JsonResponse({"error": "Internal server error"}, status=500)

@jwt_required
def balance(request):
    """Fetch user's balance."""
    if request.user.is_authenticated:
        user_profile, _ = UserProfile.objects.get_or_create(user=request.user) 
        balance = user_profile.balance
        return JsonResponse({"balance": float(balance)}, status=200)
    else:
        return JsonResponse({"error": "User not authenticated"}, status=401)
    
@jwt_required
def get_live_prices(request):
    """Fetch live prices for the user's bought stocks and calculate profit/loss."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "User not authenticated"}, status=401)

    # Fetch user's bought stocks
    user_stocks = UserStock.objects.filter(user=request.user) # wrong : output will be the list of stocks bought by the user , how ? UserStock is a model which has a field user which is a foreign key to the User model , so when we filter the UserStock model with the user=request.user , we get the list of stocks bought by the user
    live_prices = {}

    for stock in user_stocks:
        redis_key = f"candlestick_data:{stock.stock}"
        data = redis_conn.get(redis_key)

        if data:
            latest_data = json.loads(data)[-1]  # Get the latest candlestick data
            current_price = Decimal(latest_data["close"])
            average_price = stock.average_price

            # Calculate profit/loss
            profit_loss = (current_price - average_price) * stock.quantity
            profit_loss_percentage = ((current_price - average_price) / average_price) * 100

            live_prices[stock.stock] = {
                "quantity": stock.quantity,
                "average_price": float(average_price),
                "live_price": latest_data["close"],
                "total_value": float(stock.quantity * latest_data["close"]),
                "profit_loss": float(profit_loss),  # Total profit/loss in currency
                "profit_loss_percentage": float(profit_loss_percentage),  # Profit/loss percentage
            }

    return JsonResponse(live_prices)

@jwt_required
def order_history(request):
    """Main order history view (renders template)"""
    # Get all transactions (individual trades)
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')
    
    # Get pending limit orders
    pending_orders = LimitOrder.objects.filter(user=request.user).order_by('-created_at')
    
    # Combine and format all orders
    all_orders = []
    
    for tx in transactions:
        all_orders.append({
            "type": tx.get_order_type_display(),
            "action": tx.get_action_display(),
            "stock": tx.stock,
            "quantity": tx.quantity,  # Original quantity from this specific trade
            "price": float(tx.price),
            "status": "Executed",
            "timestamp": tx.timestamp,
        })

    for order in pending_orders:
        all_orders.append({
            "type": "Limit Order",
            "action": order.get_order_type_display(),
            "stock": order.stock,
            "quantity": order.quantity,
            "price": float(order.price),
            "status": "Pending",
            "timestamp": order.created_at,
        })

    return JsonResponse({"orders": all_orders}, status=200)

@jwt_required
def order_history_ajax(request):
    
    """AJAX endpoint for dynamic updates"""
    # Same logic as order_history but returns JSON
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')
    pending_orders = LimitOrder.objects.filter(user=request.user).order_by('-created_at')
    
    all_orders = []
    
    for tx in transactions:
        all_orders.append({
            "type": tx.order_type,
            "action": tx.action,
            "stock": tx.stock,
            "quantity": tx.quantity,
            "price": float(tx.price),
            "status": "Executed",
            "timestamp": tx.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        })

    for order in pending_orders:
        all_orders.append({
            "type": "LIMIT",
            "action": order.order_type,
            "stock": order.stock,
            "quantity": order.quantity,
            "price": float(order.price),
            "status": "Pending",
            "timestamp": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return JsonResponse({"orders": all_orders})


@jwt_required
def leaderboard(request):
    """Leaderboard showing lifetime profits + current holdings"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    leaderboard_data = []
    
    for profile in UserProfile.objects.select_related('user').all():
        total_profit = profile.cumulative_profit  # Start with realized profits
        
        # Add unrealized profits from current holdings
        for stock in profile.user.userstock_set.all(): # profile.user.userstock_set.all() 
            try:
                redis_data = redis_conn.get(f"candlestick_data:{stock.stock}")
                if redis_data:
                    current_price = Decimal(json.loads(redis_data)[-1]["close"])
                    total_profit += (current_price - stock.average_price) * stock.quantity
            except:
                continue  # Skip if price data unavailable

        leaderboard_data.append({
            "username": profile.user.username,
            "total_profit": float(total_profit.quantize(Decimal('0.01')))
        })

    leaderboard_data.sort(key=lambda x: x["total_profit"], reverse=True)
    return JsonResponse( {"leaderboard_data": leaderboard_data}, status=200) 