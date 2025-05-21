# smartdorm/serializers.py
from rest_framework import serializers
from smartdorm.models import Tenant, Engagement, Department, GlobalAppSettings, Parcel
from django.utils import timezone

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

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['name', 'full_name']

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
        fields = ['current_semester', 'applications_open', 'updated_at']
        read_only_fields = ['updated_at']

    def update(self, instance, validated_data):
        instance.current_semester = validated_data.get('current_semester', instance.current_semester)
        instance.applications_open = validated_data.get('applications_open', instance.applications_open)
        instance.save()
        return instance
    
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