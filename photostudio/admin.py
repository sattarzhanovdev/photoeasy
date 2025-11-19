from django.contrib import admin, messages
from django.shortcuts import redirect
from django.utils.html import format_html
from django.db.models import Sum

from .models import (
    Photographer,
    PhotoSession,
    SessionPhoto,
    PhotoOrder,
    Service,
)


# ====== ФОТОГРАФЫ ======

@admin.register(Photographer)
class PhotographerAdmin(admin.ModelAdmin):
    list_display = ("id", "studio_name", "first_name", "last_name", "user")
    search_fields = ("studio_name", "first_name", "last_name", "user__username")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # обычный фотограф видит только себя
        if hasattr(request.user, "photographer"):
            return qs.filter(id=request.user.photographer.id)
        return qs.none()


# ====== УСЛУГИ (ПРАЙС) ======

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "photographer", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # фотограф видит только свои услуги
        if hasattr(request.user, "photographer"):
            return qs.filter(photographer=request.user.photographer)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # поле "photographer" – автоматически подставляем текущего
        if db_field.name == "photographer" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = Photographer.objects.filter(
                    id=request.user.photographer.id
                )
                kwargs["initial"] = request.user.photographer
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ====== ФОТОСЕССИИ ======

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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # фотограф видит только свои сессии
        if hasattr(request.user, "photographer"):
            return qs.filter(photographer=request.user.photographer)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # поле "photographer" – ограничиваем только текущим фотографом
        if db_field.name == "photographer" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = Photographer.objects.filter(
                    id=request.user.photographer.id
                )
                kwargs["initial"] = request.user.photographer
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ====== ФОТО СЕССИИ ======

@admin.register(SessionPhoto)
class SessionPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "uploaded_at")
    list_filter = ("session__photographer", "uploaded_at")
    readonly_fields = ("watermarked_image", "face_encoding")

    # --- показываем только свои фотосессии фотографу ---
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "session" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = PhotoSession.objects.filter(
                    photographer=request.user.photographer
                )
            else:
                kwargs["queryset"] = PhotoSession.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # --- в форме включаем multiple для поля original_image ---
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "original_image" in form.base_fields:
            widget = form.base_fields["original_image"].widget
            widget.attrs["multiple"] = True        # <-- главное место
        return form

    # --- кастомная логика add_view: создаём много SessionPhoto за один POST ---
    def add_view(self, request, form_url="", extra_context=None):
        """
        Если пользователь выбрал несколько файлов в original_image,
        создаём отдельный SessionPhoto для каждого файла.
        """
        if request.method == "POST":
            files = request.FILES.getlist("original_image")
            # если файлов > 1 — запускаем массовое создание
            if len(files) > 1:
                session_id = request.POST.get("session")
                if not session_id:
                    messages.error(request, "Выберите фотосессию.")
                    # даём стандартный флоу, чтобы показать ошибку
                    return super().add_view(request, form_url, extra_context)

                try:
                    session = PhotoSession.objects.get(pk=session_id)
                except PhotoSession.DoesNotExist:
                    messages.error(request, "Выбранная фотосессия не найдена.")
                    return super().add_view(request, form_url, extra_context)

                created = 0
                for f in files:
                    photo = SessionPhoto(session=session, original_image=f)
                    # в save() уже генерируется face_encoding и watermarked_image
                    photo.save()
                    created += 1

                messages.success(
                    request,
                    f"Успешно загружено {created} фотографий в сессию «{session}».",
                )
                # после загрузки — обратно в список фотографий
                return redirect("admin:photos_sessionphoto_changelist")

        # если один файл или GET — обычное поведение админки
        return super().add_view(request, form_url, extra_context)


# ====== ЗАКАЗЫ ======

@admin.register(PhotoOrder)
class PhotoOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_name",
        "client_phone",
        "amount",
        "paid_at",
        "photographer",
        "session",
    )
    list_filter = ("photographer", "paid_at")
    search_fields = ("client_name", "client_phone")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # фотограф видит только свои заказы
        if hasattr(request.user, "photographer"):
            return qs.filter(photographer=request.user.photographer)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # фотограф в заказе — всегда текущий пользователь
        if db_field.name == "photographer" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = Photographer.objects.filter(
                    id=request.user.photographer.id
                )
                kwargs["initial"] = request.user.photographer

        # список фотосессий – только свои
        if db_field.name == "session" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = PhotoSession.objects.filter(
                    photographer=request.user.photographer
                )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # фотографии – только свои
        if db_field.name == "photos" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = SessionPhoto.objects.filter(
                    session__photographer=request.user.photographer
                )

        # услуги – только свои
        if db_field.name == "services" and not request.user.is_superuser:
            if hasattr(request.user, "photographer"):
                kwargs["queryset"] = Service.objects.filter(
                    photographer=request.user.photographer,
                    is_active=True,
                )

        return super().formfield_for_manytomany(db_field, request, **kwargs)

    # суммарная выручка по отфильтрованным заказам
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        total = qs.aggregate(total=Sum("amount"))["total"] or 0
        response.context_data["summary_total"] = total
        return response
