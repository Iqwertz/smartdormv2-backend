# smartdorm/serializers.py
from rest_framework import serializers
from smartdorm.models import Tenant, Engagement, Department, GlobalAppSettings, Parcel, Subtenant,  Rental, Room, Departure, DepartmentSignature, Claim, EngagementApplication
from django.utils import timezone
from django.urls import reverse
import base64

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            'id', 'birthday', 'current_floor', 'current_points', 'current_room',
            'deposit', 'email', 'extension', 'external_id', 'gender', 'move_in',
            'move_out', 'name', 'nationality', 'note', 'probation_end', 'study_field',
            'sublet', 'surname', 'tel_number', 'university', 'username', 'new_address'
        ]
        read_only_fields = ['id']  # ID is auto-generated

class NewTenantSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    surname = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    gender = serializers.CharField(max_length=255)
    nationality = serializers.CharField(max_length=255)
    birthday = serializers.DateField()
    tel_number = serializers.CharField(max_length=255, required=False, allow_blank=True)
    move_in = serializers.DateField()
    current_room = serializers.CharField(max_length=255)
    deposit = serializers.DecimalField(max_digits=19, decimal_places=2, min_value=0)
    university = serializers.CharField(max_length=255)
    study_field = serializers.CharField(max_length=255)
    note = serializers.CharField(required=False, allow_blank=True)

class SubtenantSerializer(serializers.ModelSerializer):
    # To display tenant info nicely in GET responses
    tenant_name = serializers.SerializerMethodField(read_only=True)
    room_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Subtenant
        fields = '__all__'

    def get_tenant_name(self, obj):
        if obj.tenant:
            return f"{obj.tenant.name} {obj.tenant.surname}"
        return None

    def get_room_name(self, obj):
        if obj.room:
            return obj.room.name
        return None

class NewSubtenantSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    surname = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    move_in = serializers.DateField()
    move_out = serializers.DateField()
    tenant_id = serializers.IntegerField()
    room_id = serializers.IntegerField()
    university_confirmation = serializers.BooleanField()

    def validate(self, data):
        if data['move_in'] >= data['move_out']:
            raise serializers.ValidationError("Das Auszugsdatum muss nach dem Einzugsdatum liegen.")
        return data

class RentalSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = Rental
        fields = ['id', 'move_in', 'moved_out', 'room_name']

class TenantMoveSerializer(serializers.Serializer):
    room_id = serializers.IntegerField()
    move_date = serializers.DateField()

    def validate_room_id(self, value):
        if not Room.objects.filter(id=value).exists():
            raise serializers.ValidationError("Room does not exist.")
        return value

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'full_name']

class EngagementSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = Engagement
        fields = [
            'id',
            'semester',
            'points',
            'note',
            'compensate',
            'department', 
            # 'department_name', 
            'external_id' 
        ]
        read_only_fields = ['id', 'department', 'external_id']
        
        
class HsvTenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            'name', 'surname', 'email', 'tel_number', 'current_room', 'current_floor'
        ]
        read_only_fields = fields

class GlobalAppSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalAppSettings
        fields = ['current_semester', 'applications_open', 'show_applications', 'updated_at']
        read_only_fields = ['updated_at']

    def update(self, instance, validated_data):
        instance.current_semester = validated_data.get('current_semester', instance.current_semester)
        instance.applications_open = validated_data.get('applications_open', instance.applications_open)
        instance.show_applications = validated_data.get('show_applications', instance.show_applications)
        instance.save()
        return instance
    
class EngagementApplicationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EngagementApplication
        # Tenant and semester are set in the view
        fields = ['department', 'motivation', 'image', 'image_name']
        extra_kwargs = {
            'image': {'required': False, 'allow_null': True},
            'image_name': {'required': False, 'allow_blank': True}
        }

class TenantForApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['name', 'surname']

class EngagementApplicationListSerializer(serializers.ModelSerializer):
    tenant = TenantForApplicationSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    # image_base64 = serializers.SerializerMethodField()  <-- REMOVE THIS
    image_url = serializers.SerializerMethodField() # <-- ADD THIS

    class Meta:
        model = EngagementApplication
        # fields = ['id', 'tenant', 'department', 'motivation', 'image_base64'] <-- CHANGE THIS
        fields = ['id', 'tenant', 'department', 'motivation', 'image_url'] # <-- TO THIS

    def get_image_url(self, obj):
        # Return a URL to the new image endpoint if an image exists
        if obj.image:
            # We will create two different endpoints for tenants and heimrat for permission reasons
            request = self.context.get('request')
            if request and 'heimrat' in request.path:
                 return request.build_absolute_uri(reverse('engagements:heimrat-get-application-image', kwargs={'app_id': obj.id}))
            return request.build_absolute_uri(reverse('tenants:get-application-image', kwargs={'app_id': obj.id}))
        return None

class MyEngagementApplicationSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = EngagementApplication
        fields = ['id', 'semester', 'department', 'motivation']

class HeimratEngagementApplicationCreateSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())

    class Meta:
        model = EngagementApplication
        fields = ['tenant', 'department', 'motivation', 'image', 'image_name']
        extra_kwargs = {
            'image': {'required': False, 'allow_null': True},
            'image_name': {'required': False, 'allow_blank': True}
        }

class ParcelCreateRequestSerializer(serializers.Serializer):
    room = serializers.CharField(max_length=255, required=False, allow_blank=True)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    surname = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    registered = serializers.BooleanField(default=False)

    def validate(self, data):
        room = data.get('room')
        name = data.get('name')
        surname = data.get('surname')

        if not room and not (name and surname):
            raise serializers.ValidationError(
                "Either 'room' or both 'name' and 'surname' must be provided."
            )
        if room and (name or surname):
            raise serializers.ValidationError(
                "Provide 'room' OR ('name' and 'surname'), not both."
            )
        return data

class ParcelSerializer(serializers.ModelSerializer):
    # To display tenant/subtenant info nicely if needed in GET responses
    tenant_info = serializers.SerializerMethodField(read_only=True)
    subtenant_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Parcel
        fields = [
            'id', 'external_id', 'arrived', 'count', 'registered',
            'picked_up', 'tenant', 'subtenant', 'tenant_info', 'subtenant_info'
        ]
        read_only_fields = ['id', 'external_id', 'arrived', 'picked_up', 'tenant_info', 'subtenant_info']

    def get_tenant_info(self, obj):
        if obj.tenant:
            return f"{obj.tenant.name} {obj.tenant.surname} (Room: {obj.tenant.current_room or 'N/A'})"
        return None

    def get_subtenant_info(self, obj):
        if obj.subtenant:
            return f"{obj.subtenant.name} {obj.subtenant.surname} (Associated Room: {obj.subtenant.room.name or 'N/A'})"
        return None

class DepartureSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)

    class Meta:
        model = Departure
        fields = ['tenant', 'status', 'created_on', 'external_id']

class DepartureDetailSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)
    signatures = serializers.SerializerMethodField()

    class Meta:
        model = Departure
        fields = ['tenant', 'status', 'created_on', 'external_id', 'signatures']

    def get_signatures(self, obj):
        signatures = obj.departmentsignature_set.all().order_by('department_name')
        return DepartmentSignatureSerializer(signatures, many=True).data

class DepartmentSignatureSerializer(serializers.ModelSerializer):
    departure = DepartureSerializer(read_only=True)

    class Meta:
        model = DepartmentSignature
        fields = ['id', 'external_id', 'amount', 'department_name', 'signed_on', 'departure']
        

class ClaimSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)
    class Meta:
        model = Claim
        fields = ['id', 'created_on', 'status', 'type', 'tenant', 'external_id']
        
class AdminTenantSerializer(serializers.ModelSerializer):
    """Minimal tenant info for the engagement list."""
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'surname', 'email', 'current_room', 'current_floor']

class AdminEngagementListSerializer(serializers.ModelSerializer):
    """Detailed serializer for listing engagements in the admin view."""
    tenant = AdminTenantSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = Engagement
        fields = ['id', 'tenant', 'department', 'semester', 'points', 'note', 'compensate']

class EngagementCreateByHeimratSerializer(serializers.Serializer):
    tenant_id = serializers.IntegerField()
    department_id = serializers.IntegerField()
    semester = serializers.CharField(max_length=255)
    note = serializers.CharField(required=False, allow_blank=True)
    compensate = serializers.BooleanField(default=False)

    def validate_tenant_id(self, value):
        if not Tenant.objects.filter(id=value).exists():
            raise serializers.ValidationError("Tenant not found.")
        return value
    
    def validate_department_id(self, value):
        if not Department.objects.filter(id=value).exists():
            raise serializers.ValidationError("Department not found.")
        return value

class EngagementPointUpdateSerializer(serializers.Serializer):
    points = serializers.DecimalField(max_digits=19, decimal_places=2)