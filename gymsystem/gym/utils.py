import csv
import io
import base64
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.conf import settings


def generate_qr_code_base64(data_text):
    """
    Generates a QR Code as a base64 encoded PNG or SVG data URI.
    Uses qrcode library if installed, or fallback SVG data URI.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(data_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        encoded = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{encoded}"
    except ImportError:
        # Fallback to Google Chart QR API URI or SVG data URI
        import urllib.parse
        encoded_text = urllib.parse.quote(data_text)
        return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded_text}"


def attach_qr_to_member(member):
    """
    Generates and attaches QR Code image file to MemberProfile.
    """
    qr_data = f"FITPRO-MEMBER-ID:{member.id}|NAME:{member.full_name}|MOBILE:{member.mobile}"
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#13132a", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        file_name = f"qr_member_{member.id}.png"
        member.qr_code.save(file_name, ContentFile(buf.getvalue()), save=True)
    except ImportError:
        pass


def export_to_csv(filename, headers, rows):
    """
    Generates a CSV HttpResponse download.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def send_system_email(subject, message, recipient_email):
    """
    Safe email sender wrapper using Django's send_mail.
    """
    if not recipient_email:
        return False
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@fitprogym.com')
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[recipient_email],
            fail_silently=True,
        )
        return True
    except Exception:
        return False
