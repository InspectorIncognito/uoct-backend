import re

from django.utils.deprecation import MiddlewareMixin


class CSRFExemptAPIMiddleware(MiddlewareMixin):
    """
    Middleware to exempt API endpoints from CSRF verification.
    All URLs starting with /api/ will be exempt from CSRF checks.
    """

    def process_request(self, request):
        if request.path.startswith("/api/"):
            setattr(request, "_dont_enforce_csrf_checks", True)
        return None
