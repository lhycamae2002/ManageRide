from rest_framework.viewsets import ModelViewSet
from .models import Ride
from .serializers import RideSerializer


class RideViewSet(ModelViewSet):
    queryset = Ride.objects.all()
    serializer_class = RideSerializer