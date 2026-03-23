from django.shortcuts import render

def global_sw(request):
    return render(request, 'pwa/sw_global.js', content_type='application/javascript; charset=utf-8')

def global_manifest(request):
    role = ''
    if request.user.is_authenticated:
        m = request.user.memberships.filter(is_active=True).first()
        role = m.role.name if m else ''
    return render(request, 'pwa/manifest_global.json', {'role': role}, content_type='application/json')

def offline_global(request):
    return render(request, 'pwa/offline_global.html')

