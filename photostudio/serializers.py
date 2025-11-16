from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Photographer, PhotoSession, SessionPhoto


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
        ]
        read_only_fields = ["view_code", "download_code", "created_at"]


class SessionPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionPhoto
        fields = ["id", "image", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]
