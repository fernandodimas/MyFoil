# Fix MonkeyPatchWarning and Threading errors by patching EARLY
from gevent import monkey
monkey.patch_all()

from celery import Celery
import os
import logging
import sys

# DEBUG: Force file logging immediately
data_dir = os.path.join(os.getcwd(), 'data')
if not os.path.exists(data_dir):
    try:
        os.makedirs(data_dir)
    except:
        pass

log_file = os.path.join(data_dir, 'celery_debug.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.info("Celery App initializing...")

def make_celery(app_name=__name__):
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    celery = Celery(
        app_name,
        broker=redis_url,
        backend=redis_url,
        include=['tasks']
    )
    
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
    
    return celery

celery = make_celery('myfoil')
