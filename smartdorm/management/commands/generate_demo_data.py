import sys
import random
from datetime import timedelta, date
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db import transaction
from smartdorm.models import (
    Tenant, Room, Rental, Department, Engagement, EngagementApplication,
    Departure, DepartmentSignature, Parcel, Subtenant, Claim, Termination,
    DepartmentExtension, GlobalAppSettings, DepositBank
)
from faker import Faker

class Command(BaseCommand):
    help = 'Generates comprehensive dummy data for the SmartDorm demo environment'

    def handle(self, *args, **options):
        if 'demo' not in sys.modules and not Tenant.objects.exists() and False:
            pass
            
        fake = Faker('de_DE')
        self.stdout.write('Clearing old data...')

        with transaction.atomic():
            DepositBank.objects.all().delete()
            Termination.objects.all().delete()
            DepartmentExtension.objects.all().delete()
            Claim.objects.all().delete()
            Subtenant.objects.all().delete()
            Parcel.objects.all().delete()
            DepartmentSignature.objects.all().delete()
            Departure.objects.all().delete()
            EngagementApplication.objects.all().delete()
            Engagement.objects.all().delete()
            Rental.objects.all().delete()
            Tenant.objects.all().delete()
            Room.objects.all().delete()
            Department.objects.all().delete()
            
            # Rooms (400 rooms)
            self.stdout.write('Generating Rooms...')
            rooms = []
            for i in range(1, 401):
                floor = f"Floor {((i - 1) // 20) + 1}"
                room = Room(
                    id=i, 
                    external_id=f"RM-{i}", 
                    floor=floor, 
                    house=1, 
                    name=f"{((i - 1) // 20) + 1}{str((i - 1) % 20 + 1).zfill(2)}", 
                    price=300.00 + random.randint(0, 50), 
                    type=random.choice(["Single", "Double"]), 
                    post_row=i
                )
                rooms.append(room)
            Room.objects.bulk_create(rooms)

            # Departments
            self.stdout.write('Generating Departments...')
            departments = []
            dept_names = ["Heimrat", "Netzwerkreferat", "Inforeferat", "Zimmerreferat", "Finanzenreferat", "Schlichtungsreferat"]
            for i, d_name in enumerate(dept_names):
                dept = Department(
                    id=i+1, 
                    full_name=f"{d_name} Department", 
                    name=d_name, 
                    points=float(random.randint(1, 3)), 
                    size=random.randint(3, 10)
                )
                departments.append(dept)
            Department.objects.bulk_create(departments)

            # Tenants
            self.stdout.write('Generating 600 Tenants...')
            tenants = []
            today = timezone.now().date()
            tenant_id = 1
            
            # Sub-lists to speed up queries / distributions later
            current_tenants = []
            past_tenants = []
            
            for is_current in [False, True]:
                count = 300
                for _ in range(count):
                    if is_current:
                        move_in = fake.date_between(start_date='-2y', end_date=today - timedelta(days=1))
                        move_out = fake.date_between(start_date=today + timedelta(days=30), end_date=today + timedelta(days=365))
                    else:
                        move_in = fake.date_between(start_date='-4y', end_date='-2y')
                        move_out = fake.date_between(start_date=move_in + timedelta(days=180), end_date=today - timedelta(days=1))

                    probation = move_in + timedelta(days=180)
                    room = random.choice(rooms)
                    
                    t = Tenant(
                        id=tenant_id,
                        birthday=fake.date_of_birth(minimum_age=18, maximum_age=30),
                        current_floor=room.floor if is_current else None,
                        current_points=random.randint(0, 15),
                        current_room=room.name if is_current else None,
                        deposit=random.choice([300.00, 500.00, 600.00]),
                        email=fake.email(),
                        extension=random.randint(0, 3),
                        external_id=f"EXT-T-{tenant_id}",
                        gender=random.choice(["Male", "Female", "Other"]),
                        move_in=move_in,
                        move_out=move_out,
                        name=fake.first_name(),
                        surname=fake.last_name(),
                        nationality=fake.country(),
                        note="Mock User" if random.random() < 0.1 else None,
                        probation_end=probation,
                        study_field=random.choice(["Computer Science", "Physics", "Mathematics", "Biology", "Chemistry", "Economics"]),
                        sublet=0.0,
                        tel_number=fake.phone_number()[:20],
                        university=random.choice(["LMU", "TUM", "HM"]),
                        username=f"tenant{tenant_id}",
                        new_address=fake.address()[:200] if not is_current else None
                    )
                    tenants.append(t)
                    if is_current:
                        current_tenants.append(t)
                    else:
                        past_tenants.append(t)
                    tenant_id += 1
                    
            Tenant.objects.bulk_create(tenants)
            
            # Rentals
            self.stdout.write('Generating Rentals...')
            rentals = []
            rental_id = 1
            for t in tenants:
                if t in current_tenants:
                    room = next((r for r in rooms if r.name == t.current_room), rooms[0])
                else:
                    room = random.choice(rooms)

                rentals.append(Rental(
                    id=rental_id,
                    external_id=f"RNT-{rental_id}",
                    move_in=t.move_in,
                    moved_out=t.move_out,
                    room=room,
                    tenant=t
                ))
                rental_id += 1
                
                # Ensure some have past rentals
                if random.random() < 0.2:
                    past_room = random.choice(rooms)
                    past_move_in = t.move_in - timedelta(days=360)
                    past_move_out = t.move_in - timedelta(days=1)
                    rentals.append(Rental(
                        id=rental_id,
                        external_id=f"RNT-{rental_id}",
                        move_in=past_move_in,
                        moved_out=past_move_out,
                        room=past_room,
                        tenant=t
                    ))
                    rental_id += 1
            Rental.objects.bulk_create(rentals)

            # Deposit Banks
            self.stdout.write('Generating DepositBank infos...')
            deposit_banks = []
            for t in tenants:
                if random.random() < 0.8: # 80% have a deposit bank added
                    deposit_banks.append(DepositBank(
                        tenant=t,
                        name=fake.company()[:255],
                        iban=fake.iban()[:255]
                    ))
            DepositBank.objects.bulk_create(deposit_banks)

            # Engagements & Applications
            self.stdout.write('Generating Engagements...')
            engagements = []
            applications = []
            eng_id = 1
            app_id = 1
            for t in tenants:
                if random.random() < 0.4:
                    for _ in range(random.randint(1, 4)):
                        d = random.choice(departments)
                        engagements.append(Engagement(
                            id=eng_id,
                            compensate=random.choice([True, False]),
                            external_id=f"ENG-{eng_id}",
                            note=fake.sentence()[:255],
                            points=d.points,
                            semester=random.choice(["WS23/24", "SS24", "WS24/25", "SS25"]),
                            department=d,
                            tenant=t
                        ))
                        eng_id += 1
                if t in current_tenants and random.random() < 0.15:
                    d = random.choice(departments)
                    applications.append(EngagementApplication(
                        id=app_id,
                        semester="WS25/26",
                        motivation=fake.text(),
                        external_id=f"APP-{app_id}",
                        department=d,
                        tenant=t
                    ))
                    app_id += 1
            Engagement.objects.bulk_create(engagements)
            EngagementApplication.objects.bulk_create(applications)

            # Extensions & Claims
            self.stdout.write('Generating Extensions and Claims...')
            extensions = []
            claims = []
            claim_id = 1
            for t in tenants:
                if random.random() < 0.2:
                    extensions.append(DepartmentExtension(
                        tenant=t,
                        months=random.choice([1, 2, 6]),
                        note="Good engagement"
                    ))
                if random.random() < 0.2:
                    claims.append(Claim(
                        id=claim_id,
                        created_on=t.move_in + timedelta(days=30),
                        external_id=f"CLM-{claim_id}",
                        status=random.choice(Claim.Status.choices)[0],
                        type=random.choice(Claim.Type.choices)[0],
                        tenant=t
                    ))
                    claim_id += 1
            DepartmentExtension.objects.bulk_create(extensions)
            Claim.objects.bulk_create(claims)

            # Subtenants
            self.stdout.write('Generating Subtenants...')
            subtenants = []
            subtenant_id = 1
            for t in tenants:
                if random.random() < 0.15:
                    rnt = next((r for r in rentals if r.tenant == t), None)
                    if rnt:
                        s_move_in = t.move_in + timedelta(days=random.randint(10, 30))
                        if s_move_in < t.move_out:
                            s_move_out = min(s_move_in + timedelta(days=random.randint(30, 90)), t.move_out - timedelta(days=1))
                            if s_move_out > s_move_in:
                                duration = (s_move_out - s_move_in).days / 30.0
                                subtenants.append(Subtenant(
                                    id=subtenant_id,
                                    created_on=t.move_in + timedelta(days=5),
                                    external_id=f"SUB-{subtenant_id}",
                                    move_in=s_move_in,
                                    move_out=s_move_out,
                                    duration=round(duration, 1),
                                    university_confirmation=True,
                                    room=rnt.room,
                                    tenant=t,
                                    name=fake.first_name()[:255],
                                    surname=fake.last_name()[:255],
                                    email=fake.email()[:255]
                                ))
                                subtenant_id += 1
            Subtenant.objects.bulk_create(subtenants)

            # Terminations & Departures & Parcels
            self.stdout.write('Generating Terminations, Departures & Parcels...')
            terminations = []
            departures = []
            signatures = []
            parcels = []
            parcel_id = 1
            sig_id = 1
            
            for t in tenants:
                if random.random() < 0.1:
                    terminations.append(Termination(
                        tenant=t,
                        date=t.move_out,
                        note="Regular termination request"
                    ))
                
                # Create a departure exactly once for past tenants and sometimes for current tenants near moving out
                if t in past_tenants or (t in current_tenants and t.move_out <= today + timedelta(days=60) and random.random() > 0.3):
                    # Pick a status depending on whether its already past move_out
                    if t.move_out < today:
                        status = Departure.Status.CLOSED
                    else:
                        status = random.choice([Departure.Status.CREATED, Departure.Status.CONFIRMED, Departure.Status.POSTPONED])
                        
                    dep = Departure(
                        tenant=t,
                        created_on=t.move_out - timedelta(days=30),
                        external_id=f"DEP-{t.id}",
                        status=status
                    )
                    departures.append(dep)
                    
                    if dep.status in [Departure.Status.CLOSED, Departure.Status.CONFIRMED]:
                        signatures.append(DepartmentSignature(
                            id=sig_id,
                            amount=random.choice([0, 0, 0, 50, 20]),
                            department_name=random.choice(["Heimrat", "Verwaltung"]),
                            external_id=f"SIG-{sig_id}",
                            signed_on=dep.created_on + timedelta(days=10),
                            departure=dep
                        ))
                        sig_id += 1
                        signatures.append(DepartmentSignature(
                            id=sig_id,
                            amount=0,
                            department_name="Netzwerkreferat",
                            external_id=f"SIG-{sig_id}",
                            signed_on=dep.created_on + timedelta(days=15),
                            departure=dep
                        ))
                        sig_id += 1
                        
                # Parcels
                if random.random() < 0.4:
                    for _ in range(random.randint(1, 5)):
                        is_picked_up = random.random() > 0.2
                        parcels.append(Parcel(
                            id=parcel_id,
                            arrived=timezone.now() - timedelta(days=random.randint(1, 30)),
                            count=random.randint(1, 3),
                            external_id=f"PAR-{parcel_id}",
                            picked_up=timezone.now() - timedelta(days=random.randint(0, 1)) if is_picked_up else None,
                            registered=True,
                            tenant=t
                        ))
                        parcel_id += 1
                    
            Termination.objects.bulk_create(terminations)
            Departure.objects.bulk_create(departures)
            DepartmentSignature.objects.bulk_create(signatures)
            Parcel.objects.bulk_create(parcels)

            self.stdout.write(self.style.SUCCESS('Successfully generated highly comprehensive fake data (600 tenants)!'))
