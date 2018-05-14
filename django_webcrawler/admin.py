from django.contrib import admin

from .models import Domain, Url


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'visited_at')
    readonly_fields = ('hostname', 'visited_at', 'robots_txt', 'robots_txt_updated_at')


@admin.register(Url)
class UrlAdmin(admin.ModelAdmin):
    list_display = ('url', 'domain', 'visited_at')
    readonly_fields = ('url', 'url_sha256', 'domain', 'visited_at', 'content', 'links_to')
