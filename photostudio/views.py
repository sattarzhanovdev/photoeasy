import io
from datetime import timedelta

from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from .models import Photographer, PhotoSession, SessionPhoto, PhotoOrder
from .serializers import (
    UserRegisterSerializer,
    PhotographerSerializer,
    PhotoSessionSerializer,
    SessionPhotoSerializer,
    PhotoOrderSerializer,
    SessionPhotoGallerySerializer
)
from .utils import extract_face_encoding_from_file, add_watermark_to_bytes, face_distance


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
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.photographer


class PhotographerDashboardView(APIView):
    """
    GET /api/me/dashboard/
    Финансовый дашборд фотографа.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        photographer = request.user.photographer

        orders = PhotoOrder.objects.filter(photographer=photographer)
        sessions = PhotoSession.objects.filter(photographer=photographer)

        total_earning = orders.aggregate(total=Sum("amount"))["total"] or 0
        total_orders = orders.count()
        total_sessions = sessions.count()

        today = timezone.now().date()
        from_date = today - timedelta(days=30)

        recent_orders = orders.filter(paid_at__date__gte=from_date)
        recent_earning = recent_orders.aggregate(total=Sum("amount"))["total"] or 0

        earning_by_day = (
            recent_orders
            .annotate(day=TruncDate("paid_at"))
            .values("day")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("day")
        )

        return Response(
            {
                "total_earning": total_earning,
                "total_orders": total_orders,
                "total_sessions": total_sessions,
                "last_30_days_earning": recent_earning,
                "earning_by_day": list(earning_by_day),
            }
        )


# ========== ФОТОСЕССИИ ==========

class PhotoSessionViewSet(viewsets.ModelViewSet):
    """
    /api/sessions/        (GET, POST)
    /api/sessions/{id}/   (GET, PUT, PATCH, DELETE)
    """
    serializer_class = PhotoSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PhotoSession.objects.filter(photographer=self.request.user.photographer)

    def perform_create(self, serializer):
        photographer = self.request.user.photographer
        # Коды генерируются в models.PhotoSession.save()
        serializer.save(photographer=photographer)


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
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        # находим сессию только этого фотографа
        session = get_object_or_404(
            PhotoSession,
            id=session_id,
            photographer=request.user.photographer,
        )

        files = request.FILES.getlist("images")
        if not files:
            return Response({"detail": "Не переданы файлы 'images'"}, status=400)

        created = []
        with transaction.atomic():
            for f in files:
                raw = f.read()

                # encoding для поиска по лицу
                try:
                    encoding = extract_face_encoding_from_file(ContentFile(raw, f.name))
                except RuntimeError as e:
                    return Response({"detail": str(e)}, status=500)

                original_file = ContentFile(raw, name=f.name)

                photo = SessionPhoto(
                    session=session,
                    original_image=original_file,
                    face_encoding=encoding,
                )
                # внутри save() генерируется watermarked_image
                photo.save()
                created.append(photo)

        data = SessionPhotoSerializer(created, many=True).data
        return Response(data, status=201)



# ========== ПОИСК ПО ЛИЦУ ==========

class FaceSearchView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("image")
        if not file:
            return Response({"detail": "Не передано поле 'image'"}, status=400)

        data = file.read()
        encoding = extract_face_encoding_from_file(ContentFile(data, name=file.name))
        if encoding is None:
            return Response({"detail": "Лицо не найдено на фото"}, status=400)

        photos = SessionPhoto.objects.all()
        matches = []
        THRESHOLD = 0.45

        for p in photos:
            if not p.face_encoding:
                continue

            enc2 = list(map(float, p.face_encoding))

            dist = face_distance(encoding, enc2)
            if dist <= THRESHOLD:
                matches.append({
                    "photo_id": p.id,
                    "image_url": (
                        p.watermarked_image.url if p.watermarked_image else p.original_image.url
                    ),
                    "session_id": p.session_id,
                    "client_name": p.session.client_name,
                    "distance": float(dist),
                })

        return Response({"matches": matches})



# ========== ЗАКАЗЫ (после оплаты) ==========

class PhotoOrderCreateView(generics.CreateAPIView):
    """
    POST /api/orders/

    Тело запроса (после оплаты):

    {
      "session": 3,
      "client_name": "Иван Иванов",
      "client_phone": "+996...",
      "paid_at": "2025-11-18T12:00:00Z",
      "amount": "2500.00",
      "photos": [1, 2, 5]
    }
    """
    serializer_class = PhotoOrderSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        session = None
        photographer = None

        session_id = self.request.data.get("session")
        if session_id:
            try:
                session = PhotoSession.objects.get(id=session_id)
                photographer = session.photographer
            except PhotoSession.DoesNotExist:
                pass

        serializer.save(photographer=photographer, session=session)

class SessionPhotoListView(generics.ListAPIView):
    """
    GET /api/photos/?view_code=ABCD1234

    Возвращает фото (с водяным знаком) для фотосессии с указанным view_code
    + download_code этой сессии.
    """
    serializer_class = SessionPhotoGallerySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        view_code = self.request.query_params.get("view_code")

        # чтобы list() мог достать эту сессию
        self.session = None

        if not view_code:
            return SessionPhoto.objects.none()

        session = get_object_or_404(PhotoSession, view_code=view_code)
        self.session = session

        return (
            SessionPhoto.objects
            .filter(session=session)
            .select_related("session")
            .order_by("uploaded_at")
        )

    def list(self, request, *args, **kwargs):
        # стандартный список фоток
        response = super().list(request, *args, **kwargs)

        # если сессия найдена – оборачиваем ответ
        if getattr(self, "session", None):
            return Response({
                "session": {
                    "id": self.session.id,
                    "client_name": self.session.client_name,
                    "view_code": self.session.view_code,
                    "download_code": self.session.download_code,
                },
                "photos": response.data,
            })

        # если кода нет – вернётся пустой список
        return response
