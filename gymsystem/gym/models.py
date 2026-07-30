from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import random


class User(AbstractUser):
    ROLE_CHOICE = [
        ('ADMIN', 'Admin'),
        ('MEMBER', 'Member'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICE, default='MEMBER')
    is_email_verified = models.BooleanField(default=False)
    profile_completed = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_locked(self):
        if self.account_locked_until and timezone.now() < self.account_locked_until:
            return True
        return False

    def __str__(self):
        return f"{self.username} ({self.role})"


class MembershipPlan(models.Model):
    PLAN_TIER_CHOICES = (
        ("SILVER", "Silver"),
        ("GOLD", "Gold"),
        ("PLATINUM", "Platinum"),
        ("PREMIUM", "Premium"),
    )

    name = models.CharField(max_length=100, unique=True)
    tier = models.CharField(max_length=20, choices=PLAN_TIER_CHOICES, default="GOLD")
    duration_months = models.PositiveIntegerField(
        help_text="Membership duration in months (e.g. 1, 3, 6, 12)"
    )
    price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    benefits = models.TextField(blank=True, help_text="Commas or line-separated benefits list")
    access_time = models.CharField(max_length=100, default="6:00 AM - 10:00 PM")
    trainer_included = models.BooleanField(default=False)
    diet_plan_included = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]
        verbose_name = "Membership Plan"
        verbose_name_plural = "Membership Plans"

    def get_benefits_list(self):
        if self.benefits:
            return [b.strip() for b in self.benefits.replace('\r', '').split('\n') if b.strip()]
        return []

    def __str__(self):
        return f"{self.name} ({self.tier}) - {self.duration_months} Month(s)"


class Trainer(models.Model):
    name = models.CharField(max_length=100)
    mobile = models.CharField(max_length=15, unique=True)
    specialization = models.CharField(max_length=200)
    shift_timings = models.TimeField()
    photo = models.ImageField(upload_to="trainers/", blank=True, null=True)
    email = models.EmailField(blank=True, null=True, unique=True)
    experience = models.PositiveIntegerField(default=0, help_text="Experience in years")
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    joining_date = models.DateField(default=timezone.now)
    certifications = models.TextField(blank=True, help_text="Certified Personal Trainer, Crossfit, etc.")
    weekly_schedule = models.TextField(blank=True, help_text="Mon-Fri 6am-2pm, Sat 8am-12pm")
    is_active = models.BooleanField(default=True)
    bio = models.TextField(blank=True, help_text="Short trainer bio")

    class Meta:
        ordering = ["name"]
        verbose_name = "Trainer"
        verbose_name_plural = "Trainers"

    def __str__(self):
        return f"{self.name} ({self.specialization})"

    @property
    def assigned_members_count(self):
        return self.members.count()


class MemberProfile(models.Model):
    GENDER_CHOICES = (
        ("MALE", "Male"),
        ("FEMALE", "Female"),
        ("OTHER", "Other"),
    )

    GOAL_CHOICES = (
        ("WEIGHT_LOSS", "Weight Loss"),
        ("MUSCLE_GAIN", "Muscle Gain"),
        ("MAINTENANCE", "Fitness & Maintenance"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
    )
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    full_name = models.CharField(max_length=100)
    mobile = models.CharField(max_length=15, unique=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    height = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text="Height in cm")
    weight = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text="Weight in kg")
    fitness_goal = models.CharField(max_length=20, choices=GOAL_CHOICES, default="WEIGHT_LOSS")
    blood_group = models.CharField(max_length=10, blank=True)
    emergency_contact = models.CharField(max_length=15, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    medical_history = models.TextField(blank=True)
    address = models.TextField(blank=True)
    joining_date = models.DateField(default=timezone.now)
    qr_code = models.ImageField(upload_to="qr_codes/", blank=True, null=True)
    trainer = models.ForeignKey(Trainer, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    membership_start = models.DateField(blank=True, null=True)
    membership_end = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Member Profile"
        verbose_name_plural = "Member Profiles"

    def __str__(self):
        return f"{self.full_name} ({self.user.username})"

    @property
    def current_age(self):
        if self.date_of_birth:
            today = timezone.now().date()
            age = today.year - self.date_of_birth.year
            if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
                age -= 1
            return age
        return 25

    @property
    def bmi(self):
        if self.height and self.weight:
            height_in_meter = float(self.height) / 100
            return round(float(self.weight) / (height_in_meter ** 2), 2)
        return None

    @property
    def bmi_category(self):
        bmi = self.bmi
        if bmi is None:
            return "N/A"
        if bmi < 18.5:
            return "Underweight"
        elif bmi < 25:
            return "Normal"
        elif bmi < 30:
            return "Overweight"
        else:
            return "Obese"

    @property
    def membership_status(self):
        if self.membership_end:
            return "Active" if self.membership_end >= timezone.now().date() else "Expired"
        return "No Plan"

    @property
    def days_until_expiry(self):
        if self.membership_end:
            delta = self.membership_end - timezone.now().date()
            return delta.days
        return None

    @property
    def attendance_this_month(self):
        today = timezone.now().date()
        return self.attendance.filter(
            date__year=today.year,
            date__month=today.month,
            status="PRESENT"
        ).count()


class MemberProgressHistory(models.Model):
    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="progress_history")
    date = models.DateField(default=timezone.now)
    weight = models.DecimalField(max_digits=5, decimal_places=2, help_text="Weight in kg")
    height = models.DecimalField(max_digits=5, decimal_places=2, help_text="Height in cm")
    bmi = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "Member Progress History"
        verbose_name_plural = "Member Progress Histories"

    def __str__(self):
        return f"{self.member.full_name} - {self.date} ({self.weight}kg)"


class Equipment(models.Model):
    CONDITION_CHOICES = (
        ("EXCELLENT", "Excellent"),
        ("GOOD", "Good"),
        ("FAIR", "Fair"),
        ("DAMAGED", "Damaged"),
    )

    STATUS_CHOICES = (
        ("AVAILABLE", "Available"),
        ("MAINTENANCE", "Under Maintenance"),
        ("RETIRED", "Retired"),
    )

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, default="Strength", help_text="Cardio, Strength, Accessories, etc.")
    brand = models.CharField(max_length=100, blank=True, help_text="e.g. Life Fitness, Rogue")
    model_number = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to="equipment/", blank=True, null=True)
    units = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purchase_date = models.DateField(default=timezone.now)
    warranty_date = models.DateField(null=True, blank=True)
    maintenance_date = models.DateField(null=True, blank=True, help_text="Next scheduled maintenance")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default="GOOD")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="AVAILABLE")
    location = models.CharField(max_length=100, blank=True, default="Main Gym Floor")
    supplier = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Equipment"
        verbose_name_plural = "Equipment"

    def __str__(self):
        return f"{self.name} ({self.units} Units)"


class Payment(models.Model):
    PAYMENT_MODE_CHOICES = (
        ("CASH", "Cash"),
        ("ONLINE", "Online"),
        ("CARD", "Card"),
        ("UPI", "UPI"),
    )

    PAYMENT_STATUS_CHOICES = (
        ("PAID", "Paid"),
        ("PENDING", "Pending"),
        ("FAILED", "Failed"),
        ("REFUNDED", "Refunded"),
    )

    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_date = models.DateField(default=timezone.now)
    mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING")
    invoice_no = models.CharField(max_length=30, unique=True, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_proof = models.ImageField(upload_to="payment_proofs/", blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-payment_date"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    @property
    def total_amount(self):
        return (self.amount + self.gst) - self.discount

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            self.invoice_no = f"INV-{timezone.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.member.full_name} - ₹{self.amount} ({self.status})"


class Attendance(models.Model):
    STATUS_CHOICES = (
        ("PRESENT", "Present"),
        ("ABSENT", "Absent"),
        ("LATE", "Late"),
        ("LEAVE", "Leave"),
    )

    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(default=timezone.now)
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PRESENT")
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("member", "date")
        ordering = ["-date", "member__full_name"]
        verbose_name = "Attendance"
        verbose_name_plural = "Attendance"

    def __str__(self):
        return f"{self.member.full_name} - {self.date} ({self.status})"


class Enquiry(models.Model):
    ENQUIRY_STATUS_CHOICES = (
        ("NEW", "New"),
        ("SEEN", "Seen"),
        ("IN_PROGRESS", "In Progress"),
        ("RESOLVED", "Resolved"),
        ("REJECTED", "Rejected"),
    )

    name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.CharField(max_length=15)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=ENQUIRY_STATUS_CHOICES, default="NEW")
    reply = models.TextField(blank=True, help_text="Admin reply to enquiry")
    follow_up_date = models.DateField(null=True, blank=True)
    assigned_trainer = models.ForeignKey(
        Trainer, on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Enquiry"
        verbose_name_plural = "Enquiries"

    def __str__(self):
        return f"{self.name} ({self.status})"


class WorkoutPlan(models.Model):
    DAY_CHOICES = (
        ("MONDAY", "Monday"),
        ("TUESDAY", "Tuesday"),
        ("WEDNESDAY", "Wednesday"),
        ("THURSDAY", "Thursday"),
        ("FRIDAY", "Friday"),
        ("SATURDAY", "Saturday"),
        ("SUNDAY", "Sunday"),
    )

    DIFFICULTY_CHOICES = (
        ("BEGINNER", "Beginner"),
        ("INTERMEDIATE", "Intermediate"),
        ("ADVANCED", "Advanced"),
    )

    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="workout_plans")
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    day = models.CharField(max_length=20, choices=DAY_CHOICES)
    exercise_name = models.CharField(max_length=100)
    sets = models.PositiveIntegerField(default=3)
    reps = models.PositiveIntegerField(default=10)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    rest_seconds = models.PositiveIntegerField(default=60)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="BEGINNER")
    duration_minutes = models.PositiveIntegerField(default=30, help_text="Duration in minutes")
    calories_burned = models.PositiveIntegerField(default=0, help_text="Estimated calories burned")
    equipment_required = models.CharField(max_length=100, blank=True, default="Dumbbells / Barbell")
    exercise_image = models.ImageField(upload_to="workout_exercises/", blank=True, null=True)
    video_url = models.URLField(blank=True, help_text="YouTube or Vimeo demonstration video link")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["member", "day", "exercise_name"]
        verbose_name = "Workout Plan"
        verbose_name_plural = "Workout Plans"

    def __str__(self):
        return f"{self.member.full_name} - {self.exercise_name} ({self.day})"


class DietPlan(models.Model):
    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="diet_plans")
    breakfast = models.TextField()
    lunch = models.TextField()
    dinner = models.TextField()
    snacks = models.TextField(blank=True)
    water_intake = models.PositiveIntegerField(default=3, help_text="Water intake in liters per day")
    calories = models.PositiveIntegerField()
    protein_goal = models.PositiveIntegerField(default=0, help_text="Daily protein goal in grams")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Diet Plan"
        verbose_name_plural = "Diet Plans"

    def __str__(self):
        return f"{self.member.full_name} - {self.calories} Calories"


class Announcement(models.Model):
    TYPE_CHOICES = (
        ("ANNOUNCEMENT", "General Announcement"),
        ("OFFER", "Special Offer"),
        ("HOLIDAY", "Gym Holiday"),
        ("EVENT", "Special Event"),
    )

    title = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="ANNOUNCEMENT")
    content = models.TextField()
    image = models.ImageField(upload_to="announcements/", blank=True, null=True)
    date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self):
        return f"[{self.type}] {self.title}"


class GalleryItem(models.Model):
    CATEGORY_CHOICES = (
        ("GYM_PHOTO", "Gym Infrastructure"),
        ("EVENT", "Gym Event"),
        ("TRANSFORMATION", "Member Transformation"),
        ("VIDEO", "Video Highlight"),
    )

    title = models.CharField(max_length=150)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="GYM_PHOTO")
    image = models.ImageField(upload_to="gallery/", blank=True, null=True)
    video_url = models.URLField(blank=True, help_text="Video link if category is Video")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Gallery Item"
        verbose_name_plural = "Gallery Items"

    def __str__(self):
        return f"{self.title} ({self.category})"


class Feedback(models.Model):
    RATING_CHOICES = (
        (1, "⭐"),
        (2, "⭐⭐"),
        (3, "⭐⭐⭐"),
        (4, "⭐⭐⭐⭐"),
        (5, "⭐⭐⭐⭐⭐"),
    )

    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="feedbacks")
    message = models.TextField()
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, default=5)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback"

    def __str__(self):
        return f"{self.member.full_name} - {self.rating}/5"


class Notification(models.Model):
    NOTIF_TYPE_CHOICES = (
        ("EXPIRY", "Membership Expiry"),
        ("BIRTHDAY", "Birthday Wish"),
        ("PAYMENT", "Payment Due"),
        ("ANNOUNCEMENT", "Announcement"),
        ("GENERAL", "General"),
    )

    member = models.ForeignKey(
        MemberProfile, on_delete=models.CASCADE, related_name="notifications",
        null=True, blank=True, help_text="Leave blank to send to all members"
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notif_type = models.CharField(max_length=20, choices=NOTIF_TYPE_CHOICES, default="GENERAL")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        target = self.member.full_name if self.member else "All Members"
        return f"{self.notif_type} → {target}: {self.title}"


def otp_expiry():
    return timezone.now() + timedelta(minutes=10)


class OTP(models.Model):
    PURPOSE_CHOICES = (
        ("REGISTER", "Registration Verification"),
        ("FORGOT_PASSWORD", "Password Reset"),
        ("ADMIN_LOGIN", "Admin Login Verification"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default="REGISTER")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=otp_expiry)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.username} - {self.otp} ({self.purpose})"


class LoginVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_verifications")
    photo = models.ImageField(upload_to="live_verifications/")
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Login Verification"
        verbose_name_plural = "Login Verifications"

    def __str__(self):
        return f"{self.user.username} - {self.timestamp}"
