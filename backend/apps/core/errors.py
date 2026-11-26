from django.http import JsonResponse


def csrf_failure(request,reason=''):
    return JsonResponse({'code':'csrf_failed','detail':'Your security token is missing or expired. Reload the page and try again.'},status=403)
