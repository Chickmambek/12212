# middleware.py (or wherever your middleware is located)
from django.http import HttpResponseForbidden
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class IPWhitelistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def get_client_ip(self, request):
        """Extract client IP address from request, handling proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # X-Forwarded-For can contain multiple IPs in comma-separated list
            # First IP is the original client
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def __call__(self, request):
        # Get client IP
        ip = self.get_client_ip(request)

        # Get allowed IPs from settings
        # Make sure settings.ALLOWED_IPS is a list, not a string
        allowed_ips = getattr(settings, 'ALLOWED_IPS', [])

        # Debug logging
        logger.debug(f"IPWhitelistMiddleware - Client IP: {ip}")
        logger.debug(f"IPWhitelistMiddleware - Allowed IPs: {allowed_ips}")
        logger.debug(f"IPWhitelistMiddleware - Path: {request.path_info}")

        # Check if this path is protected
        path = request.path_info
        # Added /admin21/ to protected paths as it contains sensitive scraper controls
        protected_paths = ['/admin/', '/dashboard/', '/admin21/']
        is_protected = any(path.startswith(protected) for protected in protected_paths)

        if is_protected:
            logger.debug(f"IPWhitelistMiddleware - Checking protected path: {path}")

            # If ALLOWED_IPS is empty list, allow all
            if not allowed_ips:
                logger.debug("IPWhitelistMiddleware - No IP restrictions (empty list)")
                return self.get_response(request)

            # Check if IP is allowed
            if ip in allowed_ips:
                logger.debug(f"IPWhitelistMiddleware - IP {ip} is allowed")
                return self.get_response(request)
            else:
                # DENIED - show detailed message
                logger.warning(f"IPWhitelistMiddleware - Access denied for IP: {ip}")
                logger.warning(f"IPWhitelistMiddleware - Allowed IPs: {allowed_ips}")

                # Use the detailed error message
                error_message = (
                    f"Access Denied. Your IP: {ip}. "
                    f"Allowed IPs: {', '.join(allowed_ips)}"
                )
                return HttpResponseForbidden(error_message)

        # Not a protected path, allow access
        return self.get_response(request)
