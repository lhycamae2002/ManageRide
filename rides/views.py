from datetime import timedelta, datetime
from django.utils import timezone
from django.db.models import Prefetch, F, ExpressionWrapper, FloatField
from rest_framework import viewsets
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .models import Ride, RideEvent
from .serializers import RideSerializer, RideEventSerializer


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, 'role', None) == 'admin')


class RideViewSet(viewsets.ModelViewSet):
    serializer_class = RideSerializer
    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'rider__email']
    ordering_fields = ['pickup_time', 'distance']

    def get_queryset(self):
        qs = Ride.objects.select_related('rider', 'driver')

        # prepare prefetch for ride events in last 24 hours
        now = timezone.now()
        threshold = now - timedelta(hours=24)

        recent_events_qs = RideEvent.objects.filter(created_at__gte=threshold).only('id_ride_event', 'description', 'created_at')
        qs = qs.prefetch_related(Prefetch('ride_events', queryset=recent_events_qs, to_attr='todays_ride_events'))

        # sorting by distance when lat & lng provided (approximate planar distance for speed)
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        if lat is not None and lng is not None:
            try:
                lat_f = float(lat)
                lng_f = float(lng)
                # approximate squared distance expression
                lat_diff = ExpressionWrapper((F('pickup_latitude') - lat_f) * (F('pickup_latitude') - lat_f), output_field=FloatField())
                lng_diff = ExpressionWrapper((F('pickup_longitude') - lng_f) * (F('pickup_longitude') - lng_f), output_field=FloatField())
                qs = qs.annotate(distance=lat_diff + lng_diff)
            except ValueError:
                pass

        # apply ordering from query params automatically via OrderingFilter
        # default ordering by id_ride to ensure consistent pagination
        return qs.order_by('id_ride')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        now = timezone.now()
        threshold = now - timedelta(hours=24)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'todays_threshold': threshold})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context={'todays_threshold': threshold})
        return Response(serializer.data)
