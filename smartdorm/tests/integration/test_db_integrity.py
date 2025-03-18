from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from smartdorm.models import Tenant, Room, Rental

class DatabaseContentTestCase(TestCase):

    def setUp(self):
        """
        This method sets up the initial data in the database 
        that your tests will use.
        """
        # Create a tenant
        self.tenant = Tenant.objects.create(
            id=1,
            birthday=timezone.now().date(),
            email="test@example.com",
            external_id="test-id",
            gender="Male",
            move_in=timezone.now().date(),
            move_out=timezone.now().date() + timedelta(days=365),
            name="Test",
            nationality="TestNationality",
            probation_end=timezone.now().date() + timedelta(days=30),
            study_field="Test Field",
            surname="Tenant",
            university="Test University"
        )


    def test_tenant_count(self):
        """Check if the correct number of tenants are in the database."""
        self.assertEqual(Tenant.objects.count(), 1)