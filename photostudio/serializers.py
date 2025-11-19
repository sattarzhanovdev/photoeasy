from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Photographer, PhotoSession, SessionPhoto, PhotoOrder, Service

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    studio_name = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["username", "password", "first_name", "last_name", "studio_name"]

    def create(self, validated_data):
        studio_name = validated_data.pop("studio_name")
        first_name = validated_data.pop("first_name")
        last_name = validated_data.pop("last_name")

        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
        )
        Photographer.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            studio_name=studio_name,
        )
        return user


class PhotographerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Photographer
        fields = ["id", "first_name", "last_name", "studio_name"]


class PhotoSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhotoSession
        fields = [
            "id",
            "client_name",
            "client_phone",
            "view_code",
            "download_code",
            "created_at",
            "date",
            "price",  # стоимость фотосессии
        ]
        read_only_fields = ["view_code", "download_code", "created_at"]


class SessionPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionPhoto
        fields = ["id", "original_image", "watermarked_image", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at", "watermarked_image"]
        # original_image – пишем, watermarked_image – только читаем


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "price"]
class PhotoOrderSerializer(serializers.ModelSerializer):
    photos = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SessionPhoto.objects.all(),
        required=False,
    )
    services = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Service.objects.all(),
        required=False,
    )

    class Meta:
        model = PhotoOrder
        fields = [
            "id",
            "photographer",
            "session",
            "client_name",
            "client_phone",
            "paid_at",
            "amount",
            "photos",
            "services",
            "created_at",
        ]
        read_only_fields = ("photographer", "session", "created_at")

    def create(self, validated_data):
        photos = validated_data.pop("photos", [])
        services = validated_data.pop("services", [])

        order = PhotoOrder.objects.create(**validated_data)

        if photos:
            order.photos.set(photos)
        if services:
            order.services.set(services)

        return order

class SessionPhotoGallerySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    client_name = serializers.CharField(source="session.client_name")

    class Meta:
        model = SessionPhoto
        fields = ["id", "image_url", "client_name"]

    def get_image_url(self, obj):
        # отдаём водяной знак, если есть, иначе оригинал
        if obj.watermarked_image:
            url = obj.watermarked_image.url
        else:
            url = obj.original_image.url

        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url)
        return url