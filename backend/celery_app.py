from celery import Celery

# Initialize the Celery app with Redis as the broker and backend
app = Celery("price_tracker", broker="redis://broker:6379/0", backend="redis://broker:6379/0")

# Import tasks to register them with Celery
app.autodiscover_tasks(["tasks"])

# Configure Celery
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=2,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 minutes
    task_soft_time_limit=300,  # 5 minutes
)
