import smtplib
from email.message import EmailMessage
from config import SMTP_LOGIN, SMTP_PORT, SMTP_PASSWORD, SMTP_SERVER, BRANCH_EMAILS, DEFAULT_EMAIL

def send_booking_email(data: dict):
    try:
        branch = data.get("branch")
        to_email = BRANCH_EMAILS.get(branch, DEFAULT_EMAIL)

        msg = EmailMessage()
        msg["Subject"] = f"Новая запись ({branch})"
        msg["From"] = SMTP_LOGIN
        msg["To"] = to_email

        msg.set_content(
            f"Филиал: {branch}\n"
            f"Дата: {data.get('date')}\n"
            f"Время: {data.get('time')}\n"
            f"Имя: {data.get('name')}\n"
            f"Телефон: {data.get('phone')}"
        )

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(SMTP_LOGIN, SMTP_PASSWORD)
            smtp.send_message(msg)

        print(f"[OK] Письмо отправлено на {to_email} ({branch})")

    except Exception as e:
        print(f"Ошибка при отправке письма для филиала {branch}: {e}")


def cancel_email(data: dict):
    try:
        branch = data.get("branch")
        to_email = BRANCH_EMAILS.get(branch, DEFAULT_EMAIL)

        msg = EmailMessage()
        msg["Subject"] = f"❌ Отмена записи ({branch})"
        msg["From"] = SMTP_LOGIN
        msg["To"] = to_email

        msg.set_content(
            f"‼️ Отмена записи:\n"
            f"Филиал: {branch}\n"
            f"Дата: {data.get('date')}\n"
            f"Время: {data.get('time')}\n"
            f"Имя: {data.get('name')}\n"
            f"Телефон: {data.get('phone')}"
        )

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(SMTP_LOGIN, SMTP_PASSWORD)
            smtp.send_message(msg)

        print(f"[OK] Отмена отправлена на {to_email} ({branch})")

    except Exception as e:
        print(f"Ошибка при отправке отмены для {branch}: {e}")

