from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    RegisterView,
    login_view,
    PhotoSessionViewSet,
    SessionPhotoBulkUploadView,
    FaceSearchView,
    PhotoOrderCreateView,
    SessionPhotoListView, 
    ServiceListView, 
    dashboard_view, 
    dashboard_export_xlsx
)

router = DefaultRouter()
router.register(r"sessions", PhotoSessionViewSet, basename="session")

urlpatterns = [
    # auth
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", login_view, name="login"),

    # личный кабинет фотографа
    path("dashboard/", dashboard_view, name="dashboard"),
    path("dashboard/export/", dashboard_export_xlsx, name="dashboard_export"),

    # массовая загрузка фото
    path(
        "sessions/<int:session_id>/photos/bulk-upload/",
        SessionPhotoBulkUploadView.as_view(),
        name="session-photo-bulk-upload",
    ),
    
    path("services/", ServiceListView.as_view(), name="service-list"),

    # поиск по лицу
    path("search-by-face/", FaceSearchView.as_view(), name="face-search"),

    # заказ после оплаты
    path("orders/", PhotoOrderCreateView.as_view(), name="orders-create"),
    path("photos/", SessionPhotoListView.as_view(), name="photos-list"),

]
