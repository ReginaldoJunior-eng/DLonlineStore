"""URL configuration for dlstore project."""
from django.contrib import admin
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import path, include, re_path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('campineira/', include('campineira.urls')),
    path('upseller/', include('upseller.urls')),
]

# staticfiles.views.serve acha os arquivos direto nas pastas static/ de cada
# app (AppDirectoriesFinder) — funciona sem precisar rodar `collectstatic`
# antes, diferente do helper static()+STATIC_ROOT (que só serve o que já foi
# coletado ali, e ficava 404 pro logo.png dentro do .exe empacotado, onde
# collectstatic nunca roda). Registrado direto (não via
# staticfiles_urlpatterns()/static() — os dois retornam lista VAZIA quando
# DEBUG=False, apesar da documentação sugerir o contrário à primeira vista)
# porque esse app roda com DEBUG=False empacotado e não usa um servidor de
# estáticos separado — é local, um usuário só, sem exposição à internet.
urlpatterns += [
    # insecure=True: staticfiles.views.serve recusa rodar com DEBUG=False a
    # não ser que isso seja passado explicitamente (pensado exatamente pra
    # esse cenário — servidor local, sem exposição à internet).
    re_path(r'^static/(?P<path>.*)$', staticfiles_serve, kwargs={'insecure': True}),
]
