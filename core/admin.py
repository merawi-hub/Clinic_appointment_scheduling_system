from django.contrib import admin
from .models import User, Specialization, DoctorProfile, DoctorAvailability, Appointment, Notification, ProfileChangeRequest, DoctorReplacementQueue

admin.site.register(User)
admin.site.register(Specialization)
admin.site.register(DoctorProfile)
admin.site.register(DoctorAvailability)
admin.site.register(Appointment)
admin.site.register(Notification)
admin.site.register(ProfileChangeRequest)
admin.site.register(DoctorReplacementQueue)
