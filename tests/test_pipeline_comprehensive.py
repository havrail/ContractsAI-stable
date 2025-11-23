import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src_python')))

from pipeline import PipelineManager


class TestPipelineManager:
    """Unit tests for PipelineManager class."""
    
    @pytest.fixture
    def pipeline(self):
        """Create a PipelineManager instance with mocked dependencies."""
        with patch('pipeline.easyocr.Reader'):
            manager = PipelineManager()
            manager.llm_client = Mock()
            manager.reader = Mock()
            return manager
    
    def test_calculate_file_hash(self, pipeline, tmp_path):
        """Test file hash calculation."""
        # Create a temporary file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")
        
        # Calculate hash
        hash_result = pipeline.calculate_file_hash(str(test_file))
        
        # Verify
        assert hash_result is not None
        assert len(hash_result) == 32  # MD5 hash is 32 characters
        
        # Same file should produce same hash
        hash_result2 = pipeline.calculate_file_hash(str(test_file))
        assert hash_result == hash_result2
    
    def test_map_choice(self, pipeline):
        """Test choice mapping functionality."""
        choices = ["Service Agreement", "NDA", "Other"]
        
        # Exact match
        assert pipeline._map_choice("Service Agreement", choices) == "Service Agreement"
        
        # Partial match
        assert pipeline._map_choice("service", choices) == "Service Agreement"
        
        # No match returns default
        assert pipeline._map_choice("Unknown", choices, default="Other") == "Other"
    
    def test_map_signature(self, pipeline):
        """Test signature mapping logic."""
        # Fully signed
        assert pipeline._map_signature("Fully Signed", 2) == "Fully Signed"
        assert pipeline._map_signature("Both parties", 2) == "Fully Signed"
        
        # Counterparty signed
        assert pipeline._map_signature("Counterparty signed", 1) == "Counterparty Signed"
        
        # Telenity signed (default)
        assert pipeline._map_signature("", 0) == "Telenity Signed"
        
        # Visual count override
        assert pipeline._map_signature("", 2) == "Fully Signed"
        assert pipeline._map_signature("", 1) == "Counterparty Signed"
    
    @patch('pipeline.convert_from_path')
    @patch('pipeline.PdfReader')
    def test_extract_text_native_success(self, mock_pdf_reader, mock_convert, pipeline):
        """Test successful PDF text extraction."""
        # Mock PDF pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page 1 text"
        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page 2 text"
        
        mock_reader = Mock()
        mock_reader.pages = [mock_page1, mock_page2]
        mock_pdf_reader.return_value = mock_reader
        
        # Test
        result = pipeline.extract_text_native("test.pdf")
        
        # Verify
        assert result == "Page 1 text\\nPage 2 text"
    
    @patch('pipeline.SessionLocal')
    def test_process_single_file_cache_hit(self, mock_session, pipeline):
        """Test that cached results are returned."""
        # Mock cached contract
        cached_contract = Mock()
        cached_contract.dosya_adi = "test.pdf"
        cached_contract.contract_name = "Test Contract"
        cached_contract.file_hash = "abc123"
        cached_contract.doc_type = "NDA"
        cached_contract.signature = "Fully Signed"
        cached_contract.company_type = "Vendor"
        cached_contract.signing_party = "ACME Corp"
        cached_contract.country = "USA"
        cached_contract.address = "123 Main St"
        cached_contract.signed_date = "2024-01-01"
        cached_contract.telenity_entity = "TE - Telenity Europe"
        cached_contract.telenity_fullname = "Telenity İletişim"
        
        # Mock database query
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = cached_contract
        mock_db.query.return_value = mock_query
        mock_session.return_value = mock_db
        
        # Mock hash calculation
        pipeline.calculate_file_hash = Mock(return_value="abc123")
        
        # Test
        result = pipeline.process_single_file("test.pdf", "/fake/path")
        
        # Verify cache hit
        assert result["dosya_adi"] == "test.pdf"
        assert result["contract_name"] == "Test Contract"
        assert result["durum_notu"] == "Önbellekten Alındı"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
