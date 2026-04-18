def notifications_count(request):
    if request.user.is_authenticated:
        from .models import Notification, DoctorReplacementQueue, LeaveRequest, RescheduleRequest
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        waiting = 0
        pending_leave_count = 0
        pending_reschedule_count = 0
        reschedule_pending_count = 0
        if request.user.is_superuser or request.user.role == 'admin':
            waiting = DoctorReplacementQueue.objects.filter(status='waiting').count()
            pending_leave_count = LeaveRequest.objects.filter(status='pending').count()
            pending_reschedule_count = RescheduleRequest.objects.filter(status='pending').count()
        if request.user.role == 'doctor':
            try:
                from .models import DoctorProfile
                dp = DoctorProfile.objects.get(user=request.user)
                reschedule_pending_count = RescheduleRequest.objects.filter(
                    appointment__doctor=dp, status='pending'
                ).count()
            except Exception:
                pass
        return {
            'unread_notifications': count,
            'waiting_count': waiting,
            'pending_leave_count': pending_leave_count,
            'pending_reschedule_count': pending_reschedule_count,
            'reschedule_pending_count': reschedule_pending_count,
        }
    return {'unread_notifications': 0, 'waiting_count': 0, 'pending_leave_count': 0,
            'pending_reschedule_count': 0, 'reschedule_pending_count': 0}
