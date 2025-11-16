from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import generics, permissions, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import Photographer, PhotoSession, SessionPhoto
from .serializers import (
    UserRegisterSerializer,
    PhotographerSerializer,
    PhotoSessionSerializer,
    SessionPhotoSerializer,
)
from .utils import extract_face_encoding_from_file, face_distance


# ========== АУТЕНТИФИКАЦИЯ ==========

class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    {
      "username": "photo1",
      "password": "12345678",
      "first_name": "Иван",
      "last_name": "Иванов",
      "studio_name": "Studio X"
    }
    """
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        Token.objects.create(user=user)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """
    POST /api/auth/login/
    { "username": "...", "password": "..." }
    -> { "token": "..." }
    """
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    if not user:
        return Response({"detail": "Неверный логин или пароль"}, status=400)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key})


# ========== ЛИЧНЫЙ КАБИНЕТ ФОТОГРАФА ==========

class PhotographerMeView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/me/
    """
    serializer_class = PhotographerSerializer

    def get_object(self):
        return self.request.user.photographer


# ========== ФОТОСЕССИИ ==========

import secrets
import string


def _generate_code(length=8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PhotoSessionViewSet(viewsets.ModelViewSet):
    """
    /api/sessions/        (GET, POST)
    /api/sessions/{id}/   (GET, PUT, PATCH, DELETE)
    """
    serializer_class = PhotoSessionSerializer

    def get_queryset(self):
        return PhotoSession.objects.filter(photographer=self.request.user.photographer)

    def perform_create(self, serializer):
        photographer = self.request.user.photographer

        view_code = _generate_code()
        download_code = _generate_code()
        while PhotoSession.objects.filter(view_code=view_code).exists():
            view_code = _generate_code()
        while PhotoSession.objects.filter(download_code=download_code).exists():
            download_code = _generate_code()

        serializer.save(
            photographer=photographer,
            view_code=view_code,
            download_code=download_code,
        )


# ========== МАССОВАЯ ЗАГРУЗКА ФОТО ==========

class SessionPhotoBulkUploadView(generics.GenericAPIView):
    """
    POST /api/sessions/{session_id}/photos/bulk-upload/
    Form-data:
      images: file1
      images: file2
      ...
    """
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = SessionPhotoSerializer

    def post(self, request, session_id):
        user = request.user
        try:
            session = PhotoSession.objects.get(
                id=session_id, photographer=user.photographer
            )
        except PhotoSession.DoesNotExist:
            return Response({"detail": "Сессия не найдена"}, status=404)

        files = request.FILES.getlist("images")
        if not files:
            return Response({"detail": "Файлы не переданы (images)"}, status=400)

        created = []
        with transaction.atomic():
            for f in files:
                encoding = extract_face_encoding_from_file(f)
                # после чтения надо сбросить указатель, чтобы ImageField сохранил файл
                f.seek(0)

                photo = SessionPhoto.objects.create(
                    session=session,
                    image=f,
                    face_encoding=encoding,
                )
                created.append(photo)

        data = SessionPhotoSerializer(created, many=True).data
        return Response(data, status=201)


# ========== ПОИСК ПО ЛИЦУ ==========

class FaceSearchView(generics.GenericAPIView):
    """
    POST /api/search-by-face/
    Form-data:
      image: <file с лицом>

    Возвращает список фото с похожим лицом.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("image")
        if not file:
            return Response({"detail": "Не передано поле 'image'"}, status=400)

        # БЕЗ распаковки, только одно значение
        encoding = extract_face_encoding_from_file(file)
        if encoding is None:
            return Response(
                {"detail": "Лицо не найдено на фото"},
                status=400,
            )

        # Ищем по всем фотографиям (только по тем, где есть encoding)
        photos = SessionPhoto.objects.all()
        matches = []
        THRESHOLD = 0.6  # меньше — строже

        for p in photos:
            if not p.face_encoding:
                continue

            dist = face_distance(encoding, p.face_encoding)
            if dist <= THRESHOLD:
                matches.append(
                    {
                        "photo_id": p.id,
                        "image_url": p.image.url,
                        "session_id": p.session_id,
                        "client_name": p.session.client_name,
                        "distance": float(dist),
                    }
                )

        return Response({"matches": matches})