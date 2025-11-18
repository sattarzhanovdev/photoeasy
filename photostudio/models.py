import os
from django.db import models
from django.contrib.auth import get_user_model

from .utils import add_watermark_to_bytes

import io
from django.db import models
from django.core.files.base import ContentFile
from django.utils.crypto import get_random_string
from django.conf import settings

from .utils import extract_face_encoding_from_file, add_watermark_to_bytes
User = get_user_model()


def _generate_code(length: int = 8) -> str:
    import string, random
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


def _generate_unique_code(model, field_name: str, length: int = 8) -> str:
    code = _generate_code(length)
    while model.objects.filter(**{field_name: code}).exists():
        code = _generate_code(length)
    return code


class Photographer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    studio_name = models.CharField(max_length=255)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.studio_name} ({self.first_name})"


class PhotoSession(models.Model):
    photographer = models.ForeignKey(Photographer, on_delete=models.CASCADE)
    client_name = models.CharField(max_length=255)
    client_phone = models.CharField(max_length=50)
    date = models.DateField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    view_code = models.CharField(max_length=12, unique=True, blank=True)
    download_code = models.CharField(max_length=12, unique=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.view_code:
            self.view_code = get_random_string(10).upper()

        if not self.download_code:
            self.download_code = get_random_string(10).upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client_name} — {self.photographer}"


class SessionPhoto(models.Model):
    session = models.ForeignKey(PhotoSession, on_delete=models.CASCADE)
    original_image = models.ImageField(upload_to="photos/originals/")
    watermarked_image = models.ImageField(upload_to="photos/watermarked/", blank=True, null=True)
    face_encoding = models.JSONField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Если оригинал новый — генерируем всё
        if not self.pk and self.original_image:
            # 1) ЧИТАЕМ ФАЙЛ ТОЛЬКО ОДИН РАЗ!
            data = self.original_image.read()

            # 2) ДЕЛАЕМ ENCODING
            try:
                self.face_encoding = extract_face_encoding_from_file(ContentFile(data, name=self.original_image.name))
            except Exception:
                self.face_encoding = None

            # 3) ДЕЛАЕМ ВОДЯНОЙ ЗНАК
            try:
                wm_bytes = add_watermark_to_bytes(data, text="WATERMARK")
                wm_name = f"wm_{self.original_image.name}"
                self.watermarked_image.save(wm_name, ContentFile(wm_bytes), save=False)
            except Exception:
                pass

            # 4) ВОССТАНАВЛИВАЕМ ФАЙЛ (НА ВАЖНО!)
            self.original_image = ContentFile(data, name=self.original_image.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Photo {self.id} — Session {self.session_id}"


class PhotoOrder(models.Model):
    photographer = models.ForeignKey(
        Photographer,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name="Фотограф",
    )
    session = models.ForeignKey(
        PhotoSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Фотосессия",
    )

    client_name = models.CharField("Ф.И.О клиента", max_length=255)
    client_phone = models.CharField("Телефон клиента", max_length=50)
    paid_at = models.DateTimeField("Дата оплаты")
    amount = models.DecimalField("Сумма заказа", max_digits=10, decimal_places=2)

    photos = models.ManyToManyField(
        SessionPhoto,
        related_name="orders",
        verbose_name="Фотографии, которые скачал клиент",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Заказ #{self.id} ({self.client_name})"
