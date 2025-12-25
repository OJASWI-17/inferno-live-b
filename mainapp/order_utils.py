from decimal import Decimal
from .models import UserStock, UserProfile, Transaction

def buy_stock(user, stock_symbol, quantity, price, order_type='MARKET'):
    """Handle buying stocks - keep original return format but add balance"""
    user_profile = UserProfile.objects.get(user=user)
    total_cost = price * quantity

    if user_profile.balance < total_cost:
        return {"error": "Insufficient balance"}

    # Deduct balance
    user_profile.balance -= total_cost
    user_profile.save()

    # Create transaction record
    Transaction.objects.create(
        user=user,
        stock=stock_symbol,
        quantity=quantity,
        price=price,
        order_type=order_type,
        action='BUY'
    )

    # Update or create UserStock
    user_stock, created = UserStock.objects.get_or_create(
        user=user,
        stock=stock_symbol,
        defaults={"quantity": quantity, "average_price": price, "order_type": order_type}
    )

    if not created:
        total_quantity = user_stock.quantity + quantity
        user_stock.average_price = (
            (user_stock.average_price * user_stock.quantity) + (price * quantity)
        ) / total_quantity
        user_stock.quantity = total_quantity
        user_stock.order_type = order_type
        user_stock.save()

    return {
        "success": True,
        "message": "Purchase successful",
        "balance": float(user_profile.balance),  # Keep original field name
        "stock": stock_symbol,  # Maintain all original return fields
        "quantity": quantity,
        "price": float(price)
    }

def sell_stock(user, stock_symbol, quantity, price, order_type='MARKET'):
    """Handle selling stocks - keep original return format but add balance"""
    try:
        user_profile = UserProfile.objects.get(user=user)
        user_stock = UserStock.objects.get(user=user, stock=stock_symbol)
        
        if user_stock.quantity < quantity:
            return {"error": "Insufficient quantity to sell"}
        
        # Calculate profit
        sale_profit = (Decimal(str(price)) - user_stock.average_price) * Decimal(str(quantity))
        
        # Update profile
        user_profile.cumulative_profit += sale_profit
        user_profile.balance += Decimal(str(price)) * Decimal(str(quantity))
        user_profile.save()

        # Create transaction record
        Transaction.objects.create(
            user=user,
            stock=stock_symbol,
            quantity=quantity,
            price=price,
            order_type=order_type,
            action='SELL'
        )

        # Update holdings
        if user_stock.quantity == quantity:
            user_stock.delete()
        else:
            user_stock.quantity -= quantity
            user_stock.save()

        return {
            "success": True,
            "message": "Sale successful",
            "balance": float(user_profile.balance),  # Keep original field name
            "cumulative_profit": float(user_profile.cumulative_profit),
            "stock": stock_symbol,  # Maintain all original return fields
            "quantity": quantity,
            "price": float(price),
            "sale_profit": float(sale_profit)
        }
    except UserStock.DoesNotExist:
        return {"error": "You do not own this stock"}