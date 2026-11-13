from django.conf import settings
from django.http import HttpResponse

class AvailabilityMiddleware:
    """W13-only rollout gate; never intercepts the W5 namespace."""
    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        if match and match.app_name == 'showcase' and not response.streaming:
            from django.utils.cache import add_never_cache_headers
            add_never_cache_headers(response)
        return response

    def process_view(self,request,view_func,view_args,view_kwargs):
        if not request.resolver_match or request.resolver_match.app_name != 'showcase':
            return None
        unavailable=not getattr(settings,'W13_ENABLED',False)
        read_only=(request.method not in ('GET','HEAD','OPTIONS') and
                   not getattr(settings,'W13_WRITES_ENABLED',False))
        if unavailable or read_only:
            return HttpResponse('W13 is temporarily unavailable.' if unavailable else
                                'W13 is temporarily read-only. Your existing submissions are preserved.',
                                status=503,headers={'Retry-After':'300'},content_type='text/plain; charset=utf-8')
