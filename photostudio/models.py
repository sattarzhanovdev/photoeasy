from django.db import models
from django.contrib.auth.models import User

import string
import random
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Photographer(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="photographer"
    )
    first_name = models.CharField("Имя", max_length=100)
    last_name = models.CharField("Фамилия", max_length=100)
    studio_name = models.CharField("Название фотостудии", max_length=255)

    def __str__(self):
        return f"{self.studio_name} ({self.first_name} {self.last_name})"



def _generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


def _generate_unique_code(model, field_name: str, length: int = 8) -> str:
    """
    Генерирует уникальный код для указанного поля модели.
    """
    code = _generate_code(length)
    while model.objects.filter(**{field_name: code}).exists():
        code = _generate_code(length)
    return code


class PhotoSession(models.Model):
    photographer = models.ForeignKey(
        "Photographer",
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="Фотограф",
    )
    client_name = models.CharField("Имя клиента", max_length=255)
    client_phone = models.CharField("Телефон клиента", max_length=50)

    # ⬇️ Коды — генерируются автоматически, в админке не редактируются
    view_code = models.CharField(
        "Код для просмотра",
        max_length=16,
        unique=True,
        editable=False,
        blank=True,
    )
    download_code = models.CharField(
        "Код для скачивания",
        max_length=16,
        unique=True,
        editable=False,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # при создании сессии генерим коды, если их нет
        if not self.view_code:
            self.view_code = _generate_unique_code(
                PhotoSession, "view_code", length=8
            )
        if not self.download_code:
            self.download_code = _generate_unique_code(
                PhotoSession, "download_code", length=10
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client_name} ({self.photographer.studio_name})"


class SessionPhoto(models.Model):
    session = models.ForeignKey(
        PhotoSession, on_delete=models.CASCADE, related_name="photos"
    )
    image = models.ImageField(upload_to="session_photos/%Y/%m/%d/")
    # embeding лица
    face_encoding = models.JSONField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo #{self.id} of session {self.session_id}"
