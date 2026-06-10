import pytest
from rest_framework.test import APIRequestFactory
from apps.platform.views.search_views import FederatedSearchView
from unittest.mock import patch

class TestFederatedSearchView:
    @pytest.fixture
    def factory(self):
        return APIRequestFactory()

    @pytest.fixture
    def view(self):
        return FederatedSearchView.as_view()

    @pytest.mark.django_db
    def test_search_view_no_query_parameter(self, factory, view):
        """Test search endpoint when 'q' parameter is missing."""
        request = factory.get('/api/search/')
        response = view(request)
        
        assert response.status_code == 200
        assert response.data == {
            "internal_results": [],
            "documentation_results": []
        }

    @pytest.mark.django_db
    def test_search_view_empty_query(self, factory, view):
        """Test search endpoint when 'q' parameter is empty."""
        request = factory.get('/api/search/', {'q': ''})
        response = view(request)
        
        assert response.status_code == 200
        assert response.data == {
            "internal_results": [],
            "documentation_results": []
        }

    @pytest.mark.django_db
    def test_search_view_whitespace_query(self, factory, view):
        """Test search endpoint when 'q' parameter is only whitespace."""
        request = factory.get('/api/search/', {'q': '   '})
        response = view(request)
        
        assert response.status_code == 200
        assert response.data == {
            "internal_results": [],
            "documentation_results": []
        }

    @pytest.mark.django_db
    @patch('apps.platform.views.search_views.federated_search')
    def test_search_view_with_valid_query(self, mock_search, factory, view):
        """Test search endpoint with a valid query."""
        mock_results = {
            "internal_results": [{"id": 1, "title": "Test internal"}],
            "documentation_results": [{"id": 1, "title": "Test doc"}]
        }
        mock_search.return_value = mock_results
        
        request = factory.get('/api/search/', {'q': 'test query'})
        response = view(request)
        
        assert response.status_code == 200
        assert response.data == mock_results
        mock_search.assert_called_once_with('test query')

    @pytest.mark.django_db
    @patch('apps.platform.views.search_views.federated_search')
    def test_search_view_query_strip(self, mock_search, factory, view):
        """Test search endpoint strips whitespace from query before searching."""
        mock_results = {
            "internal_results": [{"id": 1, "title": "Test"}],
            "documentation_results": []
        }
        mock_search.return_value = mock_results
        
        request = factory.get('/api/search/', {'q': '  padded query  '})
        response = view(request)
        
        assert response.status_code == 200
        assert response.data == mock_results
        mock_search.assert_called_once_with('padded query')

    @pytest.mark.django_db
    @patch('apps.platform.views.search_views.federated_search')
    def test_search_view_exception_propagation(self, mock_search, factory, view):
        """Test search endpoint when federated_search throws an exception."""
        mock_search.side_effect = Exception("Search backend failed")
        
        request = factory.get('/api/search/', {'q': 'error query'})
        
        with pytest.raises(Exception, match="Search backend failed"):
            response = view(request)
