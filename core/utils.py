from datetime import datetime, timedelta
from .models import DoctorAvailability, Appointment


def get_available_slots(doctor_profile, date):
    """
    Returns a list of available time slot strings for a given doctor and date.
    Handles multiple availability windows per day. Filters out already booked slots.
    """
    day_of_week = date.weekday()

    availabilities = DoctorAvailability.objects.filter(
        doctor=doctor_profile,
        day_of_week=day_of_week
    ).order_by('start_time')

    if not availabilities.exists():
        return []

    slots = []
    for availability in availabilities:
        current = datetime.combine(date, availability.start_time)
        end = datetime.combine(date, availability.end_time)
        delta = timedelta(minutes=availability.slot_duration)
        window_mins = (end - current).total_seconds() / 60

        # Auto lunch break at midpoint for schedules > 8 hours
        lunch_start = None
        lunch_end = None
        if window_mins > 480:
            midpoint = current + timedelta(minutes=window_mins / 2)
            # Round to nearest 30-min boundary
            mid_mins = midpoint.hour * 60 + midpoint.minute
            mid_mins = (mid_mins // 30) * 30
            lunch_start = current.replace(hour=0, minute=0, second=0) + timedelta(minutes=mid_mins)
            lunch_end = lunch_start + timedelta(minutes=60)

        while current + delta <= end:
            slot_end = current + delta
            # Skip slots overlapping lunch break
            if lunch_start and lunch_end and current < lunch_end and slot_end > lunch_start:
                current = lunch_end
                continue
            slots.append(current.time())
            current += delta

    booked = Appointment.objects.filter(
        doctor=doctor_profile,
        date=date,
        status__in=['pending', 'confirmed']
    ).values_list('start_time', flat=True)

    return [s for s in slots if s not in booked]


def notify(user, message):
    """Create an in-app notification for a user."""
    from .models import Notification
    Notification.objects.create(user=user, message=message)


def send_email_notification(to_email, subject, message):
    """Send an email notification in a background thread. Never blocks the request."""
    import threading
    from django.core.mail import send_mail
    from django.conf import settings
    import logging
    logger = logging.getLogger(__name__)

    def _send():
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                fail_silently=False,
            )
            logger.info(f'Email sent to {to_email}: {subject}')
        except Exception as e:
            logger.error(f'Failed to send email to {to_email}: {e}')

    threading.Thread(target=_send, daemon=True).start()

