from django.http import HttpResponseForbidden
from django.conf import settings


class IPWhitelistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the real client IP (handles proxies)
        def get_client_ip(request):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                # X-Forwarded-For can contain multiple IPs, first is original client
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip

        ip = get_client_ip(request)

        # Check if IP is allowed for protected paths
        allowed_ips = getattr(settings, 'ALLOWED_IPS', [])

        # Protect admin and dashboard
        path = request.path_info
        if path.startswith('/admin/') or path.startswith('/dashboard/'):
            # If ALLOWED_IPS is empty list, allow all (no restriction)
            if allowed_ips and ip not in allowed_ips:
                return HttpResponseForbidden(
                    f"Access Denied. Your IP: {ip}. "
                    f"Allowed IPs: {', '.join(allowed_ips)}"
                )

        return self.get_response(request)