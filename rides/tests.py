from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework.test import APIClient

from .models import User, Ride, RideEvent


class RidesAPITest(TestCase):
    def setUp(self):
        # Create users
        self.admin = User.objects.create_user(
            username='admin', password='pass',
            email='admin@example.com', role='admin',
        )
        self.rider = User.objects.create_user(
            username='rider', password='pass',
            email='rider@example.com',
        )
        self.driver = User.objects.create_user(
            username='driver', password='pass',
            email='driver@example.com',
        )

        now = timezone.now()

        # Create rides: one near origin, one farther
        self.ride_near = Ride.objects.create(
            status='en-route', rider=self.rider, driver=self.driver,
            pickup_latitude=0.0, pickup_longitude=0.0,
            pickup_time=now - timedelta(minutes=30),
        )

        self.ride_far = Ride.objects.create(
            status='pickup', rider=self.rider, driver=self.driver,
            pickup_latitude=10.0, pickup_longitude=10.0,
            pickup_time=now - timedelta(hours=2),
        )

        # Events: recent and old for ride_near; only old for ride_far
        RideEvent.objects.create(
            ride=self.ride_near,
            description='Status changed to pickup',
        )
        # Manually set created_at for the "old" events since auto_now_add
        # prevents setting it at creation time.
        old_event_near = RideEvent.objects.create(
            ride=self.ride_near,
            description='Some old event',
        )
        RideEvent.objects.filter(pk=old_event_near.pk).update(
            created_at=now - timedelta(days=2),
        )

        old_event_far = RideEvent.objects.create(
            ride=self.ride_far,
            description='Status changed to pickup',
        )
        RideEvent.objects.filter(pk=old_event_far.pk).update(
            created_at=now - timedelta(days=3),
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _get_results(self, resp):
        self.assertEqual(resp.status_code, 200)
        return resp.data.get('results', resp.data)

    # ── Core functionality ──────────────────────────────────────────

    def test_list_returns_todays_events_only(self):
        """Only RideEvents from the last 24 hours should be included."""
        resp = self.client.get('/api/rides/')
        results = self._get_results(resp)

        found = next(
            (r for r in results if r['id_ride'] == self.ride_near.id_ride),
            None,
        )
        self.assertIsNotNone(found)

        events = found.get('todays_ride_events', [])
        descriptions = [e['description'] for e in events]
        self.assertIn('Status changed to pickup', descriptions)
        self.assertNotIn('Some old event', descriptions)

    def test_list_returns_empty_events_for_old_rides(self):
        """Rides with only old events should have empty todays_ride_events."""
        resp = self.client.get('/api/rides/')
        results = self._get_results(resp)

        found = next(
            (r for r in results if r['id_ride'] == self.ride_far.id_ride),
            None,
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.get('todays_ride_events', []), [])

    # ── Filtering ───────────────────────────────────────────────────

    def test_filter_by_status(self):
        resp = self.client.get('/api/rides/?status=pickup')
        results = self._get_results(resp)
        self.assertTrue(all(r['status'] == 'pickup' for r in results))
        self.assertTrue(len(results) > 0)

    def test_filter_by_rider_email(self):
        resp = self.client.get('/api/rides/?rider__email=rider@example.com')
        results = self._get_results(resp)
        self.assertTrue(len(results) > 0)
        for r in results:
            self.assertEqual(r['rider']['email'], 'rider@example.com')

    # ── Ordering ────────────────────────────────────────────────────

    def test_ordering_by_pickup_time(self):
        resp = self.client.get('/api/rides/?ordering=pickup_time')
        results = self._get_results(resp)
        self.assertTrue(len(results) >= 2)
        self.assertLessEqual(
            results[0]['pickup_time'], results[1]['pickup_time'],
        )

    def test_ordering_by_distance(self):
        resp = self.client.get('/api/rides/?ordering=distance&lat=0&lng=0')
        results = self._get_results(resp)
        # Nearest to (0,0) should be ride_near
        if len(results) >= 1:
            self.assertEqual(results[0]['id_ride'], self.ride_near.id_ride)

    def test_ordering_by_distance_without_lat_lng_returns_400(self):
        """Requesting distance sort without lat/lng should return 400."""
        resp = self.client.get('/api/rides/?ordering=distance')
        self.assertEqual(resp.status_code, 400)

    def test_ordering_by_distance_with_invalid_lat_lng_returns_400(self):
        """Non-numeric lat/lng should return 400."""
        resp = self.client.get('/api/rides/?ordering=distance&lat=abc&lng=xyz')
        self.assertEqual(resp.status_code, 400)

    # ── Authentication / Permissions ────────────────────────────────

    def test_unauthenticated_user_denied(self):
        client = APIClient()
        resp = client.get('/api/rides/')
        self.assertIn(resp.status_code, [401, 403])

    def test_non_admin_user_denied(self):
        client = APIClient()
        client.force_authenticate(user=self.rider)
        resp = client.get('/api/rides/')
        self.assertEqual(resp.status_code, 403)

    # ── Performance ─────────────────────────────────────────────────

    def test_minimal_number_of_queries_for_list(self):
        """
        The ride list should be fetchable in at most 3 queries:
        1. COUNT query for pagination
        2. SELECT rides with JOIN on rider and driver (select_related)
        3. SELECT recent ride events (prefetch_related)
        """
        with CaptureQueriesContext(connection) as captured:
            resp = self.client.get('/api/rides/')
            self.assertEqual(resp.status_code, 200)

        # 3 queries: count + rides (with select_related) + prefetch events
        self.assertLessEqual(
            len(captured), 3,
            f"Expected at most 3 queries, got {len(captured)}:\n"
            + "\n".join(q['sql'] for q in captured),
        )