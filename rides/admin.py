from django.contrib import admin
from .models import User, Ride, RideEvent


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id_user', 'username', 'email', 'role')


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = ('id_ride', 'status', 'rider', 'driver', 'pickup_time')
    list_filter = ('status',)


@admin.register(RideEvent)
class RideEventAdmin(admin.ModelAdmin):
    list_display = ('id_ride_event', 'ride', 'description', 'created_at')
