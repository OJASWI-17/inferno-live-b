import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
import redis
from urllib.parse import parse_qs
import os

# Connect to Redis
redis_client =redis.from_url(
    os.environ.get("REDIS_URL"),
    decode_responses=True
)
class StockConsumer(AsyncWebsocketConsumer):
    """Manages stock selection and periodic updates using Celery Beat."""

    async def get_authenticated_user(self):
        """Helper method to get authenticated user properly."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Resolve the lazy user object
        user = await sync_to_async(lambda: self.scope["user"]._wrapped)()
        
        # If it's still not resolved, get from DB
        if hasattr(user, '_wrapped'):
            user_id = user.id
            return await sync_to_async(User.objects.get)(id=user_id)
        return user

    @sync_to_async
    def add_to_celery_beat(self, stockpicker):
        """Updates or creates a Celery Beat task for fetching stock data."""
        from django_celery_beat.models import PeriodicTask, IntervalSchedule

        task = PeriodicTask.objects.filter(name="every-40-seconds").first()

        if task:
            task.args = json.dumps([stockpicker])
            task.save()
        else:
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=40, 
                period=IntervalSchedule.SECONDS
            )
            task = PeriodicTask.objects.create(
                interval=schedule,
                name="every-40-seconds",
                task="mainapp.tasks.update_stock",
                args=json.dumps([stockpicker])
            )

    @sync_to_async
    def add_to_stock_detail(self, stockpicker, user_id):
        """Adds selected stocks to StockDetail model."""
        from mainapp.models import StockDetail
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(id=user_id)

        # Clear existing selections
        StockDetail.objects.filter(user__id=user_id).delete()

        # Add new selections
        for stock in stockpicker:
            stock_obj, _ = StockDetail.objects.get_or_create(stock=stock)
            stock_obj.user.add(user)

    async def connect(self):
        print("WebSocket connection established")
        import jwt
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from jwt.exceptions import InvalidSignatureError


        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"stock_{self.room_name}"

        # Parse query string
        query_params = parse_qs(self.scope["query_string"].decode())
        print("Query Params:", query_params)

        # Extract token
        token = query_params.get('token', [None])[0]
        if not token:
            print("No token provided")
            await self.close()
            return
        try:
            # Decode token
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_signature": True}
            )
            print("Decoded payload:", payload)
            User = get_user_model()
            user = await sync_to_async(User.objects.get)(id=payload["user_id"])
            self.scope["user"] = user
            self.user_id = user.id
            print(f"Authenticated user: {user.username}")

        except InvalidSignatureError as e:
            print(f"Invalid token signature: {e}")
            print(f"Received token: {token}")
            print(f"Using SECRET_KEY: {settings.JWT_SECRET_KEY}")
            await self.close()
            return
        except Exception as e:
            print(f"Authentication error: {e}")
            await self.close()
            return

        # Extract stock picker
        stockpicker = [item for sublist in query_params.get('stock_picker', []) 
                      for item in sublist.split(",")]
        print("Final Selected Stocks:", stockpicker)

        # Add stocks to Celery Beat and database
        await self.add_to_celery_beat(stockpicker)
        await self.add_to_stock_detail(stockpicker, self.user_id)

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    @sync_to_async
    def remove_user_stocks(self, user_id):
        """Removes the user's stocks and updates Celery Beat accordingly."""
        from mainapp.models import StockDetail
        from django_celery_beat.models import PeriodicTask
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(id=user_id)
        stocks = StockDetail.objects.filter(user__id=user_id)

        # Remove user's stocks from database
        for stock in stocks:
            stock.user.remove(user)
            if stock.user.count() == 0:
                stock.delete()

        # Update Celery Beat task
        task = PeriodicTask.objects.filter(name="every-40-seconds").first()
        if task:
            existing_stocks = set(json.loads(task.args)[0])
            user_stocks = set(stocks.values_list("stock", flat=True))
            updated_stocks = list(existing_stocks - user_stocks)

            if updated_stocks:
                task.args = json.dumps([updated_stocks])
                task.save()
            else:
                task.delete()

    async def disconnect(self, close_code):
        """Handles WebSocket disconnection."""
        if hasattr(self, 'user_id'):
            await self.remove_user_stocks(self.user_id)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """Handles messages from WebSocket clients."""
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")

        await self.channel_layer.group_send(
            self.room_group_name, 
            {"type": "send_stock_update", "message": message}
        )

    @sync_to_async
    def select_user_stocks(self, user_id):
        """Fetches the stocks selected by the user from the database."""
        from mainapp.models import StockDetail
        return list(StockDetail.objects.filter(user__id=user_id).values_list("stock", flat=True))

    async def send_stock_update(self, event):
        """Sends stock updates to clients."""
        if not hasattr(self, 'user_id'):
            return

        user_stocks = await self.select_user_stocks(self.user_id)
        filtered_message = {}

        for stock in user_stocks:
            redis_key = f"candlestick_data:{stock}"
            data = redis_client.get(redis_key)
            if data:
                filtered_message[stock] = json.loads(data)[-1]

        await self.send(text_data=json.dumps(filtered_message))