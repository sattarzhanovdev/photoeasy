from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum

from .models import Photographer, PhotoSession, SessionPhoto, PhotoOrder


@admin.register(Photographer)
class PhotographerAdmin(admin.ModelAdmin):
    list_display = ("id", "studio_name", "first_name", "last_name", "user")
    search_fields = ("studio_name", "first_name", "last_name", "user__username")


@admin.register(PhotoSession)
class PhotoSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_name",
        "client_phone",
        "photographer",
        "date",
        "price",
        "view_code",
        "download_code",
        "created_at",
    )
    list_filter = ("photographer", "date", "created_at")
    search_fields = ("client_name", "client_phone", "view_code", "download_code")
    readonly_fields = ("view_code", "download_code", "created_at")


@admin.register(SessionPhoto)
class SessionPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "preview", "uploaded_at", "has_encoding")
    list_filter = ("session__photographer", "uploaded_at")
    search_fields = ("session__client_name", "session__client_phone")

    def preview(self, obj):
        if obj.watermarked_image:
            return format_html(
                '<img src="{}" style="height: 80px; border-radius: 4px; object-fit: cover;" />',
                obj.watermarked_image.url,
            )
        return "-"
    preview.short_description = "Превью"

    def has_encoding(self, obj):
        return bool(obj.face_encoding)
    has_encoding.boolean = True
    has_encoding.short_description = "Есть face encoding"


@admin.register(PhotoOrder)
class PhotoOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "client_name", "client_phone", "amount", "paid_at", "photographer", "session")
    list_filter = ("photographer", "paid_at")
    search_fields = ("client_name", "client_phone")

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        total = qs.aggregate(total=Sum("amount"))["total"] or 0
        response.context_data["summary_total"] = total
        return response
