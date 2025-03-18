from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
from django.db import models

class Command(BaseCommand):
    help = 'Enhanced verification of database schema against Django models'

    def get_field_type_mapping(self):
        """Map Django field types to PostgreSQL types"""
        return {
            models.CharField: 'character varying',
            models.TextField: 'text',
            models.IntegerField: 'integer',
            models.BigIntegerField: 'bigint',
            models.DecimalField: 'numeric',
            models.DateField: 'date',
            models.DateTimeField: 'timestamp with time zone',  # Updated this
            models.BooleanField: 'boolean',
            models.FloatField: 'double precision',
            models.BinaryField: 'bytea',
            models.ForeignKey: 'integer',  # Added this
            models.OneToOneField: 'integer',  # Added this
        }

    def get_field_details(self, field):
        """Extract relevant details from a model field"""
        details = {
            'type': field.__class__,
            'null': field.null,
            'max_length': getattr(field, 'max_length', None),
            'unique': field.unique,
        }
        
        # Handle foreign keys
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            details['type'] = models.ForeignKey
            
        if isinstance(field, models.DecimalField):
            details.update({
                'max_digits': field.max_digits,
                'decimal_places': field.decimal_places,
            })
        return details

    def handle(self, *args, **options):
        type_mapping = self.get_field_type_mapping()
        with connection.cursor() as cursor:
            models_list = apps.get_models()
            
            for model in models_list:
                if not model._meta.managed:
                    self.stdout.write(f"\nChecking unmanaged model: {model.__name__}")
                else:
                    self.stdout.write(f"\nChecking managed model: {model.__name__}")
                
                table_name = model._meta.db_table
                
                # Get database information
                cursor.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        character_maximum_length,
                        is_nullable,
                        column_default,
                        numeric_precision,
                        numeric_scale
                    FROM information_schema.columns 
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, [table_name])
                
                db_columns = {row[0]: {
                    'type': row[1],
                    'max_length': row[2],
                    'nullable': row[3] == 'YES',
                    'default': row[4],
                    'numeric_precision': row[5],
                    'numeric_scale': row[6]
                } for row in cursor.fetchall()}
                
                # Get model information
                model_fields = {f.column if hasattr(f, 'column') else f.name: self.get_field_details(f) 
                              for f in model._meta.fields}
                
                # Check for missing fields in database
                for field_name, field_details in model_fields.items():
                    if field_name not in db_columns:
                        self.stdout.write(self.style.ERROR(
                            f'  ✗ Field "{field_name}" in model not found in database'
                        ))
                        continue
                    
                    db_info = db_columns[field_name]
                    expected_type = type_mapping.get(field_details['type'], 'unknown')
                    
                    if expected_type != db_info['type']:
                        if not (expected_type == 'integer' and db_info['type'] == 'bigint'):  # Allow integer/bigint flexibility
                            self.stdout.write(self.style.WARNING(
                                f'  ⚠ Type mismatch for "{field_name}": '
                                f'model={expected_type}, db={db_info["type"]}'
                            ))
                    
                    if field_details['null'] != db_info['nullable']:
                        self.stdout.write(self.style.WARNING(
                            f'  ⚠ Nullable mismatch for "{field_name}": '
                            f'model={field_details["null"]}, db={db_info["nullable"]}'
                        ))
                
                # Check for extra columns in database
                for column_name in db_columns:
                    if column_name not in model_fields:
                        self.stdout.write(self.style.WARNING(
                            f'  ⚠ Column "{column_name}" in database not found in model'
                        ))