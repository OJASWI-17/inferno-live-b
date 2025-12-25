from django.contrib.auth import logout
from django.contrib.sessions.models import Session
import logging

logger = logging.getLogger(__name__)

class SessionAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_urls = ['/healthcheck/', '/status/']

    def __call__(self, request):
        # Skip middleware for exempt URLs
        if any(request.path.startswith(url) for url in self.exempt_urls):
            return self.get_response(request)

        # Ensure that request has user (requires AuthenticationMiddleware to run before this)
        if hasattr(request, 'user') and request.user.is_authenticated:
            session_key = request.session.session_key

            # Check if the session exists in the database
            if session_key and not Session.objects.filter(session_key=session_key).exists():
                logger.warning(
                    f"Invalid session for user {request.user.id} - IP: {request.META.get('REMOTE_ADDR')}"
                )
                logout(request)

        return self.get_response(request)
