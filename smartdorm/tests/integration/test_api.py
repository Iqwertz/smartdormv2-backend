from django.test import TestCase, Client

class ApiTestCase(TestCase):
    """Test case for the API without requiring database modifications"""

    def setUp(self):
        """Setup for the tests"""
        self.client = Client()
    
    def test_api_homepage(self):
        """Test that the home page loads correctly"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200) 