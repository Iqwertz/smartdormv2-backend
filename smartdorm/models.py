from django.db import models
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__) 
class Tenant(models.Model):
    id = models.IntegerField(primary_key=True)
    birthday = models.DateField()
    current_floor = models.CharField(max_length=255, null=True, blank=True)
    current_points = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    current_room = models.CharField(max_length=255, null=True, blank=True)
    deposit = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    email = models.CharField(max_length=255)
    extension = models.IntegerField(null=True, blank=True)
    external_id = models.CharField(max_length=255)
    gender = models.CharField(max_length=255)
    move_in = models.DateField()
    move_out = models.DateField()
    name = models.CharField(max_length=255)
    nationality = models.CharField(max_length=255)
    note = models.CharField(max_length=255, null=True, blank=True)
    probation_end = models.DateField()
    study_field = models.CharField(max_length=255)
    sublet = models.FloatField(null=True, blank=True)
    surname = models.CharField(max_length=255)
    tel_number = models.CharField(max_length=255, null=True, blank=True)
    university = models.CharField(max_length=255)
    username = models.CharField(max_length=255, null=True, blank=True)
    new_address = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 't_tenant'
        managed = False
        
    def get_full_name(self):
        """Returns the person's full name."""
        return f"{self.name} {self.surname}"

# Example queries using tenants model
def get_active_tenants():
    return Tenant.objects.filter(
        move_in__lte=timezone.now().date(),
        move_out__gte=timezone.now().date()
    )

def get_tenants_by_university(university_name):
    return Tenant.objects.filter(university=university_name)

def get_tenants_by_floor(floor):
    return Tenant.objects.filter(current_floor=floor)

def get_tenant_details(tenant_id):
    return Tenant.objects.filter(id=tenant_id).values(
        'name', 'surname', 'email', 'current_room', 
        'university', 'study_field', 'nationality'
    ).first()

def get_expiring_probations(days_threshold=30):
    threshold_date = timezone.now().date() + timedelta(days=days_threshold)
    return Tenant.objects.filter(
        probation_end__lte=threshold_date,
        move_out__gte=timezone.now().date()
    ).order_by('probation_end')

class Room(models.Model):
    id = models.IntegerField(primary_key=True)
    external_id = models.CharField(max_length=255)
    floor = models.CharField(max_length=255)
    house = models.IntegerField()
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=19, decimal_places=2)
    type = models.CharField(max_length=255)
    post_row = models.IntegerField()

    class Meta:
        db_table = 't_room'
        managed = False

class Rental(models.Model):
    id = models.IntegerField(primary_key=True)
    external_id = models.CharField(max_length=255)
    move_in = models.DateField()
    moved_out = models.DateField()
    room = models.ForeignKey(Room, on_delete=models.DO_NOTHING, db_column='room_id')
    tenant = models.ForeignKey('Tenant', on_delete=models.DO_NOTHING, db_column='tenant_id')

    class Meta:
        db_table = 't_rental'
        managed = False

class Department(models.Model):
    id = models.IntegerField(primary_key=True)
    full_name = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    points = models.DecimalField(max_digits=19, decimal_places=2)
    size = models.IntegerField()

    class Meta:
        db_table = 't_department'
        managed = False

class Engagement(models.Model):
    id = models.IntegerField(primary_key=True)
    compensate = models.BooleanField()
    external_id = models.CharField(max_length=255)
    note = models.CharField(max_length=255, null=True, blank=True)
    points = models.DecimalField(max_digits=19, decimal_places=2)
    semester = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.DO_NOTHING, db_column='department_id')
    tenant = models.ForeignKey('Tenant', on_delete=models.DO_NOTHING, db_column='tenant_id')

    class Meta:
        db_table = 't_engagement'
        managed = False

class EngagementApplication(models.Model):
    id = models.IntegerField(primary_key=True)
    semester = models.CharField(max_length=255)
    motivation = models.TextField()
    external_id = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.DO_NOTHING, db_column='department_id')
    tenant = models.ForeignKey('Tenant', on_delete=models.DO_NOTHING, db_column='tenant_id')
    image_name = models.CharField(max_length=255, null=True, blank=True)
    image = models.BinaryField(null=True, blank=True)

    class Meta:
        db_table = 't_engagement_application'
        managed = False

class Departure(models.Model):
    class Status(models.TextChoices):
        CREATED = 'CREATED', 'Erstellt'
        POSTPONED = 'POSTPONED', 'Verlängert'
        CONFIRMED = 'CONFIRMED', 'Bestätigt'
        CLOSED = 'CLOSED', 'Abgeschlossen'
    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.DO_NOTHING, db_column='tenant_id')
    created_on = models.DateField()
    external_id = models.CharField(max_length=255)
    status = models.CharField(max_length=255, choices=Status.choices, default=Status.CREATED) # 'POSTPONED', 'CREATED', 'CLOSED', 'CONFIRMED'

    class Meta:
        db_table = 't_departure'
        managed = False

class DepartmentSignature(models.Model):
    id = models.IntegerField(primary_key=True)
    amount = models.DecimalField(max_digits=19, decimal_places=2)
    department_name = models.CharField(max_length=30)
    external_id = models.CharField(max_length=255)
    signed_on = models.DateField()
    departure = models.ForeignKey(Departure, on_delete=models.DO_NOTHING, db_column='departure_id')

    class Meta:
        db_table = 't_department_signature'
        managed = False

class Parcel(models.Model):
    id = models.IntegerField(primary_key=True)
    arrived = models.DateTimeField()  # Django will handle timezone automatically
    count = models.IntegerField()
    external_id = models.CharField(max_length=255)
    picked_up = models.DateTimeField(null=True, blank=True)
    registered = models.BooleanField()
    tenant = models.ForeignKey('Tenant', null=True, blank=True, on_delete=models.DO_NOTHING, db_column='tenant_id')
    subtenant = models.ForeignKey('Subtenant', null=True, blank=True, on_delete=models.DO_NOTHING, db_column='subtenant_id')

    class Meta:
        db_table = 't_parcel'
        managed = False
        
class Subtenant(models.Model):
    id = models.IntegerField(primary_key=True)
    created_on = models.DateField()
    external_id = models.CharField(max_length=255)
    move_in = models.DateField(db_column='move_id') # Note: 'move_id' is a typo in the original db, should have been 'move_in' but is kept for compatibility
    move_out = models.DateField()
    university_confirmation = models.BooleanField()
    room = models.ForeignKey(Room, on_delete=models.DO_NOTHING, db_column='room_id')
    tenant = models.ForeignKey('Tenant', on_delete=models.DO_NOTHING, db_column='tenant_id')
    name = models.CharField(max_length=255)
    surname = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    duration = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 't_subtenant'
        managed = False

class User(models.Model):
    id = models.IntegerField(primary_key=True)
    password = models.CharField(max_length=255)
    username = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 't_user'
        managed = False

class DepositBank(models.Model):
    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.DO_NOTHING, db_column='tenant_id')
    name = models.CharField(max_length=255)
    iban = models.CharField(max_length=255)

    class Meta:
        db_table = 't_deposit_bank'
        managed = False

class Claim(models.Model):
    id = models.IntegerField(primary_key=True)
    created_on = models.DateField()
    external_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20)
    type = models.CharField(max_length=20)
    tenant = models.ForeignKey('Tenant', on_delete=models.DO_NOTHING, db_column='tenant_id')

    class Meta:
        db_table = 't_claim'
        managed = False

class OfflineUser(models.Model):
    id = models.IntegerField(primary_key=True)
    email = models.TextField()
    password = models.TextField()
    permissions = models.IntegerField()

    class Meta:
        db_table = 'offline_user'
        managed = False

class OfflineUserPermissions(models.Model):
    id = models.IntegerField(primary_key=True)
    offline_user = models.ForeignKey(OfflineUser, on_delete=models.DO_NOTHING, db_column='offline_user_id', null=True)
    permissions = models.TextField()

    class Meta:
        db_table = 'offline_user_permissions'
        managed = False
        
class GlobalAppSettings(models.Model):
    # Singleton model: there should only be one instance of this model.
    id = models.PositiveIntegerField(primary_key=True, default=1, editable=False)
    current_semester = models.CharField(
        max_length=50,
        default="SS25",
        help_text="Current academic semester (e.g., WS24/25, SS25)"
    )
    applications_open = models.BooleanField(
        default=False,
        help_text="Are new applications currently being accepted?"
    )
    # Example of another setting:
    # site_maintenance_mode = models.BooleanField(default=False, help_text="Is the site in maintenance mode?")

    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp of the last update to settings.")

    class Meta:
        verbose_name = "Global App Setting"
        verbose_name_plural = "Global App Settings"
        db_table = 't_global_app_settings'

    def __str__(self):
        return "Global Application Settings"

    def save(self, *args, **kwargs):
        # Enforce singleton: only allow saving if ID is 1
        if self.id != 1:
            logger.warning(f"Attempt to create a new GlobalAppSettings instance with id={self.id} was blocked.")
            #raise ValidationError("Cannot create new GlobalAppSettings. Only one instance with id=1 is allowed.")
        super().save(*args, **kwargs)
        logger.info(f"GlobalAppSettings (id=1) saved at {self.updated_at}.")

    def delete(self, *args, **kwargs):
        # Prevent deletion of the singleton instance
        logger.warning(f"Attempt to delete GlobalAppSettings (id=1) was blocked.")
        #raise ValidationError("Cannot delete the GlobalAppSettings instance.")

    @classmethod
    def load(cls):
        """
        Loads the singleton instance of GlobalAppSettings.
        If the row doesn't exist (but the table does), it creates it with default values
        defined in the model fields.
        This method assumes the table has been created by migrations.
        """
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            logger.info("Initialized new GlobalAppSettings singleton instance (id=1) with default values.")
        return obj