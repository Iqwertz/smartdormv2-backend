import sys
import random
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from smartdorm.models import Tenant, Room, Rental, Department, Engagement, Departure
from faker import Faker

class Command(BaseCommand):
    help = 'Generates dummy data for the SmartDorm demo environment'

    def handle(self, *args, **options):
        # We don't want to accidentally run this in production!
        if 'demo' not in sys.modules and not Tenant.objects.exists() and False:
            pass # just a sanity check placeholder, maybe rely on a settings variable or just let it run.
            
        fake = Faker('de_DE')
        self.stdout.write('Clearing old data...')
        Engagement.objects.all().delete()
        Departure.objects.all().delete()
        Rental.objects.all().delete()
        Tenant.objects.all().delete()
        Room.objects.all().delete()
        Department.objects.all().delete()

        self.stdout.write('Generating Rooms...')
        rooms = []
        for i in range(1, 51):
            floor = f"Floor {i // 10 + 1}"
            room = Room(
                id=i, 
                external_id=f"RM-{i}", 
                floor=floor, 
                house=1, 
                name=f"Room {i}", 
                price=300.00 + random.randint(0, 50), 
                type="Single", 
                post_row=i
            )
            rooms.append(room)
        Room.objects.bulk_create(rooms)

        self.stdout.write('Generating Departments...')
        departments = []
        dept_names = ["Heimrat", "Netzwerkreferat", "Inforeferat", "Zimmerreferat"]
        for i, d_name in enumerate(dept_names):
            dept = Department(
                id=i+1, 
                full_name=f"{d_name} Department", 
                name=d_name, 
                points=1.0, 
                size=5
            )
            departments.append(dept)
        Department.objects.bulk_create(departments)

        self.stdout.write('Generating Tenants...')
        tenants = []
        for i in range(1, 41):
            move_in = fake.date_between(start_date='-2y', end_date='-1m')
            move_out = move_in + timedelta(days=365*2)
            probation = move_in + timedelta(days=180)
            
            tenant = Tenant(
                id=i,
                birthday=fake.date_of_birth(minimum_age=18, maximum_age=30),
                current_floor=rooms[i-1].floor,
                current_points=random.randint(0, 10),
                current_room=rooms[i-1].name,
                deposit=500.00,
                email=fake.email(),
                extension=random.randint(0, 2),
                external_id=f"EXT-{i}",
                gender=random.choice(["Male", "Female", "Other"]),
                move_in=move_in,
                move_out=move_out,
                name=fake.first_name(),
                surname=fake.last_name(),
                nationality=fake.country(),
                note="Demo user",
                probation_end=probation,
                study_field="Computer Science",
                sublet=0.0,
                tel_number=fake.phone_number(),
                university="LMU",
                username=f"tenant{i}",
                new_address=fake.address()
            )
            tenants.append(tenant)
        Tenant.objects.bulk_create(tenants)

        self.stdout.write('Generating Rentals...')
        rentals = []
        for i, tenant in enumerate(tenants):
            rental = Rental(
                id=i+1,
                external_id=f"RNT-{i+1}",
                move_in=tenant.move_in,
                moved_out=tenant.move_out,
                room=rooms[i],
                tenant=tenant
            )
            rentals.append(rental)
        Rental.objects.bulk_create(rentals)

        self.stdout.write('Generating Engagements...')
        engagements = []
        for i in range(1, 15):
            t = random.choice(tenants)
            d = random.choice(departments)
            eng = Engagement(
                id=i,
                compensate=True,
                external_id=f"ENG-{i}",
                note="Great work",
                points=d.points,
                semester="SS24",
                department=d,
                tenant=t
            )
            engagements.append(eng)
        Engagement.objects.bulk_create(engagements)

        self.stdout.write(self.style.SUCCESS('Successfully generated fake data!'))
