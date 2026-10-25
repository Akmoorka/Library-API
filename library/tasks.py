from celery import shared_task


@shared_task(bind=True, max_retries=3, retry_backoff=True, autoretry_for=(Exception,))
def notification_send_task(self, *, notification_id):
    from library import services  # локально: services импортирует tasks

    services.notification_send(notification_id=notification_id)
