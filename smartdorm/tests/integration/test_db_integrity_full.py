# from django.test import TestCase
# from django.utils import timezone
# from datetime import timedelta

# from smartdorm.models import Tenant, Room, Rental

# class DatabaseContentTestCase(TestCase):

#     def setUp(self):
#         """
#         This method sets up the initial data in the database 
#         that your tests will use.
#         """
#         # Create a tenant
#         self.tenant = Tenant.objects.create(
#             id=1,
#             birthday=timezone.now().date(),
#             email="test@example.com",
#             external_id="test-id",
#             gender="Male",
#             move_in=timezone.now().date(),
#             move_out=timezone.now().date() + timedelta(days=365),
#             name="Test",
#             nationality="TestNationality",
#             probation_end=timezone.now().date() + timedelta(days=30),
#             study_field="Test Field",
#             surname="Tenant",
#             university="Test University"
#         )

#         # Create a room
#         self.room = Room.objects.create(
#             id=1,
#             external_id="room-test-id",
#             floor="1",
#             house=1,
#             name="Test Room",
#             price=100.00,
#             type="Single",
#             post_row=1
#         )

#         # Create a rental
#         Rental.objects.create(
#             id=1,
#             external_id="rental-test-id",
#             move_in=timezone.now().date(),
#             moved_out=timezone.now().date() + timedelta(days=365),
#             room=self.room,  # Assign the room object
#             tenant=self.tenant  # Assign the tenant object
#         )

#     def test_tenant_count(self):
#         """Check if the correct number of tenants are in the database."""
#         self.assertEqual(Tenant.objects.count(), 1)

#     def test_tenant_data(self):
#         """Check if the tenant's data is correctly stored."""
#         tenant = Tenant.objects.get(id=1)
#         self.assertEqual(tenant.name, "Test")
#         self.assertEqual(tenant.email, "test@example.com")
#         # ... add more assertions for other fields

#     def test_room_exists(self):
#         """Check if the room exists."""
#         room = Room.objects.get(id=1)
#         self.assertEqual(room.name, "Test Room")

#     def test_rental_exists(self):
#         """Check if the rental exists and is linked to the correct tenant."""
#         rental = Rental.objects.get(id=1)
#         self.assertEqual(rental.tenant.id, self.tenant.id)
#         self.assertEqual(rental.room.id, self.room.id)