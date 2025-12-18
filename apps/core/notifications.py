# apps/core/notifications.py

import threading
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

class NotificationService:
    @staticmethod
    def send_html_email(user_email, subject, template_name, context, user=None):
        """
        Sends a professional HTML email with a plain-text fallback.
        Supports both authenticated users (profile checks) and 
        anonymous users (registration/login).
        """
        
        # 1. Check User Preference (Only if a User object is provided)
        # For registration/login, user might be None or not have a profile yet
        if user and hasattr(user, 'profile'):
            if not user.profile.pref_email_notifications:
                print(f"Skipping email to {user_email}: User disabled preferences.")
                return

        # 2. Add Global Branding to Context
        context['company_name'] = "Rentify"
        context['support_email'] = "support@rentify.com"

        # 3. Render HTML and Generate Plain Text Fallback
        try:
            # Looks for templates/emails/{template_name}.html
            html_content = render_to_string(f"emails/{template_name}.html", context)
            text_content = strip_tags(html_content) 
        except Exception as e:
            print(f"Template Error: {str(e)}")
            return

        # 4. Background Threading Task
        def start_send():
            try:
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user_email],
                )
                email.attach_alternative(html_content, "text/html")
                email.send(fail_silently=False)
                print(f"Professional HTML email sent successfully to {user_email}")
            except Exception as e:
                print(f"Failed to send HTML email: {str(e)}")

        # 5. Fire and Forget
        threading.Thread(target=start_send).start()

    @staticmethod
    def send_email_notification(user, subject, template_name, context):
        """
        Legacy support for existing plain-text calls if needed.
        Redirects to the new HTML method for better quality.
        """
        NotificationService.send_html_email(user.email, subject, template_name, context, user=user)