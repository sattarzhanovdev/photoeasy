import io
from django.http import HttpResponse
from openpyxl import Workbook

from datetime import timedelta
from django.contrib.auth.decorators import login_required

from django.contrib.auth import authenticate, get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.shortcuts import get_object_or_404, render

from rest_framework import generics, permissions, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from django.contrib.admin.views.decorators import staff_member_required
from .models import Photographer, PhotoSession, SessionPhoto, PhotoOrder, Service
from .serializers import (
    UserRegisterSerializer,
    PhotographerSerializer,
    PhotoSessionSerializer,
    SessionPhotoSerializer,
    PhotoOrderSerializer,
    SessionPhotoGallerySerializer,
    ServiceSerializer
)
from .utils import (
    extract_face_encoding_from_file,
    add_watermark_to_bytes,
    face_distance,
)

User = get_user_model()


# ========== КАСТОМНАЯ АДМИН-ПАНЕЛЬ (ДОБРОВОЛЬНО) ==========

@login_required
def dashboard_export_xlsx(request):
    """
    XLSX-отчёт:
    - superuser получает данные по всем фотографам
    - обычный фотограф — только свои данные
    """
    user = request.user

    # тот же scope, что и в dashboard_view
    if user.is_superuser:
        scope_label = "Все фотографы"
        orders_qs = PhotoOrder.objects.all()
        sessions_qs = PhotoSession.objects.all()
        photos_qs = SessionPhoto.objects.all()
    else:
        if not hasattr(user, "photographer"):
            scope_label = "Нет привязанного профиля фотографа"
            orders_qs = PhotoOrder.objects.none()
            sessions_qs = PhotoSession.objects.none()
            photos_qs = SessionPhoto.objects.none()
        else:
            photographer = user.photographer
            scope_label = f"Фотограф: {photographer.studio_name}"
            orders_qs = PhotoOrder.objects.filter(photographer=photographer)
            sessions_qs = PhotoSession.objects.filter(photographer=photographer)
            photos_qs = SessionPhoto.objects.filter(session__photographer=photographer)

    total_earning = orders_qs.aggregate(total=Sum("amount"))["total"] or 0
    total_orders = orders_qs.count()
    total_sessions = sessions_qs.count()
    total_photos = photos_qs.count()

    today = timezone.now().date()
    from_date = today - timezone.timedelta(days=30)
    recent_orders = orders_qs.filter(paid_at__date__gte=from_date)
    last_30_days_earning = recent_orders.aggregate(total=Sum("amount"))["total"] or 0

    # -------- создаём Excel --------
    wb = Workbook()

    # Лист 1: Summary
    ws_summary = wb.active
    ws_summary.title = "Сводка"

    ws_summary.append(["Отчёт по:", scope_label])
    ws_summary.append([])
    ws_summary.append(["Показатель", "Значение"])
    ws_summary.append(["Общая выручка", float(total_earning)])
    ws_summary.append(["Выручка за 30 дней", float(last_30_days_earning)])
    ws_summary.append(["Количество заказов", total_orders])
    ws_summary.append(["Количество фотосессий", total_sessions])
    ws_summary.append(["Количество фотографий", total_photos])

    # Лист 2: Заказы
    ws_orders = wb.create_sheet("Заказы")
    ws_orders.append([
        "ID заказа",
        "Клиент",
        "Телефон",
        "Фотограф",
        "Фотосессия",
        "Оплачено (дата/время)",
        "Сумма",
        "Услуги",
    ])

    orders_qs = orders_qs.select_related("session", "photographer").prefetch_related("services")

    for order in orders_qs.order_by("-paid_at"):
        if order.photographer:
            photographer_name = f"{order.photographer.studio_name}"
        else:
            photographer_name = ""

        session_client = order.session.client_name if order.session else ""

        # если ты добавил ManyToMany Service -> PhotoOrder
        services_list = [s.name for s in order.services.all()] if hasattr(order, "services") else []
        services_str = ", ".join(services_list)

        ws_orders.append([
            order.id,
            order.client_name,
            order.client_phone,
            photographer_name,
            session_client,
            timezone.localtime(order.paid_at).strftime("%Y-%m-%d %H:%M") if order.paid_at else "",
            float(order.amount),
            services_str,
        ])

    # немного увеличить ширину колонок
    for col in ws_orders.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                value_len = len(str(cell.value))
                if value_len > max_len:
                    max_len = value_len
            except Exception:
                pass
        ws_orders.column_dimensions[col_letter].width = max(max_len + 2, 12)

    # -------- отдаём файл пользователю --------
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    filename = f"dashboard_{timezone.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


@login_required
def dashboard(request):
    users_active = User.objects.filter(is_active=True).count()
    orders_count = PhotoOrder.objects.count()
    sessions_count = PhotoSession.objects.count()
    photos_count = SessionPhoto.objects.count()

    context = {
        "users_active": users_active,
        "orders_count": orders_count,
        "sessions_count": sessions_count,
        "photos_count": photos_count,
    }
    return render(request, "dashboard.html", context)

@login_required
def dashboard_view(request):
    user = request.user

    if user.is_superuser:
        scope_label = "Все фотографы"
        orders_qs = PhotoOrder.objects.all()
        sessions_qs = PhotoSession.objects.all()
        photos_qs = SessionPhoto.objects.all()
        services_qs = Service.objects.all()
    else:
        if not hasattr(user, "photographer"):
            scope_label = "Нет привязанного профиля фотографа"
            orders_qs = PhotoOrder.objects.none()
            sessions_qs = PhotoSession.objects.none()
            photos_qs = SessionPhoto.objects.none()
            services_qs = Service.objects.none()
        else:
            photographer = user.photographer
            scope_label = f"Фотограф: {photographer.studio_name}"

            orders_qs = PhotoOrder.objects.filter(photographer=photographer)
            sessions_qs = PhotoSession.objects.filter(photographer=photographer)
            photos_qs = SessionPhoto.objects.filter(session__photographer=photographer)
            services_qs = Service.objects.filter(photographer=photographer)

    total_earning = orders_qs.aggregate(total=Sum("amount"))["total"] or 0
    total_orders = orders_qs.count()
    total_sessions = sessions_qs.count()
    total_photos = photos_qs.count()

    today = timezone.now().date()
    from_date = today - timedelta(days=30)

    recent_orders = orders_qs.filter(paid_at__date__gte=from_date)
    last_30_days_earning = recent_orders.aggregate(total=Sum("amount"))["total"] or 0

    earning_by_day = (
        recent_orders
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("day")
    )

    top_services = (
        services_qs
        .annotate(order_count=Count("orders"))
        .order_by("-order_count")[:5]
    )

    latest_orders = (
        orders_qs
        .select_related("session", "photographer")
        .order_by("-paid_at")[:10]
    )

    context = {
        "scope_label": scope_label,
        "total_earning": total_earning,
        "total_orders": total_orders,
        "total_sessions": total_sessions,
        "total_photos": total_photos,
        "last_30_days_earning": last_30_days_earning,
        "earning_by_day": earning_by_day,
        "top_services": top_services,
        "latest_orders": latest_orders,
    }
    return render(request, "dashboard.html", context)


@staff_member_required  # только для админов/персонала
def dashboard(request):
    users_active = User.objects.filter(is_active=True).count()
    orders_count = PhotoOrder.objects.count()
    sessions_count = PhotoSession.objects.count()
    photos_count = SessionPhoto.objects.count()

    context = {
        "users_active": users_active,
        "orders_count": orders_count,
        "sessions_count": sessions_count,
        "photos_count": photos_count,
    }
    return render(request, "admin_soft/dashboard.html", context)


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


class MyPhotoOrdersView(generics.ListAPIView):
    """
    GET /api/me/orders/
    Список заказов ТОЛЬКО текущего фотографа.
    """
    serializer_class = PhotoOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PhotoOrder.objects
            .filter(photographer=self.request.user.photographer)
            .order_by("-paid_at")
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
        # фотограф видит ТОЛЬКО свои сессии
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
        # находим сессию ТОЛЬКО этого фотографа
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


# ========== ПОИСК ПО ЛИЦУ (ДЛЯ КЛИЕНТА ПО КОНКРЕТНОЙ СЪЁМКЕ) ==========

class FaceSearchView(APIView):
    """
    POST /api/search-by-face/?view_code=ABCD1234

    Тело: form-data c полем image (фото/селфи).
    Поиск ведём ТОЛЬКО по сессии с этим view_code.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("image")
        view_code = request.query_params.get("view_code")

        if not file:
            return Response({"detail": "Не передано поле 'image'"}, status=400)

        if not view_code:
            return Response({"detail": "Не передан параметр 'view_code'"}, status=400)

        # Находим сессию по view_code (это публичный код для клиентов)
        session = get_object_or_404(PhotoSession, view_code=view_code)

        data = file.read()
        encoding = extract_face_encoding_from_file(ContentFile(data, name=file.name))
        if encoding is None:
            return Response({"detail": "Лицо не найдено на фото"}, status=400)

        # Берём только фото из этой сессии
        photos = SessionPhoto.objects.filter(session=session)
        matches = []
        THRESHOLD = 0.45  # можно подкрутить

        for p in photos:
            if not p.face_encoding:
                continue

            enc2 = list(map(float, p.face_encoding))

            dist = face_distance(encoding, enc2)
            if dist <= THRESHOLD:
                matches.append({
                    "photo_id": p.id,
                    "image_url": (
                        p.watermarked_image.url
                        if p.watermarked_image
                        else p.original_image.url
                    ),
                    "session_id": p.session_id,
                    "client_name": p.session.client_name,
                    "distance": float(dist),
                })

        return Response({"matches": matches})


# ========== ЗАКАЗЫ (после оплаты клиентом) ==========

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


# ========== СПИСОК ФОТО ДЛЯ КЛИЕНТА ПО view_code ==========

class SessionPhotoListView(generics.ListAPIView):
    """
    GET /api/photos/?view_code=ABCD1234

    Возвращает:
    {
      "session": {
          "id": ...,
          "client_name": "...",
          "view_code": "...",
          "download_code": "..."
      },
      "photos": [ ... ]
    }
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

        # если кода нет – вернётся обычный пустой список
        return response


class ServiceListView(generics.ListAPIView):
    """
    GET /api/services/?view_code=ABCD1234

    Отдаёт список услуг фотографа:
    - если передан view_code -> ищем сессию и берём её фотографа
    - можно также передать photographer=<id>, если нужно.
    """
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        view_code = self.request.query_params.get("view_code")
        photographer_id = self.request.query_params.get("photographer")

        qs = Service.objects.filter(is_active=True)

        if view_code:
            session = get_object_or_404(PhotoSession, view_code=view_code)
            qs = qs.filter(photographer=session.photographer)
        elif photographer_id:
            qs = qs.filter(photographer_id=photographer_id)

        return qs
