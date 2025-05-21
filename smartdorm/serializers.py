# smartdorm/serializers.py
from rest_framework import serializers
from smartdorm.models import Tenant, Engagement, Department 

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
