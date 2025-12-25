from django.apps import AppConfig
import redis
from django.db.models.signals import post_migrate

def reset_orders_and_balance():
    """Clear the UserStock and LimitOrder tables and reset UserProfile balance."""
    from .models import UserStock, LimitOrder, UserProfile ,Transaction

    try:
        # Delete all UserStock entries
        UserStock.objects.all().delete()
        print("UserStock table cleared on startup!")

        # Delete all LimitOrder entries
        LimitOrder.objects.all().delete()
        print("LimitOrder table cleared on startup!")

        # Reset UserProfile balance
        UserProfile.objects.all().update(balance=10000.00)  # Set default balance
        print("UserProfile balance reset on startup!")
        
        Transaction.objects.all().delete()
        print("order_history table cleared on startup!")
    except Exception as e:
        print(f"Error resetting orders and balance: {e}")

class MainappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mainapp'

    def ready(self):
        """Flush Redis and reset orders and balance after the app is ready."""
        try:
            # Flush Redis
            redis_client = redis.StrictRedis(host="localhost", port=6379, db=0, decode_responses=True)
            redis_client.flushdb()
            print("Redis database cleared on startup!")
        except Exception as e:
            print(f"Error clearing Redis: {e}")

        # Reset orders and balance
        reset_orders_and_balance()