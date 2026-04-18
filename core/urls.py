from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('home/', views.dashboard_view, name='dashboard'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Patient
    path('patient/', views.patient_dashboard, name='patient_dashboard'),
    path('doctors/', views.search_doctors, name='search_doctors'),
    path('book/<int:doctor_id>/', views.book_appointment, name='book_appointment'),
    path('cancel/<int:appointment_id>/', views.cancel_appointment, name='cancel_appointment'),
    path('reschedule/<int:appointment_id>/', views.patient_reschedule_request, name='patient_reschedule'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/<int:notif_id>/clear/', views.clear_notification, name='clear_notification'),
    path('notifications/clear-all/', views.clear_all_notifications, name='clear_all_notifications'),
    path('profile/', views.profile_view, name='profile'),
    path('change-password/', views.change_password_view, name='change_password'),

    # Admin specializations
    path('admin-dashboard/chart-data/', views.chart_data_api, name='chart_data_api'),
    path('admin-dashboard/report/', views.generate_report, name='generate_report'),
    path('admin-dashboard/specializations/', views.admin_specializations, name='admin_specializations'),

    # Doctor
    path('doctor/', views.doctor_dashboard, name='doctor_dashboard'),
    path('doctor/today/', views.doctor_today_schedule, name='doctor_today'),
    path('doctor/upcoming/', views.doctor_upcoming, name='doctor_upcoming'),
    path('doctor/schedule/', views.doctor_schedule, name='doctor_schedule'),
    path('doctor/schedule/<int:avail_id>/edit/', views.edit_availability, name='edit_availability'),
    path('doctor/appointment/<int:appointment_id>/', views.manage_appointment, name='manage_appointment'),
    path('doctor/appointment/<int:appointment_id>/notes/', views.add_visit_notes, name='add_visit_notes'),
    path('doctor/appointment/<int:appointment_id>/followup/', views.doctor_followup_appointment, name='doctor_followup'),
    path('doctor/leave/', views.doctor_leave_request, name='doctor_leave_request'),
    path('doctor/leave/<int:leave_id>/cancel/', views.doctor_cancel_leave, name='doctor_cancel_leave'),
    path('doctor/leave/<int:leave_id>/extend/', views.doctor_extend_leave, name='doctor_extend_leave'),
    path('patient/history/', views.patient_medical_history, name='medical_history'),
    path('patient/history/clear/', views.clear_history, name='clear_history'),

    # Admin
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/users/', views.admin_users, name='admin_users'),
    path('admin-dashboard/users/<int:user_id>/toggle/', views.admin_toggle_user, name='admin_toggle_user'),
    path('admin-dashboard/users/<int:user_id>/approve/', views.admin_approve_user, name='admin_approve_user'),
    path('admin-dashboard/users/<int:user_id>/delete/', views.admin_delete_user, name='admin_delete_user'),
    path('admin-dashboard/appointments/', views.admin_appointments, name='admin_appointments'),
    path('admin-dashboard/today/', views.admin_today_appointments, name='admin_today_appointments'),
    path('admin-dashboard/appointments/<int:appointment_id>/complete/', views.admin_complete_appointment, name='admin_complete_appointment'),
    path('admin-dashboard/appointments/<int:appointment_id>/reschedule/', views.admin_reschedule_appointment, name='admin_reschedule_appointment'),
    path('admin-dashboard/emergency/', views.admin_trigger_emergency, name='admin_trigger_emergency'),
    path('admin-dashboard/emergency/<int:emergency_id>/resolve/', views.admin_resolve_emergency, name='admin_resolve_emergency'),
    path('admin-dashboard/medical-records/', views.admin_medical_records, name='admin_medical_records'),

    # Admin doctor management
    path('admin-dashboard/doctors/', views.admin_doctors, name='admin_doctors'),
    path('admin-dashboard/doctors/add/', views.admin_add_doctor, name='admin_add_doctor'),
    path('admin-dashboard/doctors/<int:doctor_id>/edit/', views.admin_edit_doctor, name='admin_edit_doctor'),
    path('admin-dashboard/doctors/<int:doctor_id>/delete/', views.admin_delete_doctor, name='admin_delete_doctor'),
    path('admin-dashboard/doctors/<int:doctor_id>/toggle-availability/', views.admin_toggle_doctor_availability, name='admin_toggle_doctor_availability'),
    path('admin-dashboard/replacement-queue/', views.admin_replacement_queue, name='admin_replacement_queue'),
    path('admin-dashboard/replacement-queue/<int:queue_id>/assign/', views.admin_assign_replacement, name='admin_assign_replacement'),
    path('admin-dashboard/leave-requests/', views.admin_leave_requests, name='admin_leave_requests'),
    path('admin-dashboard/leave-requests/<int:leave_id>/', views.admin_handle_leave, name='admin_handle_leave'),

    # Doctor reschedule
    path('doctor/reschedule-requests/', views.doctor_reschedule_requests, name='doctor_reschedule_requests'),
    path('doctor/reschedule-requests/<int:req_id>/', views.doctor_handle_reschedule, name='doctor_handle_reschedule'),
]
