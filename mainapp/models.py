from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=10000.00)  # Default balance , 
    cumulative_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # New field

    def __str__(self):
        return f"{self.user.username}'s Profile"

class StockDetail(models.Model): # this model is created bcoz we want to store the stocks available in the market
    stock = models.CharField(max_length=10)
    user = models.ManyToManyField(User)

    def __str__(self):
        return self.stock
    
    
    
    


class UserStock(models.Model):# this model is created bcoz we want to store the stocks bought by the user
    ORDER_TYPES = [
        ('MARKET', 'Market'),
        ('LIMIT', 'Limit'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    stock = models.CharField(max_length=10)
    quantity = models.PositiveIntegerField(default=0)
    average_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    order_type = models.CharField(max_length=6, choices=ORDER_TYPES, default='MARKET')  # New field

    def __str__(self):
        return f"{self.user.username} - {self.stock} ({self.quantity} shares)"



class LimitOrder(models.Model): # this model is created bcoz we want to store the limit orders placed by the user 
    ORDER_TYPES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    stock = models.CharField(max_length=10)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2) # this price is the price at which the user wants to buy or sell the stock
    order_type = models.CharField(max_length=4, choices=ORDER_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)  # Add created_at field

    def __str__(self):
        return f"{self.order_type} {self.quantity} shares of {self.stock} at ${self.price}"
    
    
class Transaction(models.Model):
    ORDER_TYPES = [
        ('MARKET', 'Market'),
        ('LIMIT', 'Limit'),
    ]
    ACTIONS = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    stock = models.CharField(max_length=10)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    order_type = models.CharField(max_length=6, choices=ORDER_TYPES)
    action = models.CharField(max_length=4, choices=ACTIONS)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} {self.quantity} {self.stock} @ {self.price} ({self.order_type})"  
    
    
    