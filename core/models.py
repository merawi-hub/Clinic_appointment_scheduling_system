from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='patient')
    phone = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class Specialization(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = models.ForeignKey(Specialization, on_delete=models.SET_NULL, null=True, blank=True)
    bio = models.TextField(blank=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username}"


class DoctorAvailability(models.Model):
    DAY_CHOICES = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration = models.IntegerField(default=30, help_text="Slot duration in minutes (15, 30, 45, 60, 90, 120, 150, 180)")

    class Meta:
        unique_together = ('doctor', 'day_of_week', 'start_time')

    def __str__(self):
        return f"{self.doctor} - {self.get_day_of_week_display()} {self.start_time}–{self.end_time}"


class Appointment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('rescheduled', 'Rescheduled'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('delayed', 'Delayed'),
    )
    appointment_ref = models.CharField(max_length=20, unique=True, blank=True)  # e.g. AC-20260414-0001
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    patient_email = models.EmailField(blank=True)   # captured at booking time
    patient_phone = models.CharField(max_length=15, blank=True)  # captured at booking time
    follow_up_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='follow_ups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'start_time']

    def save(self, *args, **kwargs):
        if not self.appointment_ref:
            from datetime import date as d
            import random, string
            prefix = f"AC-{d.today().strftime('%Y%m%d')}"
            suffix = ''.join(random.choices(string.digits, k=4))
            self.appointment_ref = f"{prefix}-{suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.appointment_ref}] {self.patient.username} → {self.doctor} on {self.date} at {self.start_time} [{self.status}]"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:50]}"


class DoctorReplacementQueue(models.Model):
    """Tracks patients waiting for a replacement doctor after their doctor was removed."""
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='replacement_queue')
    specialization = models.ForeignKey(Specialization, on_delete=models.SET_NULL, null=True)
    original_doctor_name = models.CharField(max_length=100)
    original_date = models.DateField()
    original_time = models.TimeField()
    status = models.CharField(max_length=20, default='waiting',
                              choices=[('waiting','Waiting'),('assigned','Assigned'),('cancelled','Cancelled')])
    assigned_doctor = models.ForeignKey(DoctorProfile, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.patient.username} waiting for {self.specialization} replacement"


class LeaveRequest(models.Model):
    LEAVE_TYPE_CHOICES = (
        ('vacation', 'Vacation / Annual Leave'),
        ('sick', 'Sick Leave'),
        ('training', 'Training'),
        ('personal', 'Personal'),
        ('other', 'Other'),
        ('extension', 'Leave Extension'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES, default='vacation')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.doctor} — {self.get_leave_type_display()} ({self.start_date} to {self.end_date}) [{self.status}]"


class CustomScheduleRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='custom_schedule_requests')
    day_of_week = models.IntegerField(choices=DoctorAvailability.DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration = models.IntegerField(default=30)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.doctor} — Custom schedule {self.get_day_of_week_display()} [{self.status}]"


class EmergencyCase(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('resolved', 'Resolved'),
    )
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='emergencies')
    patient_name = models.CharField(max_length=100)
    patient_phone = models.CharField(max_length=15, blank=True)
    estimated_duration = models.IntegerField(default=30, help_text='Estimated duration in minutes')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-triggered_at']

    def __str__(self):
        return f"Emergency: {self.patient_name} → {self.doctor} [{self.status}]"


class RescheduleRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    appointment = models.ForeignKey('Appointment', on_delete=models.CASCADE, related_name='reschedule_requests')
    requested_date = models.DateField()
    requested_time = models.TimeField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Reschedule [{self.appointment.appointment_ref}] → {self.requested_date} {self.requested_time} [{self.status}]"


class ProfileChangeRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_requests')
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    new_password = models.CharField(max_length=128, blank=True)  # hashed
    request_type = models.CharField(max_length=20, default='profile')  # 'profile' or 'password'
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.request_type} change request by {self.user.username} [{self.status}]"
