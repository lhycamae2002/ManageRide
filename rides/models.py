from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    id_user = models.AutoField(primary_key=True, db_column='id_user')
    role = models.CharField(max_length=32, default='user')
    phone_number = models.CharField(max_length=32, blank=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'user'


class Ride(models.Model):
    id_ride = models.AutoField(primary_key=True, db_column='id_ride')
    status = models.CharField(max_length=32)
    rider = models.ForeignKey(User, related_name='rides_as_rider', on_delete=models.SET_NULL, null=True, db_column='id_rider')
    driver = models.ForeignKey(User, related_name='rides_as_driver', on_delete=models.SET_NULL, null=True, db_column='id_driver')
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    dropoff_latitude = models.FloatField(null=True, blank=True)
    dropoff_longitude = models.FloatField(null=True, blank=True)
    pickup_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ride'


class RideEvent(models.Model):
    id_ride_event = models.AutoField(primary_key=True, db_column='id_ride_event')
    ride = models.ForeignKey(Ride, related_name='ride_events', on_delete=models.CASCADE, db_column='id_ride')
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'ride_event'
