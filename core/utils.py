from datetime import datetime, timedelta, date as date_type
from .models import DoctorAvailability, Appointment


def cleanup_past_schedules(doctor_profile):
    """
    Auto-delete DoctorAvailability records where the most recent occurrence
    of that day of week has passed AND there are no future booked appointments
    on that day of week.
    
    This treats schedules as one-time (for the next occurrence of that day),
    not recurring weekly.
    """
    today = date_type.today()
    availabilities = list(DoctorAvailability.objects.filter(doctor=doctor_profile))
    
    for avail in availabilities:
        dow = avail.day_of_week  # 0=Monday ... 6=Sunday
        
        # Find the most recent past occurrence of this day of week (not today)
        days_since = (today.weekday() - dow) % 7
        if days_since == 0:
            # The schedule day is today — don't delete yet
            continue
        
        most_recent_past = today - timedelta(days=days_since)
        
        # Check if there are any future appointments on this specific day of week
        # by scanning the next 60 days for dates matching this day of week
        future_bookings = False
        check_date = today
        for _ in range(60):
            if check_date.weekday() == dow:
                if Appointment.objects.filter(
                    doctor=doctor_profile,
                    date=check_date,
                    status__in=['pending', 'confirmed', 'rescheduled']
                ).exists():
                    future_bookings = True
                    break
            check_date += timedelta(days=1)
        
        if not future_bookings:
            # No future bookings on this day of week — delete the schedule
            avail.delete()


def get_available_slots(doctor_profile, date):
    """
    Returns a list of available time slot strings for a given doctor and date.
    Handles multiple availability windows per day. Filters out already booked slots.
    For today: filters out past slots AND slots within the next 30 minutes (booking buffer).
    """
    day_of_week = date.weekday()

    availabilities = DoctorAvailability.objects.filter(
        doctor=doctor_profile,
        day_of_week=day_of_week
    ).order_by('start_time')

    if not availabilities.exists():
        return []

    # For today, calculate the minimum bookable time (now + 30 min buffer)
    is_today = (date == date_type.today())
    min_time = None
    if is_today:
        min_time = (datetime.now() + timedelta(minutes=30)).time()

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
            # For today: skip past slots and slots within 30-min buffer
            if is_today and min_time and current.time() < min_time:
                current += delta
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

