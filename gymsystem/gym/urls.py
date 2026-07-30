from django.urls import path
from .views import *

urlpatterns = [

    # ==========================
    # Public Pages & Search
    # ==========================
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("plans/", plans, name="plans"),
    path("contact/", contact, name="contact"),
    path("feedback/", feedback, name="feedback"),
    path("search/", global_search, name="global_search"),
    path("gallery/", gallery_view, name="gallery_view"),
    path("gallery/add/", gallery_add, name="gallery_add"),
    path("gallery/delete/<int:item_id>/", gallery_delete, name="gallery_delete"),
    path("announcements/", announcement_list, name="announcement_list"),
    path("announcements/add/", announcement_add, name="announcement_add"),
    path("announcements/delete/<int:ann_id>/", announcement_delete, name="announcement_delete"),

    # ==========================
    # Authentication & OTP
    # ==========================
    path("admin_login/", admin_login_view, name="admin_login"),
    path("admin-otp-verify/", admin_otp_verify, name="admin_otp_verify"),
    path("member/login/", member_login, name="member_login"),
    path("member-live-verify/", member_live_verify, name="member_live_verify"),
    path("member_register/", member_register, name="member_register"),
    path("otp-verify/", otp_verify, name="otp_verify"),
    path("forgot-password/", forgot_password_view, name="forgot_password"),
    path("reset-password-otp/", reset_password_otp_view, name="reset_password_otp"),
    path("logout/", logout_view, name="logout"),

    # ==========================
    # Admin Dashboard & AI Insights
    # ==========================
    path("admin_dashboard/", admin_dashboard, name="admin_dashboard"),
    path("admin/ai-insights/", admin_ai_insights, name="admin_ai_insights"),
    path("admin/qr-attendance/", admin_qr_attendance, name="admin_qr_attendance"),

    # ==========================
    # Membership Plans
    # ==========================
    path("admin_plans_list/", admin_plans_list, name="admin_plans_list"),
    path("admin_plans_add/", admin_plans_add, name="admin_plans_add"),
    path("admin_plan_edit/<int:plan_id>/", admin_plan_edit, name="admin_plan_edit"),
    path("admin_plans_delete/<int:plan_id>/", admin_plans_delete, name="admin_plans_delete"),

    # ==========================
    # Trainers
    # ==========================
    path("admin_trainer_list/", admin_trainer_list, name="admin_trainer_list"),
    path("admin_trainer_add/", admin_trainer_add, name="admin_trainer_add"),
    path("admin_trainer_edit/<int:trainer_id>/", admin_trainer_edit, name="admin_trainer_edit"),
    path("admin_trainer_delete/<int:trainer_id>/", admin_trainer_delete, name="admin_trainer_delete"),

    # ==========================
    # Members
    # ==========================
    path("admin_member_list/", admin_member_list, name="admin_member_list"),
    path("admin_member_add/", admin_member_add, name="admin_member_add"),
    path("admin_member_edit/<int:member_id>/", admin_member_edit, name="admin_member_edit"),
    path("admin_member_delete/<int:member_id>/", admin_member_delete, name="admin_member_delete"),

    # ==========================
    # Attendance
    # ==========================
    path("admin_attendence_list/", admin_attendence_list, name="admin_attendence_list"),
    path("admin_attendance_add/", admin_attendance_add, name="admin_attendance_add"),

    # ==========================
    # Equipment
    # ==========================
    path("admin_equipment_list/", admin_equipment_list, name="admin_equipment_list"),
    path("admin_equipment_add/", admin_equipment_add, name="admin_equipment_add"),
    path("admin_equipment_edit/<int:equipment_id>/", admin_equipment_edit, name="admin_equipment_edit"),
    path("admin_equipment_delete/<int:equipment_id>/", admin_equipment_delete, name="admin_equipment_delete"),

    # ==========================
    # Enquiries
    # ==========================
    path("admin_enquiry_list/", admin_enquiry_list, name="admin_enquiry_list"),
    path("admin_enquiry_status/<int:enquiry_id>/update/", admin_enquiry_update_status, name="admin_enquiry_update_status"),

    # ==========================
    # Workout Plans
    # ==========================
    path("admin_workout_plan_list/", admin_workout_plan_list, name="admin_workout_plan_list"),
    path("admin_workout_plan_add/", admin_workout_plan_add, name="admin_workout_plan_add"),
    path("admin_workout_plan_edit/<int:plan_id>/", admin_workout_plan_edit, name="admin_workout_plan_edit"),
    path("admin_workout_plan_delete/<int:plan_id>/", admin_workout_plan_delete, name="admin_workout_plan_delete"),

    # ==========================
    # Payments
    # ==========================
    path("admin_payment_list/", admin_payment_list, name="admin_payment_list"),
    path("admin_payment_add/", admin_payment_add, name="admin_payment_add"),
    path("admin_payment_edit/<int:payment_id>/", admin_payment_edit, name="admin_payment_edit"),
    path("admin_payment_delete/<int:payment_id>/", admin_payment_delete, name="admin_payment_delete"),

    # ==========================
    # Diet Plans
    # ==========================
    path("admin_diet_plan_list/", admin_diet_plan_list, name="admin_diet_plan_list"),
    path("admin_diet_plan_add/", admin_diet_plan_add, name="admin_diet_plan_add"),
    path("admin_diet_plan_edit/<int:plan_id>/", admin_diet_plan_edit, name="admin_diet_plan_edit"),
    path("admin_diet_plan_delete/<int:plan_id>/", admin_diet_plan_delete, name="admin_diet_plan_delete"),

    # ==========================
    # Notifications
    # ==========================
    path("admin_notifications/", admin_notifications, name="admin_notifications"),

    # ==========================
    # Exports & Printables
    # ==========================
    path("export/members/csv/", export_members_csv, name="export_members_csv"),
    path("export/payments/csv/", export_payments_csv, name="export_payments_csv"),
    path("export/attendance/csv/", export_attendance_csv, name="export_attendance_csv"),
    path("member/card/pdf/<int:member_id>/", member_card_printable, name="member_card_printable"),
    path("payment/invoice/pdf/<int:payment_id>/", payment_invoice_printable, name="payment_invoice_printable"),

    # ==========================
    # Member Area & AI Advisor
    # ==========================
    path("member/dashboard/", member_dashboard, name="member_dashboard"),
    path("member/ai-recommendations/", member_ai_recommendations, name="member_ai_recommendations"),
    path("member/workout/", member_my_workout, name="member_my_workout"),
    path("member/diet/", member_my_diet, name="member_my_diet"),
    path("member/attendance/", member_my_attendance, name="member_my_attendance"),
    path("member/payments/", member_my_payments, name="member_my_payments"),
]