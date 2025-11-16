from django.contrib import admin, messages
from django import forms
from django.utils.html import format_html

from .models import Photographer, PhotoSession, SessionPhoto
from .utils import extract_face_encoding_from_file


# =========================
# КАСТОМНЫЙ ВИДЖЕТ ДЛЯ MULTIPLE
# =========================
class MultiFileInput(forms.ClearableFileInput):
    """
    Разрешаем выбор нескольких файлов в Django 5.
    """
    allow_multiple_selected = True


# =========================
# ФОРМА ДЛЯ MULTIPLE UPLOAD
# =========================
class SessionPhotoAdminForm(forms.ModelForm):
    # НЕ привязано к модельному полю, просто "виртуальное" поле
    images = forms.Field(
        label="Изображения",
        widget=MultiFileInput(attrs={"multiple": True}),
        required=False,
    )

    class Meta:
        model = SessionPhoto
        # В форме показываем только сессию (из модели)
        fields = ("session",)


# =========================
# ADMIN
# =========================

@admin.register(Photographer)
class PhotographerAdmin(admin.ModelAdmin):
    list_display = ("id", "studio_name", "first_name", "last_name", "username")
    search_fields = ("studio_name", "first_name", "last_name", "user__username")

    def username(self, obj):
        return obj.user.username

    username.short_description = "Логин"


@admin.register(PhotoSession)
class PhotoSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_name",
        "client_phone",
        "photographer",
        "view_code",
        "download_code",
        "created_at",
    )
    search_fields = ("client_name", "client_phone", "view_code", "download_code")
    list_filter = ("photographer", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("view_code", "download_code")  # ⬅️ вот это

@admin.register(SessionPhoto)
class SessionPhotoAdmin(admin.ModelAdmin):
    form = SessionPhotoAdminForm
    list_display = ("id", "session", "thumbnail", "uploaded_at")
    list_filter = ("session__photographer", "uploaded_at")
    search_fields = ("session__client_name", "session__view_code")
    readonly_fields = ("uploaded_at",)

    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px; border-radius:4px;" />',
                obj.image.url,
            )
        return "No image"

    thumbnail.short_description = "Превью"

    def save_model(self, request, obj, form, change):
        """
        При добавлении создаём несколько SessionPhoto по полю images.
        """
        # ВСЕ файлы из поля 'images'
        files = request.FILES.getlist("images")

        if not files:
            messages.error(request, "Вы не выбрали ни одного файла.")
            return

        session = form.cleaned_data["session"]
        created_count = 0

        for f in files:
            encoding = extract_face_encoding_from_file(f)
            f.seek(0)

            SessionPhoto.objects.create(
                session=session,
                image=f,
                face_encoding=encoding,
            )
            created_count += 1

        messages.success(
            request,
            f"Успешно добавлено {created_count} фотографий в сессию {session}.",
        )

    def response_add(self, request, obj, post_url_continue=None):
        """
        После добавления возвращаемся в список SessionPhoto.
        """
        from django.shortcuts import redirect

        return redirect("admin:photostudio_sessionphoto_changelist")
