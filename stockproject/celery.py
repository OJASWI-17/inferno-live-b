from __future__ import absolute_import, unicode_literals
import os
from  celery import Celery
from django.conf import settings
from celery.schedules import crontab  # Import crontab for scheduling

# from celery.schedules import crontab # crontab - allocating periodic tasks

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stockproject.settings')

app = Celery('stockproject')
app.conf.enable_utc = False
app.conf.update(timezone='Asia/Kolkata')    

app.config_from_object(settings, namespace='CELERY')


app.conf.beat_schedule = {
    'process-limit-orders-every-1-seconds': {
        'task': 'mainapp.tasks.process_limit_orders',  # Task path
        'schedule': 1.0,  # Run every 1 seconds
    },
}

app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')




