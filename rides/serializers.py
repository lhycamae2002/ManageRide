from rest_framework import serializers
from .models import Ride, RideEvent, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id_user', 'username', 'first_name', 'last_name',
            'email', 'role', 'phone_number',
        )


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
        fields = (
            'id_ride', 'status', 'rider', 'driver',
            'pickup_latitude', 'pickup_longitude',
            'dropoff_latitude', 'dropoff_longitude',
            'pickup_time', 'todays_ride_events',
        )

    def get_todays_ride_events(self, obj):
        """
        Return only RideEvents from the last 24 hours.
        Uses prefetched `todays_ride_events` attribute set via Prefetch
        to avoid extra queries. Falls back to a filtered queryset if
        the attribute is not present (e.g. detail view).
        """
        events = getattr(obj, 'todays_ride_events', None)
        if events is None:
            threshold = self.context.get('todays_threshold')
            if threshold is None:
                return []
            qs = obj.ride_events.filter(created_at__gte=threshold)
            return RideEventSerializer(qs, many=True).data
        return RideEventSerializer(events, many=True).data