import json
import random
import base64
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta

from .models import *
from .ai_engine import AIEngine
from .utils import generate_qr_code_base64, attach_qr_to_member, export_to_csv, send_system_email


# ══════════════════════════════════════════
#  DECORATORS
# ══════════════════════════════════════════

def admin_required(view_func):
    """Decorator to restrict access to admin users only."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or getattr(request.user, 'role', None) != 'ADMIN':
            messages.error(request, 'You must be an admin to access this page.')
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def member_required(view_func):
    """Decorator to restrict access to member users only."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or getattr(request.user, 'role', None) != 'MEMBER':
            messages.error(request, 'You must be a member to access this page.')
            return redirect('member_login')
        return view_func(request, *args, **kwargs)
    return wrapper


# ══════════════════════════════════════════
#  AUTHENTICATION & OTP FLOWS
# ══════════════════════════════════════════

def admin_login_view(request):
    if request.user.is_authenticated:
        if request.user.role == "ADMIN":
            return redirect("admin_dashboard")
        return redirect("member_dashboard")

    if request.method == "POST":
        username_or_email = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user_obj = User.objects.filter(Q(username=username_or_email) | Q(email=username_or_email)).first()

        if user_obj:
            if user_obj.is_locked():
                messages.error(request, "Account locked due to multiple failed login attempts. Please try again after 15 minutes.")
                return render(request, "admin_login.html")

            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None and user.role == "ADMIN":
                user.failed_login_attempts = 0
                user.account_locked_until = None
                user.last_login_ip = request.META.get('REMOTE_ADDR')
                user.save()
                
                # Send Email OTP instead of logging in immediately
                otp_val = str(random.randint(100000, 999999))
                OTP.objects.create(user=user, otp=otp_val, purpose="ADMIN_LOGIN")
                
                send_system_email(
                    "FitPro GYM — Admin Login OTP",
                    f"Hello {user.username},\n\nYour OTP for admin login verification is: {otp_val}\nIt expires in 10 minutes.",
                    user.email
                )
                
                request.session['admin_verify_user_id'] = user.id
                messages.info(request, f"OTP sent to {user.email} for verification. (Demo OTP: {otp_val})")
                return redirect("admin_otp_verify")
            else:
                user_obj.failed_login_attempts += 1
                if user_obj.failed_login_attempts >= 5:
                    user_obj.account_locked_until = timezone.now() + timedelta(minutes=15)
                    messages.error(request, "Account locked! 5 consecutive failed attempts. Locked for 15 mins.")
                else:
                    messages.error(request, f"Invalid password. ({5 - user_obj.failed_login_attempts} attempts remaining)")
                user_obj.save()
                return render(request, "admin_login.html")
        else:
            messages.error(request, "Invalid username or email.")

    return render(request, "admin_login.html")


def member_login(request):
    if request.user.is_authenticated:
        if request.user.role == "MEMBER":
            return redirect("member_dashboard")
        return redirect("admin_dashboard")

    if request.method == "POST":
        username_or_email = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user_obj = User.objects.filter(Q(username=username_or_email) | Q(email=username_or_email)).first()

        if user_obj:
            if user_obj.is_locked():
                messages.error(request, "Account locked due to multiple wrong password attempts. Try again in 15 mins.")
                return render(request, "member_login.html")

            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None and user.role == "MEMBER":
                user.failed_login_attempts = 0
                user.account_locked_until = None
                user.last_login_ip = request.META.get('REMOTE_ADDR')
                user.save()
                
                # Redirect to live verification instead of logging in
                request.session['member_live_verify_user_id'] = user.id
                return redirect("member_live_verify")
            else:
                user_obj.failed_login_attempts += 1
                if user_obj.failed_login_attempts >= 5:
                    user_obj.account_locked_until = timezone.now() + timedelta(minutes=15)
                    messages.error(request, "Account locked for 15 minutes due to 5 wrong password attempts.")
                else:
                    messages.error(request, f"Invalid password. ({5 - user_obj.failed_login_attempts} attempts left)")
                user_obj.save()
                return render(request, "member_login.html")
        else:
            messages.error(request, "No account found with this username or email.")

    return render(request, "member_login.html")


def admin_otp_verify(request):
    user_id = request.session.get('admin_verify_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect("admin_login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        input_otp = request.POST.get("otp", "").strip()
        otp_obj = OTP.objects.filter(user=user, otp=input_otp, purpose="ADMIN_LOGIN", is_used=False).first()

        if otp_obj and not otp_obj.is_expired:
            otp_obj.is_used = True
            otp_obj.save()
            del request.session['admin_verify_user_id']
            login(request, user)
            messages.success(request, f"Welcome back Admin {user.get_full_name() or user.username}!")
            return redirect("admin_dashboard")
        else:
            messages.error(request, "Invalid or expired OTP code.")

    return render(request, "admin_otp_verify.html", {"user": user})


def member_live_verify(request):
    user_id = request.session.get('member_live_verify_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect("member_login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        image_data = request.POST.get('image_data')
        if image_data:
            format, imgstr = image_data.split(';base64,') 
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr), name=f'{user.username}_live.{ext}')
            
            # Save verification record
            LoginVerification.objects.create(
                user=user,
                photo=data,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            del request.session['member_live_verify_user_id']
            login(request, user)
            messages.success(request, f"Live Verification Successful! Welcome {user.first_name or user.username}!")
            return redirect("member_dashboard")
        else:
            messages.error(request, "Failed to capture image. Please try again.")

    return render(request, "member_live_verify.html", {"user": user})


def member_register(request):
    if request.user.is_authenticated:
        if request.user.role == "MEMBER":
            return redirect("member_dashboard")
        return redirect("admin_dashboard")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        full_name = request.POST.get("full_name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        fitness_goal = request.POST.get("fitness_goal", "WEIGHT_LOSS")

        if not (username and email and password and full_name and mobile):
            messages.error(request, "Please fill all required fields.")
            return redirect("member_register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return redirect("member_register")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect("member_register")

        user = User.objects.create_user(
            username=username, email=email, password=password, role="MEMBER"
        )
        member = MemberProfile.objects.create(
            user=user, full_name=full_name, mobile=mobile, fitness_goal=fitness_goal
        )

        # Generate QR Code for Member
        attach_qr_to_member(member)

        # Create OTP
        otp_val = str(random.randint(100000, 999999))
        OTP.objects.create(user=user, otp=otp_val, purpose="REGISTER")

        # Send Email
        send_system_email(
            "FitPro GYM — Registration Verification OTP",
            f"Hello {full_name},\n\nYour OTP for registration verification is: {otp_val}\nIt expires in 10 minutes.",
            email
        )

        request.session['verify_user_id'] = user.id
        messages.info(request, f"Account created! An OTP has been sent to {email}. (Demo OTP: {otp_val})")
        return redirect("otp_verify")

    return render(request, "member_register.html")


def otp_verify(request):
    user_id = request.session.get('verify_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please register again.")
        return redirect("member_register")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        input_otp = request.POST.get("otp", "").strip()
        otp_obj = OTP.objects.filter(user=user, otp=input_otp, purpose="REGISTER", is_used=False).first()

        if otp_obj and not otp_obj.is_expired:
            otp_obj.is_used = True
            otp_obj.save()
            user.is_email_verified = True
            user.save()
            del request.session['verify_user_id']
            login(request, user)
            messages.success(request, "Email verified successfully! Welcome to FitPro GYM!")
            return redirect("member_dashboard")
        else:
            messages.error(request, "Invalid or expired OTP code.")

    return render(request, "otp_verify.html", {"user": user})


def forgot_password_view(request):
    if request.method == "POST":
        email_or_username = request.POST.get("email_or_username", "").strip()
        user = User.objects.filter(Q(email=email_or_username) | Q(username=email_or_username)).first()

        if user:
            otp_val = str(random.randint(100000, 999999))
            OTP.objects.create(user=user, otp=otp_val, purpose="FORGOT_PASSWORD")

            send_system_email(
                "FitPro GYM — Password Reset OTP",
                f"Hello {user.username},\n\nYour OTP to reset your password is: {otp_val}\nExpires in 10 minutes.",
                user.email
            )
            request.session['reset_user_id'] = user.id
            messages.success(request, f"OTP sent to your email! (Demo OTP: {otp_val})")
            return redirect("reset_password_otp")
        else:
            messages.error(request, "No user found with that email or username.")

    return render(request, "forgot_password.html")


def reset_password_otp_view(request):
    user_id = request.session.get('reset_user_id')
    if not user_id:
        return redirect("forgot_password")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        input_otp = request.POST.get("otp", "").strip()
        new_password = request.POST.get("new_password", "").strip()

        otp_obj = OTP.objects.filter(user=user, otp=input_otp, purpose="FORGOT_PASSWORD", is_used=False).first()
        if otp_obj and not otp_obj.is_expired:
            otp_obj.is_used = True
            otp_obj.save()
            user.set_password(new_password)
            user.failed_login_attempts = 0
            user.account_locked_until = None
            user.save()
            del request.session['reset_user_id']
            messages.success(request, "Password reset successful! You can now log in.")
            return redirect("member_login" if user.role == "MEMBER" else "admin_login")
        else:
            messages.error(request, "Invalid or expired OTP.")

    return render(request, "reset_password_otp.html", {"user": user})


def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("home")


# ══════════════════════════════════════════
#  PUBLIC PAGES & GALLERY
# ══════════════════════════════════════════

def home(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        subject = request.POST.get("subject", "").strip()
        enquiry_message = request.POST.get("message", "").strip()

        if name and email and mobile and enquiry_message:
            Enquiry.objects.create(
                name=name, email=email, mobile=mobile,
                subject=subject, message=enquiry_message,
            )
            messages.success(request, "Your enquiry has been submitted successfully.")
            return redirect("home")
        messages.error(request, "Please fill all the required fields.")

    trainers = Trainer.objects.filter(is_active=True)[:6]
    plans = MembershipPlan.objects.filter(is_active=True)[:4]
    feedbacks = Feedback.objects.filter(is_public=True)[:6]
    announcements = Announcement.objects.filter(is_active=True)[:4]
    gallery_items = GalleryItem.objects.all()[:8]

    total_members = MemberProfile.objects.count()
    total_trainers = Trainer.objects.filter(is_active=True).count()
    total_equipment = Equipment.objects.filter(is_active=True).count()

    return render(request, "home.html", {
        "trainers": trainers,
        "plans": plans,
        "feedbacks": feedbacks,
        "announcements": announcements,
        "gallery_items": gallery_items,
        "total_members": total_members,
        "total_trainers": total_trainers,
        "total_equipment": total_equipment,
    })


def about(request):
    trainers = Trainer.objects.filter(is_active=True)
    return render(request, "about.html", {"trainers": trainers})


def plans(request):
    plans = MembershipPlan.objects.filter(is_active=True)
    return render(request, "plans.html", {"plans": plans})


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        if name and email and message:
            Enquiry.objects.create(
                name=name, email=email, mobile=mobile or "N/A",
                subject=subject, message=message,
            )
            messages.success(request, "Your message has been sent!")
            return redirect("contact")
    return render(request, "contact.html")


def gallery_view(request):
    category_filter = request.GET.get("category", "")
    items = GalleryItem.objects.all()
    if category_filter:
        items = items.filter(category=category_filter)
    return render(request, "gallery.html", {
        "items": items,
        "category_filter": category_filter,
    })


@admin_required
def gallery_add(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        category = request.POST.get("category", "GYM_PHOTO")
        description = request.POST.get("description", "").strip()
        video_url = request.POST.get("video_url", "").strip()
        image = request.FILES.get("image")

        if title:
            GalleryItem.objects.create(
                title=title, category=category, description=description,
                video_url=video_url, image=image
            )
            messages.success(request, "Gallery item added!")
            return redirect("gallery_view")
    return redirect("gallery_view")


@admin_required
def gallery_delete(request, item_id):
    item = get_object_or_404(GalleryItem, id=item_id)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Gallery item deleted.")
    return redirect("gallery_view")


def feedback(request):
    if request.method == "POST":
        member_id = request.POST.get("member")
        message = request.POST.get("message")
        rating = request.POST.get("rating")
        is_public = request.POST.get("is_public") == "on"

        Feedback.objects.create(
            member_id=member_id,
            message=message,
            rating=rating,
            is_public=is_public
        )
        messages.success(request, "Thank you! Your feedback has been submitted.")
        return redirect("feedback")

    members = MemberProfile.objects.all()
    feedbacks = Feedback.objects.select_related('member').all().order_by('-created_at')
    return render(request, "feedback.html", {"members": members, "feedbacks": feedbacks})


# ══════════════════════════════════════════
#  GLOBAL SEARCH
# ══════════════════════════════════════════

def global_search(request):
    query = request.GET.get("q", "").strip()
    members = []
    trainers = []
    equipments = []
    payments = []
    workouts = []

    if query:
        members = MemberProfile.objects.filter(Q(full_name__icontains=query) | Q(mobile__icontains=query))
        trainers = Trainer.objects.filter(Q(name__icontains=query) | Q(specialization__icontains=query))
        equipments = Equipment.objects.filter(Q(name__icontains=query) | Q(category__icontains=query) | Q(brand__icontains=query))
        payments = Payment.objects.filter(Q(invoice_no__icontains=query) | Q(member__full_name__icontains=query))
        workouts = WorkoutPlan.objects.filter(Q(exercise_name__icontains=query) | Q(title__icontains=query))

    return render(request, "search_results.html", {
        "query": query,
        "members": members,
        "trainers": trainers,
        "equipments": equipments,
        "payments": payments,
        "workouts": workouts,
    })


# ══════════════════════════════════════════
#  ADMIN DASHBOARD & AI INSIGHTS
# ══════════════════════════════════════════

@admin_required
def admin_dashboard(request):
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year

    total_members = MemberProfile.objects.count()
    active_members = MemberProfile.objects.filter(membership_end__gte=today).count()
    total_trainers = Trainer.objects.filter(is_active=True).count()
    today_attendance = Attendance.objects.filter(date=today, status="PRESENT").count()
    pending_payments = Payment.objects.filter(status="PENDING").count()
    new_enquiries = Enquiry.objects.filter(status="NEW").count()
    monthly_revenue = Payment.objects.filter(
        payment_date__month=current_month,
        payment_date__year=current_year,
        status="PAID"
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Revenue forecast engine
    forecast = AIEngine.calculate_revenue_forecast()

    # Revenue chart data
    revenue_data = forecast["historical_data"]
    revenue_labels = forecast["historical_labels"]

    # Attendance chart data (last 7 days)
    attendance_labels = []
    attendance_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Attendance.objects.filter(date=day, status="PRESENT").count()
        attendance_labels.append(day.strftime("%a %d"))
        attendance_data.append(count)

    # Plan distribution
    plan_data = list(MembershipPlan.objects.annotate(count=Count('members')).values('name', 'count'))
    plan_labels = [p['name'] for p in plan_data]
    plan_counts = [p['count'] for p in plan_data]

    # At risk dropout members prediction
    at_risk_members = AIEngine.predict_attendance_dropout_risk()[:5]

    recent_members = MemberProfile.objects.select_related('plan', 'trainer').order_by('-created_at')[:5]
    recent_payments = Payment.objects.select_related('member').order_by('-payment_date')[:5]
    expiring_soon = MemberProfile.objects.filter(
        membership_end__gte=today,
        membership_end__lte=today + timedelta(days=7)
    ).count()

    return render(request, 'admin_dashboard.html', {
        'total_members': total_members,
        'active_members': active_members,
        'total_trainers': total_trainers,
        'today_attendance': today_attendance,
        'pending_payments': pending_payments,
        'new_enquiries': new_enquiries,
        'monthly_revenue': monthly_revenue,
        'expiring_soon': expiring_soon,
        'at_risk_members': at_risk_members,
        'projected_next_month': forecast["projected_next_month"],
        'revenue_labels': json.dumps(revenue_labels),
        'revenue_data': json.dumps(revenue_data),
        'attendance_labels': json.dumps(attendance_labels),
        'attendance_data': json.dumps(attendance_data),
        'plan_labels': json.dumps(plan_labels),
        'plan_counts': json.dumps(plan_counts),
        'recent_members': recent_members,
        'recent_payments': recent_payments,
        'today': today,
    })


@admin_required
def admin_ai_insights(request):
    """
    Dedicated AI Performance & Predictive Analytics Center.
    """
    at_risk_list = AIEngine.predict_attendance_dropout_risk()
    forecast = AIEngine.calculate_revenue_forecast()

    # Trainer Performance Analytics
    trainers = Trainer.objects.all()
    trainer_stats = []
    for t in trainers:
        m_count = t.members.count()
        present_sessions = Attendance.objects.filter(member__trainer=t, status="PRESENT").count()
        trainer_stats.append({
            "trainer": t,
            "assigned_count": m_count,
            "session_count": present_sessions,
        })

    return render(request, "admin_ai_insights.html", {
        "at_risk_list": at_risk_list,
        "forecast": forecast,
        "trainer_stats": trainer_stats,
        "forecast_labels": json.dumps(forecast["historical_labels"] + forecast["forecast_labels"]),
        "forecast_data": json.dumps(forecast["historical_data"] + forecast["forecast_data"]),
    })


@admin_required
def admin_qr_attendance(request):
    """
    QR Attendance Scanner Page.
    Marks member attendance dynamically via scanned QR string or Member ID.
    """
    today = timezone.now().date()
    scanned_member = None
    attendance_marked = False

    if request.method == "POST":
        qr_input = request.POST.get("qr_code_data", "").strip()
        member_id = None

        if "FITPRO-MEMBER-ID:" in qr_input:
            try:
                member_id = int(qr_input.split("FITPRO-MEMBER-ID:")[1].split("|")[0])
            except Exception:
                member_id = None
        else:
            try:
                member_id = int(qr_input)
            except ValueError:
                member_id = None

        if member_id:
            member = MemberProfile.objects.filter(id=member_id).first()
            if member:
                scanned_member = member
                attendance, created = Attendance.objects.get_or_create(
                    member=member, date=today,
                    defaults={"time_in": timezone.now().time(), "status": "PRESENT"}
                )
                if not created:
                    attendance.status = "PRESENT"
                    attendance.save()
                attendance_marked = True
                messages.success(request, f"Attendance marked PRESENT for {member.full_name}!")
            else:
                messages.error(request, f"No member found with ID #{member_id}.")
        else:
            messages.error(request, "Invalid QR Code scanned.")

    today_attendances = Attendance.objects.filter(date=today).select_related('member').order_by('-updated_at')[:10]

    return render(request, "admin_qr_attendance.html", {
        "scanned_member": scanned_member,
        "attendance_marked": attendance_marked,
        "today_attendances": today_attendances,
        "today": today,
    })


# ══════════════════════════════════════════
#  EXPORT & PRINTABLE REPORTS
# ══════════════════════════════════════════

@admin_required
def export_members_csv(request):
    members = MemberProfile.objects.select_related('user', 'plan', 'trainer').all()
    headers = ['ID', 'Full Name', 'Username', 'Mobile', 'Gender', 'BMI', 'Goal', 'Plan', 'Trainer', 'Joining Date', 'Status']
    rows = []
    for m in members:
        rows.append([
            m.id, m.full_name, m.user.username, m.mobile, m.gender or '',
            m.bmi or '', m.fitness_goal, m.plan.name if m.plan else 'No Plan',
            m.trainer.name if m.trainer else 'Unassigned', m.joining_date, m.membership_status
        ])
    return export_to_csv("fitpro_members_report", headers, rows)


@admin_required
def export_payments_csv(request):
    payments = Payment.objects.select_related('member', 'plan').all()
    headers = ['Invoice No', 'Member Name', 'Plan', 'Amount', 'Discount', 'GST', 'Total Amount', 'Mode', 'Status', 'Date']
    rows = []
    for p in payments:
        rows.append([
            p.invoice_no or '', p.member.full_name, p.plan.name if p.plan else '',
            p.amount, p.discount, p.gst, p.total_amount, p.mode, p.status, p.payment_date
        ])
    return export_to_csv("fitpro_payments_report", headers, rows)


@admin_required
def export_attendance_csv(request):
    attendances = Attendance.objects.select_related('member').all()
    headers = ['Date', 'Member Name', 'Mobile', 'Time In', 'Time Out', 'Status', 'Remarks']
    rows = []
    for a in attendances:
        rows.append([
            a.date, a.member.full_name, a.member.mobile, a.time_in or '', a.time_out or '', a.status, a.remarks
        ])
    return export_to_csv("fitpro_attendance_report", headers, rows)


def member_card_printable(request, member_id):
    member = get_object_or_404(MemberProfile, id=member_id)

    # Ensure user is either admin or the member themself
    if not request.user.is_authenticated:
        return redirect("member_login")
    if request.user.role != "ADMIN" and getattr(request.user, 'member_profile', None) != member:
        messages.error(request, "Unauthorized access.")
        return redirect("member_dashboard")

    qr_code_uri = generate_qr_code_base64(f"FITPRO-MEMBER-ID:{member.id}|NAME:{member.full_name}")

    return render(request, "membership_card_printable.html", {
        "member": member,
        "qr_code_uri": qr_code_uri,
    })


def payment_invoice_printable(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if not request.user.is_authenticated:
        return redirect("member_login")
    if request.user.role != "ADMIN" and getattr(request.user, 'member_profile', None) != payment.member:
        messages.error(request, "Unauthorized access.")
        return redirect("member_dashboard")

    return render(request, "invoice_printable.html", {"payment": payment})


# ══════════════════════════════════════════
#  ANNOUNCEMENTS
# ══════════════════════════════════════════

def announcement_list(request):
    announcements = Announcement.objects.filter(is_active=True).order_by("-date")
    return render(request, "announcement_list.html", {"announcements": announcements})


@admin_required
def announcement_add(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        type_choice = request.POST.get("type", "ANNOUNCEMENT")
        content = request.POST.get("content", "").strip()
        date = request.POST.get("date") or timezone.now().date()
        image = request.FILES.get("image")

        if title and content:
            Announcement.objects.create(
                title=title, type=type_choice, content=content, date=date, image=image
            )
            messages.success(request, "Announcement created successfully!")
            return redirect("announcement_list")
    return redirect("announcement_list")


@admin_required
def announcement_delete(request, ann_id):
    ann = get_object_or_404(Announcement, id=ann_id)
    if request.method == "POST":
        ann.delete()
        messages.success(request, "Announcement deleted.")
    return redirect("announcement_list")


# ══════════════════════════════════════════
#  MEMBERSHIP PLANS (CRUD)
# ══════════════════════════════════════════

@admin_required
def admin_plans_list(request):
    search = request.GET.get('search', '')
    plans = MembershipPlan.objects.all().order_by('price')
    if search:
        plans = plans.filter(name__icontains=search)
    return render(request, 'admin_plan_list.html', {'plans': plans, 'search': search})


@admin_required
def admin_plans_add(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        tier = request.POST.get("tier", "GOLD")
        duration_months = request.POST.get("duration_months", "").strip()
        price = request.POST.get("price", "").strip()
        description = request.POST.get("description", "").strip()
        benefits = request.POST.get("benefits", "").strip()
        access_time = request.POST.get("access_time", "6:00 AM - 10:00 PM").strip()
        trainer_included = request.POST.get("trainer_included") == "on"
        diet_plan_included = request.POST.get("diet_plan_included") == "on"

        if not (name and duration_months and price):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_plans_add")

        MembershipPlan.objects.create(
            name=name, tier=tier, duration_months=duration_months,
            price=price, description=description, benefits=benefits,
            access_time=access_time, trainer_included=trainer_included,
            diet_plan_included=diet_plan_included
        )
        messages.success(request, "Membership plan added.")
        return redirect("admin_plans_list")

    return render(request, "admin_plan_form.html", {"mode": "add"})


@admin_required
def admin_plan_edit(request, plan_id):
    plan = get_object_or_404(MembershipPlan, id=plan_id)
    if request.method == 'POST':
        name = request.POST.get('name')
        tier = request.POST.get('tier', 'GOLD')
        duration_months = request.POST.get('duration_months')
        price = request.POST.get('price')
        description = request.POST.get('description')
        benefits = request.POST.get('benefits')
        access_time = request.POST.get('access_time')
        trainer_included = request.POST.get('trainer_included') == 'on'
        diet_plan_included = request.POST.get('diet_plan_included') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        if name and duration_months and price:
            plan.name = name
            plan.tier = tier
            plan.duration_months = duration_months
            plan.price = price
            plan.description = description
            plan.benefits = benefits
            plan.access_time = access_time
            plan.trainer_included = trainer_included
            plan.diet_plan_included = diet_plan_included
            plan.is_active = is_active
            plan.save()
            messages.success(request, 'Membership plan updated.')
            return redirect('admin_plans_list')

    return render(request, 'admin_plan_form.html', {'mode': 'edit', 'plan': plan})


@admin_required
def admin_plans_delete(request, plan_id):
    plan = get_object_or_404(MembershipPlan, id=plan_id)
    plan.delete()
    messages.success(request, 'Plan deleted.')
    return redirect('admin_plans_list')


# ══════════════════════════════════════════
#  TRAINERS (CRUD)
# ══════════════════════════════════════════

@admin_required
def admin_trainer_list(request):
    search = request.GET.get('search', '')
    trainers = Trainer.objects.all().order_by('name')
    if search:
        trainers = trainers.filter(name__icontains=search)
    return render(request, 'admin_trainer_list.html', {'trainers': trainers, 'search': search})


@admin_required
def admin_trainer_add(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        specialization = request.POST.get("specialization", "").strip()
        shift_timings = request.POST.get("shift_timings", "").strip()
        photo = request.FILES.get("photo")
        email = request.POST.get("email", "").strip()
        experience = request.POST.get("experience", 0)
        salary = request.POST.get("salary", 0)
        joining_date = request.POST.get("joining_date") or timezone.now().date()
        certifications = request.POST.get("certifications", "").strip()
        weekly_schedule = request.POST.get("weekly_schedule", "").strip()
        is_active = request.POST.get("is_active") == "on"
        bio = request.POST.get("bio", "").strip()

        if not (name and mobile and specialization):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_trainer_add")

        Trainer.objects.create(
            name=name, mobile=mobile, specialization=specialization,
            shift_timings=shift_timings or "06:00:00", photo=photo,
            email=email if email else None,
            experience=experience, salary=salary,
            joining_date=joining_date, certifications=certifications,
            weekly_schedule=weekly_schedule, is_active=is_active, bio=bio,
        )
        messages.success(request, "Trainer added.")
        return redirect("admin_trainer_list")

    return render(request, "admin_trainer_form.html", {"mode": "add"})


@admin_required
def admin_trainer_edit(request, trainer_id):
    trainer = get_object_or_404(Trainer, id=trainer_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        specialization = request.POST.get("specialization", "").strip()
        shift_timings = request.POST.get("shift_timings", "").strip()
        email = request.POST.get("email", "").strip()
        experience = request.POST.get("experience", 0)
        salary = request.POST.get("salary", 0)
        joining_date = request.POST.get("joining_date")
        certifications = request.POST.get("certifications", "").strip()
        weekly_schedule = request.POST.get("weekly_schedule", "").strip()
        is_active = request.POST.get("is_active") == "on"
        bio = request.POST.get("bio", "").strip()
        photo = request.FILES.get("photo")

        if not (name and mobile and specialization):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_trainer_edit", trainer_id=trainer.id)

        trainer.name = name
        trainer.mobile = mobile
        trainer.specialization = specialization
        if shift_timings:
            trainer.shift_timings = shift_timings
        trainer.email = email if email else None
        trainer.experience = experience
        trainer.salary = salary
        if joining_date:
            trainer.joining_date = joining_date
        trainer.certifications = certifications
        trainer.weekly_schedule = weekly_schedule
        trainer.is_active = is_active
        trainer.bio = bio
        if photo:
            trainer.photo = photo
        trainer.save()

        messages.success(request, "Trainer updated.")
        return redirect("admin_trainer_list")

    return render(request, "admin_trainer_form.html", {"mode": "edit", "trainer": trainer})


@admin_required
def admin_trainer_delete(request, trainer_id):
    trainer = get_object_or_404(Trainer, id=trainer_id)
    if request.method == "POST":
        trainer.delete()
        messages.success(request, "Trainer deleted.")
    return redirect("admin_trainer_list")


# ══════════════════════════════════════════
#  MEMBERS (CRUD & PROGRESS)
# ══════════════════════════════════════════

@admin_required
def admin_member_list(request):
    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    members = MemberProfile.objects.select_related("user", "plan", "trainer").all().order_by("full_name")
    if search_query:
        members = members.filter(Q(full_name__icontains=search_query) | Q(mobile__icontains=search_query))
    today = timezone.now().date()
    if status_filter == "active":
        members = members.filter(membership_end__gte=today)
    elif status_filter == "expired":
        members = members.filter(membership_end__lt=today)

    return render(request, "admin_member_list.html", {
        "members": members,
        "search_query": search_query,
        "status_filter": status_filter,
    })


@admin_required
def admin_member_add(request):
    plans = MembershipPlan.objects.all().order_by("price")
    trainers = Trainer.objects.all().order_by("name")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        full_name = request.POST.get("full_name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        date_of_birth = request.POST.get("date_of_birth")
        gender = request.POST.get("gender")
        address = request.POST.get("address", "").strip()
        joining_date = request.POST.get("joining_date") or timezone.now().date()
        plan_id = request.POST.get("plan")
        trainer_id = request.POST.get("trainer")
        height = request.POST.get("height")
        weight = request.POST.get("weight")
        fitness_goal = request.POST.get("fitness_goal", "WEIGHT_LOSS")
        blood_group = request.POST.get("blood_group", "")
        emergency_contact = request.POST.get("emergency_contact", "")
        medical_history = request.POST.get("medical_history", "")
        membership_start = request.POST.get("membership_start")
        membership_end = request.POST.get("membership_end")
        profile_photo = request.FILES.get("profile_photo")

        if not (username and password and full_name and mobile):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_member_add")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("admin_member_add")

        user = User.objects.create_user(username=username, password=password, role="MEMBER")
        plan = MembershipPlan.objects.get(id=plan_id) if plan_id else None
        trainer = Trainer.objects.get(id=trainer_id) if trainer_id else None

        member = MemberProfile.objects.create(
            user=user, full_name=full_name, mobile=mobile,
            date_of_birth=date_of_birth or None,
            gender=gender, address=address, joining_date=joining_date,
            plan=plan, trainer=trainer,
            height=height or None, weight=weight or None,
            fitness_goal=fitness_goal, blood_group=blood_group,
            emergency_contact=emergency_contact, medical_history=medical_history,
            membership_start=membership_start or None,
            membership_end=membership_end or None,
            profile_photo=profile_photo,
        )

        attach_qr_to_member(member)

        if height and weight:
            bmi_val = member.bmi or 0
            MemberProgressHistory.objects.create(
                member=member, weight=weight, height=height, bmi=bmi_val, notes="Initial Entry"
            )

        messages.success(request, "Member added successfully.")
        return redirect("admin_member_list")

    return render(request, "admin_member_form.html", {"mode": "add", "plans": plans, "trainers": trainers})


@admin_required
def admin_member_edit(request, member_id):
    member = get_object_or_404(MemberProfile, id=member_id)
    plans = MembershipPlan.objects.all().order_by("price")
    trainers = Trainer.objects.all().order_by("name")

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        date_of_birth = request.POST.get("date_of_birth")
        gender = request.POST.get("gender")
        address = request.POST.get("address", "").strip()
        joining_date = request.POST.get("joining_date") or timezone.now().date()
        plan_id = request.POST.get("plan")
        trainer_id = request.POST.get("trainer")
        height = request.POST.get("height")
        weight = request.POST.get("weight")
        fitness_goal = request.POST.get("fitness_goal", "WEIGHT_LOSS")
        blood_group = request.POST.get("blood_group", "")
        emergency_contact = request.POST.get("emergency_contact", "")
        medical_history = request.POST.get("medical_history", "")
        membership_start = request.POST.get("membership_start")
        membership_end = request.POST.get("membership_end")
        profile_photo = request.FILES.get("profile_photo")

        if not (full_name and mobile):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_member_edit", member_id=member.id)

        plan = MembershipPlan.objects.get(id=plan_id) if plan_id else None
        trainer = Trainer.objects.get(id=trainer_id) if trainer_id else None

        member.full_name = full_name
        member.mobile = mobile
        member.date_of_birth = date_of_birth or None
        member.gender = gender
        member.address = address
        member.joining_date = joining_date
        member.plan = plan
        member.trainer = trainer
        member.height = height or None
        member.weight = weight or None
        member.fitness_goal = fitness_goal
        member.blood_group = blood_group
        member.emergency_contact = emergency_contact
        member.medical_history = medical_history
        member.membership_start = membership_start or None
        member.membership_end = membership_end or None
        if profile_photo:
            member.profile_photo = profile_photo
        member.save()

        if height and weight:
            bmi_val = member.bmi or 0
            MemberProgressHistory.objects.create(
                member=member, weight=weight, height=height, bmi=bmi_val, notes="Updated Profile"
            )

        messages.success(request, "Member updated.")
        return redirect("admin_member_list")

    return render(request, "admin_member_form.html", {
        "mode": "edit", "member": member, "plans": plans, "trainers": trainers,
    })


@admin_required
def admin_member_delete(request, member_id):
    member = get_object_or_404(MemberProfile, id=member_id)
    user = member.user
    member.delete()
    user.delete()
    messages.success(request, 'Member deleted.')
    return redirect('admin_member_list')


# ══════════════════════════════════════════
#  EQUIPMENT (CRUD)
# ══════════════════════════════════════════

@admin_required
def admin_equipment_list(request):
    search = request.GET.get("search", "")
    equipments = Equipment.objects.all().order_by("name")
    if search:
        equipments = equipments.filter(Q(name__icontains=search) | Q(category__icontains=search) | Q(brand__icontains=search))
    return render(request, "admin_equipment_list.html", {"equipments": equipments, "search": search})


@admin_required
def admin_equipment_add(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "Strength").strip()
        brand = request.POST.get("brand", "").strip()
        model_number = request.POST.get("model_number", "").strip()
        units = request.POST.get("units", 1)
        price = request.POST.get("price", 0)
        purchase_date = request.POST.get("purchase_date") or timezone.now().date()
        warranty_date = request.POST.get("warranty_date") or None
        maintenance_date = request.POST.get("maintenance_date") or None
        condition = request.POST.get("condition", "EXCELLENT")
        status = request.POST.get("status", "AVAILABLE")
        location = request.POST.get("location", "Main Floor").strip()
        description = request.POST.get("description", "").strip()
        image = request.FILES.get("image")

        if not name:
            messages.error(request, "Please enter equipment name.")
            return redirect("admin_equipment_add")

        Equipment.objects.create(
            name=name, category=category, brand=brand, model_number=model_number,
            units=units, price=price, purchase_date=purchase_date,
            warranty_date=warranty_date, maintenance_date=maintenance_date,
            condition=condition, status=status, location=location,
            description=description, image=image,
        )
        messages.success(request, "Equipment added.")
        return redirect("admin_equipment_list")

    return render(request, "admin_equipment_form.html", {"mode": "add"})


@admin_required
def admin_equipment_edit(request, equipment_id):
    equipment = get_object_or_404(Equipment, id=equipment_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "Strength").strip()
        brand = request.POST.get("brand", "").strip()
        model_number = request.POST.get("model_number", "").strip()
        units = request.POST.get("units", 1)
        price = request.POST.get("price", 0)
        purchase_date = request.POST.get("purchase_date") or timezone.now().date()
        warranty_date = request.POST.get("warranty_date") or None
        maintenance_date = request.POST.get("maintenance_date") or None
        condition = request.POST.get("condition", "EXCELLENT")
        status = request.POST.get("status", "AVAILABLE")
        location = request.POST.get("location", "Main Floor").strip()
        description = request.POST.get("description", "").strip()
        image = request.FILES.get("image")

        if not name:
            messages.error(request, "Please enter equipment name.")
            return redirect("admin_equipment_edit", equipment_id=equipment.id)

        equipment.name = name
        equipment.category = category
        equipment.brand = brand
        equipment.model_number = model_number
        equipment.units = units
        equipment.price = price
        equipment.purchase_date = purchase_date
        equipment.warranty_date = warranty_date
        equipment.maintenance_date = maintenance_date
        equipment.condition = condition
        equipment.status = status
        equipment.location = location
        equipment.description = description
        if image:
            equipment.image = image
        equipment.save()

        messages.success(request, "Equipment updated.")
        return redirect("admin_equipment_list")

    return render(request, "admin_equipment_form.html", {"mode": "edit", "equipment": equipment})


@admin_required
def admin_equipment_delete(request, equipment_id):
    equipment = get_object_or_404(Equipment, id=equipment_id)
    if request.method == "POST":
        equipment.delete()
        messages.success(request, "Equipment deleted.")
    return redirect("admin_equipment_list")


# ══════════════════════════════════════════
#  ATTENDANCE & ENQUIRIES
# ══════════════════════════════════════════

@admin_required
def admin_attendence_list(request):
    today = timezone.now().date()
    date = request.GET.get("date") or today.isoformat()
    member_id = request.GET.get("member_id", "").strip()
    members = MemberProfile.objects.all().order_by("full_name")
    attendances = Attendance.objects.select_related("member").filter(date=date).order_by("-time_in")
    if member_id:
        attendances = attendances.filter(member_id=member_id)

    return render(request, "admin_attendence_list.html", {
        "attendances": attendances,
        "members": members,
        "date": date,
        "member_id": member_id,
        "today_count": Attendance.objects.filter(date=today, status="PRESENT").count(),
    })


@admin_required
def admin_attendance_add(request):
    members = MemberProfile.objects.all().order_by("full_name")
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        date = request.POST.get("date") or timezone.now().date()
        time_in = request.POST.get("time_in")
        status = request.POST.get("status", "").strip()

        if not (member_id and status):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_attendance_add")

        member = get_object_or_404(MemberProfile, id=member_id)
        attendance, created = Attendance.objects.get_or_create(
            member=member, date=date,
            defaults={"time_in": time_in or timezone.now().time(), "status": status},
        )
        if not created:
            if time_in:
                attendance.time_in = time_in
            attendance.status = status
            attendance.save()

        messages.success(request, "Attendance updated.")
        return redirect("admin_attendence_list")

    return render(request, "admin_attendance_form.html", {"members": members})


@admin_required
def admin_enquiry_list(request):
    status_filter = request.GET.get("status", "")
    enquiries = Enquiry.objects.all().order_by("-created_at")
    if status_filter:
        enquiries = enquiries.filter(status=status_filter)
    trainers = Trainer.objects.filter(is_active=True)
    return render(request, "admin_enquiry_list.html", {
        "enquiries": enquiries,
        "status_filter": status_filter,
        "trainers": trainers,
    })


@admin_required
def admin_enquiry_update_status(request, enquiry_id):
    enquiry = get_object_or_404(Enquiry, id=enquiry_id)
    if request.method == "POST":
        status = request.POST.get("status")
        reply = request.POST.get("reply", "").strip()
        follow_up_date = request.POST.get("follow_up_date") or None
        trainer_id = request.POST.get("assigned_trainer") or None

        if status in ["NEW", "SEEN", "IN_PROGRESS", "RESOLVED", "REJECTED"]:
            enquiry.status = status
            enquiry.reply = reply
            enquiry.follow_up_date = follow_up_date
            if trainer_id:
                enquiry.assigned_trainer = get_object_or_404(Trainer, id=trainer_id)
            else:
                enquiry.assigned_trainer = None
            enquiry.save()

            if reply:
                send_system_email(
                    f"Response to your enquiry: {enquiry.subject or 'Gym Enquiry'}",
                    f"Hello {enquiry.name},\n\nAdmin reply:\n{reply}\n\nThank you,\nFitPro GYM Team",
                    enquiry.email
                )
            messages.success(request, "Enquiry updated.")

    return redirect("admin_enquiry_list")


# ══════════════════════════════════════════
#  WORKOUT & DIET PLANS (Admin)
# ══════════════════════════════════════════

@admin_required
def admin_workout_plan_list(request):
    member_id = request.GET.get("member_id", "").strip()
    members = MemberProfile.objects.all().order_by("full_name")
    workout_plans = WorkoutPlan.objects.select_related("member").all().order_by("-created_at")
    if member_id:
        workout_plans = workout_plans.filter(member_id=member_id)
    return render(request, "admin_workout_plan_list.html", {
        "workout_plans": workout_plans,
        "members": members,
        "selected_member_id": member_id,
    })


@admin_required
def admin_workout_plan_add(request):
    members = MemberProfile.objects.all().order_by("full_name")
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        day = request.POST.get("day", "").strip()
        exercise_name = request.POST.get("exercise_name", "").strip()
        sets = request.POST.get("sets", 3)
        reps = request.POST.get("reps", 10)
        weight = request.POST.get("weight", 0)
        rest_seconds = request.POST.get("rest_seconds", 60)
        difficulty = request.POST.get("difficulty", "BEGINNER")
        duration_minutes = request.POST.get("duration_minutes", 30)
        calories_burned = request.POST.get("calories_burned", 0)
        equipment_required = request.POST.get("equipment_required", "Dumbbells").strip()
        video_url = request.POST.get("video_url", "").strip()
        exercise_image = request.FILES.get("exercise_image")

        if not (member_id and title and day and exercise_name):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_workout_plan_add")

        member = get_object_or_404(MemberProfile, id=member_id)
        WorkoutPlan.objects.create(
            member=member, title=title, description=description,
            day=day, exercise_name=exercise_name,
            sets=sets, reps=reps, weight=weight, rest_seconds=rest_seconds,
            difficulty=difficulty, duration_minutes=duration_minutes,
            calories_burned=calories_burned, equipment_required=equipment_required,
            video_url=video_url, exercise_image=exercise_image,
        )
        messages.success(request, "Workout plan added.")
        return redirect("admin_workout_plan_list")

    return render(request, "admin_workout_plan_form.html", {"members": members, "mode": "add"})


@admin_required
def admin_workout_plan_edit(request, plan_id):
    workout_plan = get_object_or_404(WorkoutPlan, id=plan_id)
    members = MemberProfile.objects.all().order_by("full_name")
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        day = request.POST.get("day", "").strip()
        exercise_name = request.POST.get("exercise_name", "").strip()
        sets = request.POST.get("sets", 3)
        reps = request.POST.get("reps", 10)
        weight = request.POST.get("weight", 0)
        rest_seconds = request.POST.get("rest_seconds", 60)
        difficulty = request.POST.get("difficulty", "BEGINNER")
        duration_minutes = request.POST.get("duration_minutes", 30)
        calories_burned = request.POST.get("calories_burned", 0)
        equipment_required = request.POST.get("equipment_required", "").strip()
        video_url = request.POST.get("video_url", "").strip()
        exercise_image = request.FILES.get("exercise_image")

        if not (member_id and title and day and exercise_name):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_workout_plan_edit", plan_id=workout_plan.id)

        workout_plan.member = get_object_or_404(MemberProfile, id=member_id)
        workout_plan.title = title
        workout_plan.description = description
        workout_plan.day = day
        workout_plan.exercise_name = exercise_name
        workout_plan.sets = sets
        workout_plan.reps = reps
        workout_plan.weight = weight
        workout_plan.rest_seconds = rest_seconds
        workout_plan.difficulty = difficulty
        workout_plan.duration_minutes = duration_minutes
        workout_plan.calories_burned = calories_burned
        workout_plan.equipment_required = equipment_required
        workout_plan.video_url = video_url
        if exercise_image:
            workout_plan.exercise_image = exercise_image
        workout_plan.save()

        messages.success(request, "Workout plan updated.")
        return redirect("admin_workout_plan_list")

    return render(request, "admin_workout_plan_form.html", {
        "mode": "edit", "workout_plan": workout_plan, "members": members,
    })


@admin_required
def admin_workout_plan_delete(request, plan_id):
    workout_plan = get_object_or_404(WorkoutPlan, id=plan_id)
    if request.method == "POST":
        workout_plan.delete()
        messages.success(request, "Workout plan deleted.")
    return redirect("admin_workout_plan_list")


@admin_required
def admin_diet_plan_list(request):
    member_id = request.GET.get("member_id", "").strip()
    members = MemberProfile.objects.all().order_by("full_name")
    diet_plans = DietPlan.objects.select_related("member").all().order_by("-created_at")
    if member_id:
        diet_plans = diet_plans.filter(member_id=member_id)
    return render(request, "admin_diet_plan_list.html", {
        "diet_plans": diet_plans,
        "members": members,
        "selected_member_id": member_id,
    })


@admin_required
def admin_diet_plan_add(request):
    members = MemberProfile.objects.all().order_by("full_name")
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        breakfast = request.POST.get("breakfast", "").strip()
        lunch = request.POST.get("lunch", "").strip()
        dinner = request.POST.get("dinner", "").strip()
        snacks = request.POST.get("snacks", "").strip()
        water_intake = request.POST.get("water_intake", 3)
        calories = request.POST.get("calories", 2000)
        protein_goal = request.POST.get("protein_goal", 0)
        notes = request.POST.get("notes", "").strip()

        if not (member_id and breakfast and lunch and dinner):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_diet_plan_add")

        member = get_object_or_404(MemberProfile, id=member_id)
        DietPlan.objects.create(
            member=member, breakfast=breakfast, lunch=lunch, dinner=dinner,
            snacks=snacks, water_intake=water_intake, calories=calories,
            protein_goal=protein_goal, notes=notes,
        )
        messages.success(request, "Diet plan added.")
        return redirect("admin_diet_plan_list")

    return render(request, "admin_diet_plan_form.html", {"members": members, "mode": "add"})


@admin_required
def admin_diet_plan_edit(request, plan_id):
    diet_plan = get_object_or_404(DietPlan, id=plan_id)
    members = MemberProfile.objects.all().order_by("full_name")
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        breakfast = request.POST.get("breakfast", "").strip()
        lunch = request.POST.get("lunch", "").strip()
        dinner = request.POST.get("dinner", "").strip()
        snacks = request.POST.get("snacks", "").strip()
        water_intake = request.POST.get("water_intake", 3)
        calories = request.POST.get("calories", 2000)
        protein_goal = request.POST.get("protein_goal", 0)
        notes = request.POST.get("notes", "").strip()

        if not (member_id and breakfast and lunch and dinner):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_diet_plan_edit", plan_id=diet_plan.id)

        diet_plan.member = get_object_or_404(MemberProfile, id=member_id)
        diet_plan.breakfast = breakfast
        diet_plan.lunch = lunch
        diet_plan.dinner = dinner
        diet_plan.snacks = snacks
        diet_plan.water_intake = water_intake
        diet_plan.calories = calories
        diet_plan.protein_goal = protein_goal
        diet_plan.notes = notes
        diet_plan.save()

        messages.success(request, "Diet plan updated.")
        return redirect("admin_diet_plan_list")

    return render(request, "admin_diet_plan_form.html", {
        "mode": "edit", "diet_plan": diet_plan, "members": members,
    })


@admin_required
def admin_diet_plan_delete(request, plan_id):
    diet_plan = get_object_or_404(DietPlan, id=plan_id)
    if request.method == "POST":
        diet_plan.delete()
        messages.success(request, "Diet plan deleted.")
    return redirect("admin_diet_plan_list")


# ══════════════════════════════════════════
#  PAYMENTS (CRUD)
# ══════════════════════════════════════════

@admin_required
def admin_payment_list(request):
    member_id = request.GET.get("member_id", "").strip()
    status_filter = request.GET.get("status", "")
    members = MemberProfile.objects.all().order_by("full_name")
    payments = Payment.objects.select_related("member", "plan").all().order_by("-payment_date")
    if member_id:
        payments = payments.filter(member_id=member_id)
    if status_filter:
        payments = payments.filter(status=status_filter)

    total_revenue = payments.filter(status="PAID").aggregate(total=Sum('amount'))['total'] or 0

    return render(request, "admin_payment_list.html", {
        "payments": payments,
        "members": members,
        "selected_member_id": member_id,
        "status_filter": status_filter,
        "total_revenue": total_revenue,
    })


@admin_required
def admin_payment_add(request):
    members = MemberProfile.objects.all().order_by("full_name")
    plans = MembershipPlan.objects.all().order_by("name")
    if request.method == "POST":
        member_id = request.POST.get("member")
        plan_id = request.POST.get("plan")
        amount = request.POST.get("amount")
        discount = request.POST.get("discount") or 0
        gst = request.POST.get("gst") or 0
        payment_date = request.POST.get("payment_date") or timezone.now().date()
        mode = request.POST.get("mode")
        status = request.POST.get("status")
        transaction_id = request.POST.get("transaction_id", "")
        notes = request.POST.get("notes", "")
        payment_proof = request.FILES.get("payment_proof")

        if not (member_id and amount and mode and status):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_payment_add")

        member = get_object_or_404(MemberProfile, id=member_id)
        plan = get_object_or_404(MembershipPlan, id=plan_id) if plan_id else None

        payment = Payment.objects.create(
            member=member, plan=plan, amount=amount,
            discount=discount, gst=gst, payment_date=payment_date,
            mode=mode, status=status, transaction_id=transaction_id, notes=notes,
            payment_proof=payment_proof,
        )
        messages.success(request, f"Payment added! Invoice #{payment.invoice_no}")
        return redirect("admin_payment_list")

    return render(request, "admin_payment_form.html", {"mode": "add", "members": members, "plans": plans})


@admin_required
def admin_payment_edit(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    members = MemberProfile.objects.all().order_by("full_name")
    plans = MembershipPlan.objects.all().order_by("name")
    if request.method == "POST":
        member_id = request.POST.get("member")
        amount = request.POST.get("amount")
        payment_date = request.POST.get("payment_date")
        mode = request.POST.get("mode", "").strip()
        status = request.POST.get("status", "").strip()
        discount = request.POST.get("discount") or 0
        gst = request.POST.get("gst") or 0
        notes = request.POST.get("notes", "").strip()
        payment_proof = request.FILES.get("payment_proof")

        if not (member_id and amount and mode and status):
            messages.error(request, "Please fill required fields.")
            return redirect("admin_payment_edit", payment_id=payment.id)

        payment.member = get_object_or_404(MemberProfile, id=member_id)
        payment.amount = amount
        payment.payment_date = payment_date
        payment.mode = mode
        payment.status = status
        payment.discount = discount
        payment.gst = gst
        payment.notes = notes
        if payment_proof:
            payment.payment_proof = payment_proof
        payment.save()

        messages.success(request, "Payment updated.")
        return redirect("admin_payment_list")

    return render(request, "admin_payment_form.html", {
        "mode": "edit", "payment": payment, "members": members, "plans": plans,
    })


@admin_required
def admin_payment_delete(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if request.method == "POST":
        payment.delete()
        messages.success(request, "Payment deleted.")
    return redirect("admin_payment_list")


@admin_required
def admin_notifications(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        message = request.POST.get("message", "").strip()
        notif_type = request.POST.get("notif_type", "GENERAL")
        member_id = request.POST.get("member_id") or None

        if not (title and message):
            messages.error(request, "Please fill title and message.")
            return redirect("admin_notifications")

        member = get_object_or_404(MemberProfile, id=member_id) if member_id else None
        Notification.objects.create(
            member=member, title=title, message=message, notif_type=notif_type,
        )

        if member and member.user.email:
            send_system_email(title, message, member.user.email)

        messages.success(request, "Notification sent.")
        return redirect("admin_notifications")

    notifications = Notification.objects.all().order_by("-created_at")
    members = MemberProfile.objects.all().order_by("full_name")
    return render(request, "admin_notification.html", {
        "notifications": notifications,
        "members": members,
    })


# ══════════════════════════════════════════
#  MEMBER AREA & AI RECOMMENDATIONS
# ══════════════════════════════════════════

@member_required
def member_dashboard(request):
    member = get_object_or_404(MemberProfile, user=request.user)
    today = timezone.now().date()

    trainers = Trainer.objects.filter(is_active=True).order_by("name")
    attendance_count = Attendance.objects.filter(member=member).count()
    payment_count = Payment.objects.filter(member=member).count()
    latest_diet = DietPlan.objects.filter(member=member).order_by('-created_at').first()
    today_workouts = WorkoutPlan.objects.filter(
        member=member,
        day=today.strftime("%A").upper()
    )
    recent_payments = Payment.objects.filter(member=member).order_by('-payment_date')[:3]
    announcements = Announcement.objects.filter(is_active=True)[:3]
    all_notifications = Notification.objects.filter(Q(member=member) | Q(member__isnull=True)).order_by('-created_at')[:5]

    import calendar
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    month_attendance = Attendance.objects.filter(
        member=member,
        date__year=today.year,
        date__month=today.month,
        status="PRESENT"
    ).count()
    attendance_pct = round((month_attendance / days_in_month) * 100) if days_in_month else 0

    # Ensure member has QR code base64
    qr_code_uri = generate_qr_code_base64(f"FITPRO-MEMBER-ID:{member.id}|NAME:{member.full_name}")

    return render(request, "member_dashboard.html", {
        "member": member,
        "attendance_count": attendance_count,
        "payment_count": payment_count,
        "trainers": trainers,
        "latest_diet": latest_diet,
        "today_workouts": today_workouts,
        "recent_payments": recent_payments,
        "announcements": announcements,
        "all_notifications": all_notifications,
        "attendance_pct": attendance_pct,
        "qr_code_uri": qr_code_uri,
        "today": today,
    })


@member_required
def member_ai_recommendations(request):
    """
    Member AI Advisor Page: Auto-calculates BMR, TDEE, AI Diet & Workout schedules.
    """
    member = get_object_or_404(MemberProfile, user=request.user)

    if request.method == "POST":
        height = request.POST.get("height")
        weight = request.POST.get("weight")
        fitness_goal = request.POST.get("fitness_goal")

        if height and weight:
            member.height = height
            member.weight = weight
            if fitness_goal:
                member.fitness_goal = fitness_goal
            member.save()

            MemberProgressHistory.objects.create(
                member=member, weight=weight, height=height, bmi=member.bmi or 0, notes="User Progress Log"
            )
            messages.success(request, "Metrics updated! Recalculating AI targets...")

    ai_diet = AIEngine.generate_ai_diet_recommendation(member)
    ai_workout = AIEngine.generate_ai_workout_recommendation(member)
    progress_logs = MemberProgressHistory.objects.filter(member=member).order_by("date")

    progress_labels = [p.date.strftime("%b %d") for p in progress_logs]
    progress_weights = [float(p.weight) for p in progress_logs]

    return render(request, "member_ai_recommendations.html", {
        "member": member,
        "ai_diet": ai_diet,
        "ai_workout": ai_workout,
        "progress_logs": progress_logs,
        "progress_labels": json.dumps(progress_labels),
        "progress_weights": json.dumps(progress_weights),
    })


@member_required
def member_my_workout(request):
    member = get_object_or_404(MemberProfile, user=request.user)
    day_filter = request.GET.get("day", "")
    workouts = WorkoutPlan.objects.filter(member=member)
    if day_filter:
        workouts = workouts.filter(day=day_filter)
    workouts = workouts.order_by("day", "exercise_name")

    days_order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    grouped = {}
    for day in days_order:
        day_workouts = workouts.filter(day=day)
        if day_workouts.exists():
            grouped[day] = day_workouts

    return render(request, "member_workout.html", {
        "member": member,
        "grouped_workouts": grouped,
        "day_filter": day_filter,
        "days": days_order,
    })


@member_required
def member_my_diet(request):
    member = get_object_or_404(MemberProfile, user=request.user)
    diet_plans = DietPlan.objects.filter(member=member).order_by("-created_at")
    latest_diet = diet_plans.first()
    return render(request, "member_diet.html", {
        "member": member,
        "diet_plans": diet_plans,
        "latest_diet": latest_diet,
    })


@member_required
def member_my_attendance(request):
    member = get_object_or_404(MemberProfile, user=request.user)
    month = request.GET.get("month", timezone.now().date().month)
    year = request.GET.get("year", timezone.now().date().year)
    attendances = Attendance.objects.filter(
        member=member, date__month=month, date__year=year
    ).order_by("-date")
    present_count = attendances.filter(status="PRESENT").count()
    total_count = attendances.count()
    pct = round((present_count / total_count) * 100) if total_count else 0

    return render(request, "member_attendance.html", {
        "member": member,
        "attendances": attendances,
        "present_count": present_count,
        "total_count": total_count,
        "attendance_pct": pct,
        "month": int(month),
        "year": int(year),
    })


@member_required
def member_my_payments(request):
    member = get_object_or_404(MemberProfile, user=request.user)
    payments = Payment.objects.filter(member=member).order_by("-payment_date")
    total_paid = payments.filter(status="PAID").aggregate(total=Sum('amount'))['total'] or 0
    pending_dues = payments.filter(status="PENDING").aggregate(total=Sum('amount'))['total'] or 0

    return render(request, "member_payments.html", {
        "member": member,
        "payments": payments,
        "total_paid": total_paid,
        "pending_dues": pending_dues,
    })