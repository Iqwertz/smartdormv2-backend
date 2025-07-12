"""
Unit tests for model utility functions.
These tests don't require database setup and can be run quickly in CI/CD.
"""
import unittest
from unittest.mock import Mock, patch

from smartdorm.models import get_active_tenants


class TestModelUtilityFunctions(unittest.TestCase):
    """Unit tests for model utility functions"""

    @patch('smartdorm.models.Tenant.objects')
    def test_get_active_tenants(self, mock_tenant_objects):
        """Test get_active_tenants function"""
        mock_filter = Mock()
        mock_tenant_objects.filter.return_value = mock_filter
        
        result = get_active_tenants()
        
        mock_tenant_objects.filter.assert_called_once()
        self.assertEqual(result, mock_filter)


if __name__ == '__main__':
    unittest.main()
