import math
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count, Q
from .models import MemberProfile, Attendance, Payment, Trainer, WorkoutPlan, DietPlan


class AIEngine:

    @staticmethod
    def calculate_bmr_tdee(weight_kg, height_cm, age, gender="MALE", activity_level="MODERATE"):
        """
        Calculates Basal Metabolic Rate (BMR) using Mifflin-St Jeor Equation
        and Total Daily Energy Expenditure (TDEE).
        """
        if not weight_kg or not height_cm or not age:
            return {"bmr": 2000, "tdee": 2400, "water_liters": 3}

        weight = float(weight_kg)
        height = float(height_cm)
        age_years = float(age)

        # BMR Formula: (10 x weight) + (6.25 x height) - (5 x age) + s (s=+5 for men, -161 for women)
        s = 5 if str(gender).upper() == "MALE" else -161
        bmr = round((10 * weight) + (6.25 * height) - (5 * age_years) + s, 1)

        activity_multipliers = {
            "SEDENTARY": 1.2,
            "LIGHT": 1.375,
            "MODERATE": 1.55,
            "ACTIVE": 1.725,
            "VERY_ACTIVE": 1.9,
        }
        multiplier = activity_multipliers.get(activity_level.upper(), 1.55)
        tdee = round(bmr * multiplier, 1)

        # Recommended daily water intake in Liters: ~35ml per kg weight
        water_liters = round((weight * 35) / 1000, 1)

        return {
            "bmr": bmr,
            "tdee": tdee,
            "water_liters": water_liters,
        }

    @staticmethod
    def generate_ai_diet_recommendation(member):
        """
        Generates AI-suggested Calorie & Macro distribution based on fitness_goal.
        """
        age = member.current_age or 25
        weight = float(member.weight) if member.weight else 70.0
        height = float(member.height) if member.height else 170.0
        gender = member.gender or "MALE"
        goal = member.fitness_goal or "WEIGHT_LOSS"

        metrics = AIEngine.calculate_bmr_tdee(weight, height, age, gender)
        base_tdee = metrics["tdee"]

        if goal == "WEIGHT_LOSS":
            target_calories = round(base_tdee - 500)
            protein_g = round(weight * 2.2)  # 2.2g per kg
            fats_g = round((target_calories * 0.25) / 9)
            carbs_g = round((target_calories - (protein_g * 4 + fats_g * 9)) / 4)
            recommendation_note = "Caloric deficit of 500 kcal for 0.5kg/week healthy weight loss. High protein to preserve muscle."
            sample_breakfast = "3 Egg whites + 1 whole egg omelette with spinach & 2 slices whole wheat toast + Green Tea"
            sample_lunch = "150g Grilled chicken breast / Paneer tikka + 1 cup brown rice + Mixed green salad"
            sample_dinner = "150g Fish / Tofu + Steamed broccoli, carrots & zucchini + 1 chapati"
            sample_snacks = "1 scoop Whey protein / Handful of roasted almonds & walnuts"
        elif goal == "MUSCLE_GAIN":
            target_calories = round(base_tdee + 350)
            protein_g = round(weight * 2.4)
            fats_g = round((target_calories * 0.25) / 9)
            carbs_g = round((target_calories - (protein_g * 4 + fats_g * 9)) / 4)
            recommendation_note = "Clean caloric surplus of 350 kcal for lean muscle hypertrophy with adequate carbs for workout energy."
            sample_breakfast = "Oatmeal (80g) with peanut butter, banana, chia seeds & 4 egg whites / scoop protein powder"
            sample_lunch = "200g Chicken breast / Cottage cheese + 1.5 cups rice + Dal / Beans + Curd"
            sample_dinner = "200g Fish / Soya chunks curry + 2 Chapatis + Mixed salad & Avocado"
            sample_snacks = "Banana shake with peanut butter + 1 boiled egg or roasted chana"
        else:  # MAINTENANCE
            target_calories = round(base_tdee)
            protein_g = round(weight * 1.8)
            fats_g = round((target_calories * 0.30) / 9)
            carbs_g = round((target_calories - (protein_g * 4 + fats_g * 9)) / 4)
            recommendation_note = "Isocaloric balanced nutrition to maintain current body weight and optimize athletic performance."
            sample_breakfast = "Multigrain paratha / Poha with sprouts & curd + 1 fruit"
            sample_lunch = "Balanced thali: 2 Roti, 1 bowl Rice, Dal, Sabzi & Salad"
            sample_dinner = "Paneer / Lean meat cooked in olive oil + Sauteed veggies + 1 Roti"
            sample_snacks = "Fruit bowl + Greek yogurt / Green tea"

        return {
            "bmr": metrics["bmr"],
            "tdee": metrics["tdee"],
            "target_calories": max(1200, target_calories),
            "protein_g": max(50, protein_g),
            "carbs_g": max(50, carbs_g),
            "fats_g": max(30, fats_g),
            "water_liters": metrics["water_liters"],
            "recommendation_note": recommendation_note,
            "sample_breakfast": sample_breakfast,
            "sample_lunch": sample_lunch,
            "sample_dinner": sample_dinner,
            "sample_snacks": sample_snacks,
        }

    @staticmethod
    def generate_ai_workout_recommendation(member):
        """
        Generates AI-tailored workout schedule based on member's goal & BMI.
        """
        goal = member.fitness_goal or "WEIGHT_LOSS"
        bmi = member.bmi or 24.0

        if goal == "WEIGHT_LOSS":
            cardio_focus = "High Intensity Interval Training (HIIT) + Moderate Strength"
            split_name = "Fat Loss & Cardio Circuit Split"
            schedule = [
                {"day": "Monday", "focus": "Chest, Triceps & HIIT Cardio", "exercises": ["Push-ups (3x15)", "Incline DB Press (3x12)", "Treadmill Sprints (15 mins)", "Jumping Jacks (3x30s)"]},
                {"day": "Tuesday", "focus": "Back, Biceps & Core", "exercises": ["Lat Pulldowns (4x12)", "Seated Cable Row (3x12)", "Planks (3x60s)", "Mountain Climbers (3x40s)"]},
                {"day": "Wednesday", "focus": "Active Recovery / Light Cardio", "exercises": ["30 min Incline Walk / Cycling", "Full Body Foam Rolling & Stretching"]},
                {"day": "Thursday", "focus": "Legs & Lower Body HIIT", "exercises": ["Goblet Squats (4x15)", "Bodyweight Lunges (3x12/leg)", "Burpees (3x12)", "Calf Raises (3x20)"]},
                {"day": "Friday", "focus": "Shoulders, Arms & Abs Circuit", "exercises": ["Dumbbell Shoulder Press (3x12)", "Lateral Raises (3x15)", "Bicep Curls (3x12)", "Russian Twists (3x20)"]},
                {"day": "Saturday", "focus": "Full Body Fat Burner", "exercises": ["Kettlebell Swings (4x15)", "Jump Squats (3x15)", "Box Jumps (3x10)", "20 min Rowing Machine"]},
                {"day": "Sunday", "focus": "Rest & Regeneration", "exercises": ["Rest Day - Light Walking & Hydration"]},
            ]
        elif goal == "MUSCLE_GAIN":
            cardio_focus = "Low Intensity Steady State (LISS) - 10-15 mins max"
            split_name = "Hypertrophy Push-Pull-Legs (PPL) Split"
            schedule = [
                {"day": "Monday", "focus": "Push Day (Chest, Shoulders, Triceps)", "exercises": ["Barbell Bench Press (4x8-10)", "Overhead DB Press (4x8-10)", "Dips / Cable Flyes (3x12)", "Tricep Pushdowns (3x12)"]},
                {"day": "Tuesday", "focus": "Pull Day (Back & Biceps)", "exercises": ["Barbell Deadlift / Bent Row (4x6-8)", "Lat Pulldown (4x10)", "Barbell Bicep Curl (3x10)", "Face Pulls (3x15)"]},
                {"day": "Wednesday", "focus": "Legs & Lower Body Hypertrophy", "exercises": ["Barbell Squats (4x8-10)", "Romanian Deadlift (3x10)", "Leg Press (3x12)", "Standing Calf Raise (4x15)"]},
                {"day": "Thursday", "focus": "Rest / Active Mobility", "exercises": ["Light Walking + Dynamic Stretching"]},
                {"day": "Friday", "focus": "Upper Body Strength Focus", "exercises": ["Incline DB Press (4x8)", "Pull-ups (4xMax)", "Dumbbell Lateral Raise (4x12)", "Hammer Curls (3x10)"]},
                {"day": "Saturday", "focus": "Lower Body & Core Hypertrophy", "exercises": ["Bulgarian Split Squats (3x10/leg)", "Leg Curls (3x12)", "Hanging Leg Raises (3x15)", "Ab Wheel Rollouts (3x12)"]},
                {"day": "Sunday", "focus": "Rest & Recovery", "exercises": ["Full Rest & Protein Synthesis Recovery"]},
            ]
        else:  # MAINTENANCE
            cardio_focus = "Balanced Cardio (20 mins 3x/week)"
            split_name = "Full Body Functional Fitness Split"
            schedule = [
                {"day": "Monday", "focus": "Full Body Strength & Conditioning", "exercises": ["Squats (3x10)", "Push-ups (3x12)", "Lat Pulldown (3x10)", "Plank (3x45s)"]},
                {"day": "Tuesday", "focus": "Cardio & Core", "exercises": ["25 min Treadmill Running", "Bicycle Crunches (3x20)", "Leg Raises (3x12)"]},
                {"day": "Wednesday", "focus": "Rest / Yoga", "exercises": ["Stretching / Mobility / Yoga Session"]},
                {"day": "Thursday", "focus": "Upper Body Strength", "exercises": ["Dumbbell Bench Press (3x10)", "Seated Rows (3x10)", "Shoulder Press (3x10)"]},
                {"day": "Friday", "focus": "Lower Body & Core", "exercises": ["Lunges (3x10/leg)", "Leg Extension (3x12)", "Russian Twists (3x20)"]},
                {"day": "Saturday", "focus": "Group Fitness / Swimming / Outdoor", "exercises": ["Functional Training / Cycling / Outdoor Sports"]},
                {"day": "Sunday", "focus": "Rest Day", "exercises": ["Rest & Family Time"]},
            ]

        return {
            "split_name": split_name,
            "cardio_focus": cardio_focus,
            "schedule": schedule,
        }

    @staticmethod
    def predict_attendance_dropout_risk():
        """
        AI Attendance Risk Predictor:
        Flags members who haven't attended in 10+ days or have < 30% attendance rate over the last 30 days.
        """
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)

        active_members = MemberProfile.objects.filter(
            Q(membership_end__gte=today) | Q(membership_end__isnull=True)
        )

        risk_list = []
        for member in active_members:
            attendances_30 = Attendance.objects.filter(member=member, date__gte=thirty_days_ago, status="PRESENT")
            count_30 = attendances_30.count()
            last_attendance = Attendance.objects.filter(member=member, status="PRESENT").order_by('-date').first()

            days_since_last = (today - last_attendance.date).days if last_attendance else 999
            attendance_rate = round((count_30 / 30) * 100, 1)

            risk_level = "LOW"
            risk_reason = "Regular attendee"

            if days_since_last >= 14 or count_30 <= 2:
                risk_level = "HIGH"
                risk_reason = f"No attendance for {days_since_last if days_since_last != 999 else 'many'} days"
            elif days_since_last >= 7 or count_30 <= 5:
                risk_level = "MEDIUM"
                risk_reason = f"Low monthly attendance ({count_30} sessions in 30 days)"

            if risk_level in ["HIGH", "MEDIUM"]:
                risk_list.append({
                    "member": member,
                    "count_30": count_30,
                    "attendance_rate": attendance_rate,
                    "days_since_last": days_since_last if days_since_last != 999 else "Never",
                    "risk_level": risk_level,
                    "risk_reason": risk_reason,
                })

        risk_list.sort(key=lambda x: (x["risk_level"] == "HIGH", x["days_since_last"] if isinstance(x["days_since_last"], int) else 999), reverse=True)
        return risk_list

    @staticmethod
    def calculate_revenue_forecast():
        """
        Simple Linear Projection for next 3 months revenue based on past monthly trends.
        """
        today = timezone.now().date()
        monthly_revenues = []
        months_labels = []

        for i in range(5, -1, -1):
            m = today.month - i
            y = today.year
            if m <= 0:
                m += 12
                y -= 1
            rev = Payment.objects.filter(
                payment_date__month=m, payment_date__year=y, status="PAID"
            ).aggregate(total=Sum('amount'))['total'] or 0
            monthly_revenues.append(float(rev))
            from datetime import date
            months_labels.append(date(y, m, 1).strftime("%b %Y"))

        avg_revenue = sum(monthly_revenues) / len(monthly_revenues) if monthly_revenues else 0
        recent_trend = (monthly_revenues[-1] - monthly_revenues[0]) / max(1, len(monthly_revenues) - 1)

        forecast_data = []
        forecast_labels = []
        for j in range(1, 4):
            fm = today.month + j
            fy = today.year
            if fm > 12:
                fm -= 12
                fy += 1
            from datetime import date
            forecast_labels.append(date(fy, fm, 1).strftime("%b %Y (Forecast)"))
            projected = max(0, round(monthly_revenues[-1] + (recent_trend * j)))
            forecast_data.append(projected)

        return {
            "historical_labels": months_labels,
            "historical_data": monthly_revenues,
            "forecast_labels": forecast_labels,
            "forecast_data": forecast_data,
            "avg_monthly_revenue": round(avg_revenue, 2),
            "projected_next_month": forecast_data[0] if forecast_data else 0,
        }
