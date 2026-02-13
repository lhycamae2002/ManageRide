from datetime import timedelta

from django.utils import timezone
from django.db.models import F, FloatField, ExpressionWrapper, Prefetch

from rest_framework import viewsets, status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Ride, RideEvent
from .serializers import RideSerializer


class IsAdminRole(BasePermission):
    """Only allow access to users whose role is 'admin'."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'role', None) == 'admin'
        )


class RideViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Ride CRUD operations.

    Supports:
    - Filtering by `status` and `rider__email`
    - Ordering by `pickup_time` and `distance`
      (distance requires `lat` and `lng` query params)
    - Pagination (page number based, default page size 20)
    - Efficient prefetching of today's ride events (last 24h)
    """

    serializer_class = RideSerializer
    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'rider__email']
    ordering_fields = ['pickup_time', 'distance']

    def _get_todays_threshold(self):
        """Return the datetime threshold for 'today's' events (last 24h)."""
        return timezone.now() - timedelta(hours=24)

    def get_queryset(self):
        qs = Ride.objects.select_related('rider', 'driver')

        # Prefetch only ride events from the last 24 hours to avoid
        # scanning the full (potentially very large) RideEvent table.
        threshold = self._get_todays_threshold()
        recent_events_qs = RideEvent.objects.filter(
            created_at__gte=threshold,
        ).only('id_ride_event', 'description', 'created_at', 'ride_id')

        qs = qs.prefetch_related(
            Prefetch(
                'ride_events',
                queryset=recent_events_qs,
                to_attr='todays_ride_events',
            )
        )

        # Annotate with approximate planar distance when lat/lng provided.
        # This allows efficient DB-level sorting by distance with pagination.
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        if lat is not None and lng is not None:
            try:
                lat_f = float(lat)
                lng_f = float(lng)
            except (ValueError, TypeError):
                pass
            else:
                lat_diff = ExpressionWrapper(
                    (F('pickup_latitude') - lat_f) * (F('pickup_latitude') - lat_f),
                    output_field=FloatField(),
                )
                lng_diff = ExpressionWrapper(
                    (F('pickup_longitude') - lng_f) * (F('pickup_longitude') - lng_f),
                    output_field=FloatField(),
                )
                qs = qs.annotate(distance=lat_diff + lng_diff)

        return qs.order_by('id_ride')

    def list(self, request, *args, **kwargs):
        # Validate: if ordering=distance is requested, lat/lng must be present
        ordering = request.query_params.get('ordering', '')
        if 'distance' in ordering:
            lat = request.query_params.get('lat')
            lng = request.query_params.get('lng')
            if lat is None or lng is None:
                return Response(
                    {
                        'error': (
                            'Sorting by distance requires both "lat" and "lng" '
                            'query parameters.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                float(lat)
                float(lng)
            except (ValueError, TypeError):
                return Response(
                    {'error': '"lat" and "lng" must be valid numeric values.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        queryset = self.filter_queryset(self.get_queryset())
        threshold = self._get_todays_threshold()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(
                page, many=True, context={'todays_threshold': threshold},
            )
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(
            queryset, many=True, context={'todays_threshold': threshold},
        )
        return Response(serializer.data)