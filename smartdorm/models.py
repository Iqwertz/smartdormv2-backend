from django.db import models
from django.utils import timezone
from datetime import timedelta
import logging

from decimal import Decimal
import uuid

logger = logging.getLogger(__name__)


def generate_external_id():
    """Generate a unique external ID (UUID hex)"""
    return uuid.uuid4().hex

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
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id')

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
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id')

    class Meta:
        db_table = 't_engagement'
        managed = False

class EngagementApplication(models.Model):
    id = models.IntegerField(primary_key=True)
    semester = models.CharField(max_length=255) 
    motivation = models.TextField()
    external_id = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.DO_NOTHING, db_column='department_id')
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id')
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
    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.CASCADE, db_column='tenant_id')
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
    departure = models.ForeignKey(Departure, on_delete=models.CASCADE, db_column='departure_id')

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
    tenant = models.ForeignKey('Tenant', null=True, blank=True, on_delete=models.CASCADE, db_column='tenant_id')
    subtenant = models.ForeignKey('Subtenant', null=True, blank=True, on_delete=models.CASCADE, db_column='subtenant_id')

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
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id')
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
    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.CASCADE, db_column='tenant_id')
    name = models.CharField(max_length=255)
    iban = models.CharField(max_length=255)

    class Meta:
        db_table = 't_deposit_bank'
        managed = False

class Claim(models.Model):
    class Status(models.TextChoices):
        CREATED = 'CREATED', 'Erstellt'
        PROCESSING = 'PROCESSING', 'In Bearbeitung'
        APPROVED = 'APPROVED', 'Genehmigt'
        REJECTED = 'REJECTED', 'Abgelehnt'

    class Type(models.TextChoices):
        EXTENSION = 'EXTENSION', 'Verlängerung'

    id = models.IntegerField(primary_key=True)
    created_on = models.DateField()
    external_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    type = models.CharField(max_length=20, choices=Type.choices)
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id')

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
        
class Termination(models.Model):
    """
    Represents a hard termination of a contract.
    If this exists for a tenant, it overrides all other calculation logic.
    """
    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.CASCADE, db_column='tenant_id', related_name='termination_record')
    date = models.DateField()
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 't_termination'
        managed = True 

class DepartmentExtension(models.Model):
    """
    Represents ad-hoc extensions (or reductions) granted by the department.
    Months can be negative to reduce the contract duration.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id', related_name='department_extensions')
    months = models.IntegerField(help_text="Number of months to extend (positive) or reduce (negative)")
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 't_department_extension'
        managed = True

class LdapRoleAssignment(models.Model):
    """
    An LDAP group membership granted by hand from the Netzwerkreferat page.

    Exists so the nightly recalculate_tenant_stats sync knows the membership is
    intentional: without a record here the sync strips every managed group it cannot
    derive from floor/department/defaults, so a manual grant would be gone by morning.

    Keyed by LDAP cn instead of a Tenant FK, so one model covers tenants, subtenants
    and Verwaltung accounts alike, and both phases of the sync can look an assignment
    up by the username they already hold.
    """
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=255, help_text="LDAP cn of the account")
    display_name = models.CharField(max_length=255, null=True, blank=True, help_text="Snapshot of the account's display name, for the overview list")
    group_dn = models.CharField(max_length=512, help_text="Full DN of the granted LDAP group")
    note = models.TextField(null=True, blank=True, help_text="Why this role was granted")
    expires_at = models.DateField(null=True, blank=True, help_text="Last day the role is valid. Empty means unlimited.")
    created_by = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 't_ldap_role_assignment'
        managed = True
        unique_together = (('username', 'group_dn'),)

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
    show_applications = models.BooleanField(
        default=False,
        help_text="Are engagement applications visible to tenants?"
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

class Event(models.Model):
    """
    Represents a generic, recurring event type (e.g., "General Assembly", "Bar Duty").
    Configured in settings by the Network department.
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    parts_count = models.IntegerField(default=1, help_text="How many parts one attendance tracking session can have")
    required_parts = models.IntegerField(default=1, help_text="How many parts are required to count as attended")
    admin_groups = models.JSONField(default=list, help_text="List of LDAP groups that can manage this event. 'ADMIN' always has permission.")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 't_event'
        managed = True

class AttendanceSession(models.Model):
    """
    Represents a single occurrence of an Event on a specific date (e.g., General Assembly on 2026-04-12).
    """
    id = models.AutoField(primary_key=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='sessions')
    title = models.CharField(max_length=255, blank=True, default="", help_text="Optional custom session name")
    date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=[('CREATED', 'Created'), ('ACTIVE', 'Active'), ('CLOSED', 'Closed')],
        default='CREATED'
    )
    current_part = models.IntegerField(default=0, help_text="The currently active part (1 to parts_count). 0 means none active.")
    secret_token = models.CharField(max_length=64, null=True, blank=True)
    previous_secret_token = models.CharField(max_length=64, null=True, blank=True)
    last_rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 't_attendance_session'
        managed = True

class AttendanceRecord(models.Model):
    """
    Records a tenant's attendance for a specific part of an AttendanceSession.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='tenant_id', related_name='attendance_records')
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    part = models.IntegerField(help_text="Which part of the session (e.g., 1, 2, 3) this record applies to")
    timestamp = models.DateTimeField(auto_now_add=True)
    is_manual_override = models.BooleanField(default=False)

    class Meta:
        db_table = 't_attendance_record'
        managed = True
        unique_together = ('tenant', 'session', 'part')


class BaseAttendanceRecord(models.Model):
    """
    Records manually added base attendance for a tenant at an event.
    This allows migration from the old Excel-based attendance system.
    
    Note: The 'parts_count' field stores the number of SESSIONS attended in the old system,
    not the number of parts within a session.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='tenant_id', related_name='base_attendance_records')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='base_attendance_records')
    parts_count = models.IntegerField(help_text="Number of sessions attended in the old system (stored as 'parts_count' for database compatibility)")
    note = models.TextField(null=True, blank=True, help_text="Reason for adding base attendance")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 't_base_attendance_record'
        managed = True
        unique_together = ('tenant', 'event')

# ============================================================================
# Print & Scan System Models

class Device(models.Model):
    """Represents a printer/scanner"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, help_text="Name of the printer (e.g. Samsung Xpress C1860FW)")
    location = models.CharField(max_length=255, help_text="Location (e.g. Creative Department Room)")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, help_text="Responsible department")
    is_active = models.BooleanField(default=True, help_text="Global on/off")
    allow_new_sessions = models.BooleanField(default=True, help_text="Allow new sessions")
    price_per_page_color = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.10'), help_text="Price per color page in Euro")
    price_per_page_gray = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.05'), help_text="Price per black & white page in Euro")
    max_session_duration_minutes = models.IntegerField(default=30, help_text="Maximum session duration in minutes")
    cups_printer_name = models.CharField(max_length=255, help_text="Name of the printer in CUPS (e.g. Samsung_C1860_Series)")
    ip_address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="IP address or hostname of the Raspberry Pi running CUPS and the scan service (e.g. 10.50.0.15). Falls back to CUPS_SERVER setting when empty.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 't_device'
        verbose_name = "Device"
        verbose_name_plural = "Devices"

    def __str__(self):
        return f"{self.name} ({self.location})"

class PrintSession(models.Model):
    """Active or past print/scan sessions"""
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        EXPIRED = 'EXPIRED', 'Expired'
        TERMINATED = 'TERMINATED', 'Terminated'
    
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='tenant_id')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, db_column='device_id')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    external_id = models.CharField(max_length=255, unique=True, default=generate_external_id)
    pending_scan = models.JSONField(
        null=True,
        blank=True,
        help_text="Set when a scan is requested; the Pi agent reads it, scans, uploads, then it is cleared. Example: {'resolution': 300, 'mode': 'Color', 'source': 'Flatbed'}",
    )
    
    class Meta:
        db_table = 't_print_session'
        verbose_name = "Print Session"
        verbose_name_plural = "Print Sessions"
        ordering = ['-started_at']

    def __str__(self):
        return f"Session {self.external_id[:8]} - {self.tenant.get_full_name()} ({self.status})"

class PrintJob(models.Model):
    """Individual print jobs"""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PRINTING = 'PRINTING', 'Printing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(PrintSession, on_delete=models.CASCADE, db_column='session_id')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='tenant_id')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, db_column='device_id')
    filename = models.CharField(max_length=255)
    color_mode = models.CharField(max_length=10, default='Color', choices=[('Color', 'Color'), ('Gray', 'Gray')], help_text="Color mode used for this job")
    copies = models.IntegerField(default=1, help_text="Number of copies requested (needed by the Pi agent to print)")
    document = models.FileField(
        upload_to='print_jobs/',
        null=True,
        blank=True,
        help_text="Uploaded PDF to be fetched and printed by the Pi agent.",
    )
    pages = models.IntegerField(null=True, blank=True, help_text="Number of printed pages (updated after printing)")
    cost = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Cost in Euro (only for COMPLETED)")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this job was settled/paid by administration. NULL = still outstanding."
    )
    error_message = models.TextField(null=True, blank=True)
    cups_job_id = models.CharField(max_length=255, null=True, blank=True, help_text="CUPS Job ID for status query")
    external_id = models.CharField(max_length=255, unique=True, default=generate_external_id)
    
    class Meta:
        db_table = 't_print_job'
        verbose_name = "Print Job"
        verbose_name_plural = "Print Jobs"
        ordering = ['-created_at']

    def __str__(self):
        return f"Job {self.external_id[:8]} - {self.filename} ({self.status})"
    
    def save(self, *args, **kwargs):
        # Calculate cost only for COMPLETED, otherwise 0
        if self.status == 'COMPLETED' and self.pages and self.device:
            # Use color or gray price depending on color_mode
            if self.color_mode == 'Color':
                price_per_page = self.device.price_per_page_color
            else:
                price_per_page = self.device.price_per_page_gray
            self.cost = Decimal(str(self.pages)) * price_per_page
            # Log the calculation for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"PrintJob.save() calculated cost: pages={self.pages}, color_mode={self.color_mode}, price_per_page={price_per_page}, cost={self.cost}")
        elif self.status != 'COMPLETED':
            self.cost = Decimal('0.00')
        super().save(*args, **kwargs)

class Scan(models.Model):
    """Scanned documents (temporarily stored)"""
    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(PrintSession, on_delete=models.CASCADE, db_column='session_id')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='tenant_id')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, db_column='device_id')
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, help_text="Relative path to temporary storage (scans/temp/session_XXX/...)")
    scanned_at = models.DateTimeField(auto_now_add=True)
    external_id = models.CharField(max_length=255, unique=True, default=generate_external_id)
    
    class Meta:
        db_table = 't_scan'
        verbose_name = "Scan"
        verbose_name_plural = "Scans"
        ordering = ['-scanned_at']

    def __str__(self):
        return f"Scan {self.external_id[:8]} - {self.filename}"

# --- HSV e.V. membership ------------------------------------------------------------------
# The Verein is a separate legal entity from the Schollheim e.V. that owns t_tenant, so its
# data lives in its own managed tables rather than as columns on the legacy tenant record.


class EncryptedIbanMixin:
    """
    Shared accessors for the (iban_ciphertext, iban_last4) column pair.

    The last four characters are kept in the clear so lists can show a masked IBAN without
    decrypting a whole page of rows - decryption is reserved for the moments someone actually
    needs the number, which are logged.
    """

    def set_iban(self, raw_iban):
        from .utils import crypto_utils

        if not raw_iban:
            self.iban_ciphertext = ''
            self.iban_last4 = ''
            return

        iban = crypto_utils.normalize_iban(raw_iban)
        self.iban_ciphertext = crypto_utils.encrypt_str(iban)
        self.iban_last4 = crypto_utils.iban_last4(iban)

    def get_iban(self):
        """Full IBAN in plaintext. Every caller must be behind a permission check."""
        from .utils import crypto_utils

        return crypto_utils.decrypt_str(self.iban_ciphertext)

    @property
    def iban_masked(self):
        """Display form that needs no key: 'DE89 •••• •••• •••• •••• 00'."""
        if not self.iban_last4:
            return ''
        return f"•••• {self.iban_last4}"


class MembershipApplication(EncryptedIbanMixin, models.Model):
    """
    One submitted Beitrittserklärung, including the SEPA mandate given with it.

    Treated as evidence and never edited after submission: if a member later disputes a
    direct debit, the Verein has to be able to show what exactly was agreed to, when, by
    whom and under which version of the text. Later changes to the bank details go to
    Membership, not here.
    """

    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Eingereicht'
        APPROVED = 'APPROVED', 'Genehmigt'
        REJECTED = 'REJECTED', 'Abgelehnt'

    class PaymentMethod(models.TextChoices):
        SEPA = 'SEPA', 'SEPA-Lastschriftmandat'
        OTHER = 'OTHER', 'Andere Zahlungsmethode (mit dem Finanzenreferat vereinbart)'

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, db_column='tenant_id',
                               related_name='membership_applications')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)

    # Declared personal data. Deliberately a snapshot rather than a live read off Tenant:
    # the declaration has to stay readable as it was signed, even after a name change.
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    requested_join_date = models.DateField(help_text="Gewünschtes Beitrittsdatum")
    is_of_age = models.BooleanField(help_text="Selbstauskunft: mindestens 18 Jahre alt")

    # Freiwillige Einwilligung in die Amtsliste. Default off, never required to submit,
    # and revocable - so it is stored separately from the rest of the form.
    amtsliste_consent = models.BooleanField(default=False)

    # Acknowledgement of Satzung, Vereinsordnungen and the current Mitgliedsbeitrag.
    statutes_accepted = models.BooleanField(default=False)

    # SEPA mandate
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices,
                                      default=PaymentMethod.SEPA)
    account_holder_first_name = models.CharField(max_length=255, blank=True)
    account_holder_last_name = models.CharField(max_length=255, blank=True)
    iban_ciphertext = models.TextField(blank=True)
    iban_last4 = models.CharField(max_length=4, blank=True)
    mandate_confirmed = models.BooleanField(
        default=False,
        help_text="Mandat erteilt und Berechtigung zur Erteilung bestätigt"
    )

    # Evidence of the submission itself.
    terms_version = models.CharField(
        max_length=32,
        help_text="Version des Erklärungstextes, der beim Absenden angezeigt wurde"
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    submitted_ip = models.GenericIPAddressField(null=True, blank=True)
    submitted_by_username = models.CharField(max_length=255)
    declaration_pdf = models.BinaryField(
        null=True, blank=True,
        help_text="Gerendertes PDF der Erklärung. In der DB statt im Dateisystem, weil es "
                  "die IBAN enthält und MEDIA_ROOT vom Webserver ausgeliefert werden kann."
    )

    # Decision
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.CharField(max_length=255, blank=True)
    decision_note = models.TextField(blank=True)

    class Meta:
        db_table = 't_membership_application'
        managed = True
        ordering = ['-submitted_at']
        constraints = [
            # A tenant may re-apply after a rejection, but only ever have one open application.
            models.UniqueConstraint(
                fields=['tenant'],
                condition=models.Q(status='SUBMITTED'),
                name='uniq_open_membership_application',
            )
        ]

    def __str__(self):
        return f"Mitgliedsantrag {self.id} - {self.first_name} {self.last_name} ({self.status})"


class Membership(EncryptedIbanMixin, models.Model):
    """
    The live membership and SEPA mandate register. One row per tenant, created on approval.

    Unlike the application this is mutable: members change banks, revoke mandates, and the
    membership ends when the Mietverhältnis does.
    """

    class MandateStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Aktiv'
        REVOKED = 'REVOKED', 'Widerrufen'
        EXPIRED = 'EXPIRED', 'Abgelaufen'
        NONE = 'NONE', 'Kein Mandat (andere Zahlungsmethode)'

    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.CASCADE,
                                  db_column='tenant_id', related_name='membership')
    application = models.ForeignKey('MembershipApplication', on_delete=models.SET_NULL,
                                    null=True, blank=True, db_column='application_id',
                                    related_name='membership')

    joined_on = models.DateField(help_text="Beitrittsdatum")
    ended_on = models.DateField(
        null=True, blank=True,
        help_text="Ende der Mitgliedschaft. Endet laut Beitrittserklärung automatisch mit "
                  "dem Mietverhältnis."
    )

    amtsliste_consent = models.BooleanField(default=False)
    amtsliste_consent_at = models.DateTimeField(null=True, blank=True)

    # --- SEPA mandate ---
    mandate_reference = models.CharField(
        max_length=35, unique=True, null=True, blank=True,
        help_text="Mandatsnummer. Eindeutig pro Gläubiger, max. 35 Zeichen."
    )
    mandate_signed_on = models.DateField(
        null=True, blank=True,
        help_text="Datum der Mandatserteilung - geht so in die pain.008 ein."
    )
    mandate_status = models.CharField(max_length=10, choices=MandateStatus.choices,
                                      default=MandateStatus.NONE)
    payment_method = models.CharField(max_length=10,
                                      choices=MembershipApplication.PaymentMethod.choices,
                                      default=MembershipApplication.PaymentMethod.SEPA)
    account_holder = models.CharField(max_length=255, blank=True)
    iban_ciphertext = models.TextField(blank=True)
    iban_last4 = models.CharField(max_length=4, blank=True)
    last_collection_on = models.DateField(
        null=True, blank=True,
        help_text="Letzter Einzug. Entscheidet über FRST/RCUR und über den Ablauf des "
                  "Mandats nach 36 Monaten ohne Nutzung."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 't_membership'
        managed = True
        ordering = ['-joined_on']

    def __str__(self):
        return f"Mitgliedschaft {self.tenant_id} seit {self.joined_on}"

    @property
    def is_active(self):
        return self.ended_on is None or self.ended_on >= timezone.now().date()

    @property
    def sequence_type(self):
        """FRST for the first collection under this mandate, RCUR for every one after."""
        return 'RCUR' if self.last_collection_on else 'FRST'

    def end_membership(self, end_date):
        """
        End the membership as of end_date.

        The Beitrittserklärung says the membership ends automatically with the Mietverhältnis
        and needs no separate Austrittserklärung, so this is called from the departure flow
        rather than being something the member has to do.

        The mandate is deliberately left ACTIVE until the end date: contributions are still
        owed for the remaining months, and is_collectable stops including the member on its
        own once the date has passed.
        """
        self.ended_on = end_date
        self.save(update_fields=['ended_on', 'updated_at'])

    def is_collectable_on(self, reference_date):
        """
        Whether a direct debit due on reference_date may be collected from this member.

        The date matters: a membership that ends on 30.09. still owes the contributions due
        before then, so it must stay collectable for those runs and drop out only for later
        ones. Comparing against "today" instead would wrongly skip the final months.
        """
        if self.ended_on is not None and self.ended_on < reference_date:
            return False
        return (
            self.payment_method == MembershipApplication.PaymentMethod.SEPA
            and self.mandate_status == self.MandateStatus.ACTIVE
            and bool(self.mandate_reference)
            and bool(self.iban_ciphertext)
        )

    @property
    def is_collectable(self):
        """Collectable as of today. Display hint for the member register."""
        return self.is_collectable_on(timezone.now().date())


class MembershipPrompt(models.Model):
    """
    Records that a tenant asked not to be shown the join dialog again.

    Joining is voluntary, so declining has to be a real, respected answer rather than a
    dialog that keeps reappearing.
    """

    tenant = models.OneToOneField('Tenant', primary_key=True, on_delete=models.CASCADE,
                                  db_column='tenant_id', related_name='membership_prompt')
    opted_out_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 't_membership_prompt'
        managed = True

    def __str__(self):
        return f"Kein Beitrittshinweis für Bewohner {self.tenant_id}"


class DirectDebitRun(models.Model):
    """
    One generated SEPA collection file (pain.008).

    Persisted rather than generated on the fly so that the FRST/RCUR sequence stays correct
    and a file can be re-downloaded without producing a second, different collection.
    """

    id = models.AutoField(primary_key=True)
    message_id = models.CharField(max_length=35, unique=True,
                                  help_text="MsgId der pain.008, eindeutig gegenüber der Bank")
    collection_date = models.DateField(help_text="Fälligkeitsdatum des Einzugs")
    amount_per_member = models.DecimalField(max_digits=10, decimal_places=2)
    member_count = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    xml = models.TextField(blank=True)
    created_by = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 't_direct_debit_run'
        managed = True
        ordering = ['-collection_date', '-created_at']

    def __str__(self):
        return f"Einzug {self.collection_date} ({self.member_count} Mitglieder)"


class DirectDebitItem(models.Model):
    """A single member's position in a collection run, as it was submitted to the bank."""

    id = models.AutoField(primary_key=True)
    run = models.ForeignKey('DirectDebitRun', on_delete=models.CASCADE, db_column='run_id',
                            related_name='items')
    membership = models.ForeignKey('Membership', on_delete=models.CASCADE,
                                   db_column='membership_tenant_id', related_name='debit_items')
    mandate_reference = models.CharField(max_length=35)
    sequence_type = models.CharField(max_length=4, help_text="FRST oder RCUR")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    end_to_end_id = models.CharField(max_length=35)

    class Meta:
        db_table = 't_direct_debit_item'
        managed = True
        unique_together = (('run', 'membership'),)

    def __str__(self):
        return f"{self.mandate_reference} - {self.amount} EUR ({self.sequence_type})"
