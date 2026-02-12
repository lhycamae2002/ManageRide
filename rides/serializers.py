from rest_framework import serializers
from .models import Ride, RideEvent, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id_user', 'username', 'first_name', 'last_name', 'email', 'role', 'phone_number')


class RideEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideEvent
        fields = ('id_ride_event', 'description', 'created_at')


class RideSerializer(serializers.ModelSerializer):
    rider = UserSerializer(read_only=True)
    driver = UserSerializer(read_only=True)
    todays_ride_events = serializers.SerializerMethodField()

    class Meta:
        model = Ride
        fields = ('id_ride', 'status', 'rider', 'driver', 'pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude', 'pickup_time', 'todays_ride_events')

    def get_todays_ride_events(self, obj):
        # We expect prefetch to set `todays_ride_events` attribute for efficiency
        events = getattr(obj, 'todays_ride_events', None)
        if events is None:
            qs = obj.ride_events.filter(created_at__gte=self.context.get('todays_threshold'))
            return RideEventSerializer(qs, many=True).data
        return RideEventSerializer(events, many=True).data
