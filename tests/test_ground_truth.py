"""
Ground truth dataset and automated testing system for contract extraction.
"""

import os
import json
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import difflib

from logger import logger


@dataclass
class GroundTruthRecord:
    """A single ground truth record for testing."""
    filename: str
    party: str
    contract_type: str
    signed_date: str
    start_date: str = ""
    end_date: str = ""
    address: str = ""
    country: str = ""
    notes: str = ""
    created_at: str = ""
    verified_by: str = "manual"


@dataclass
class TestResult:
    """Result of testing one file."""
    filename: str
    passed: bool
    accuracy_score: float  # 0-100
    field_results: Dict[str, Dict] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_time: float = 0.0


@dataclass
class TestSummary:
    """Summary of all test results."""
    total_files: int
    passed: int
    failed: int
    average_accuracy: float
    field_accuracy: Dict[str, float] = field(default_factory=dict)
    total_time: float = 0.0
    timestamp: str = ""


class GroundTruthManager:
    """Manage ground truth dataset."""
    
    def __init__(self, dataset_path: str = "tests/ground_truth_dataset.json"):
        self.dataset_path = dataset_path
        self.dataset: Dict[str, GroundTruthRecord] = {}
        self._load_dataset()
    
    def _load_dataset(self):
        """Load ground truth dataset from file."""
        if os.path.exists(self.dataset_path):
            try:
                with open(self.dataset_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for filename, record in data.items():
                        self.dataset[filename] = GroundTruthRecord(**record)
                logger.info(f"Loaded {len(self.dataset)} ground truth records")
            except Exception as e:
                logger.error(f"Failed to load ground truth dataset: {e}")
        else:
            logger.warning(f"Ground truth dataset not found: {self.dataset_path}")
            self.dataset = {}
    
    def save_dataset(self):
        """Save ground truth dataset to file."""
        try:
            os.makedirs(os.path.dirname(self.dataset_path), exist_ok=True)
            data = {k: asdict(v) for k, v in self.dataset.items()}
            with open(self.dataset_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.dataset)} ground truth records")
        except Exception as e:
            logger.error(f"Failed to save ground truth dataset: {e}")
    
    def add_record(
        self,
        filename: str,
        party: str,
        contract_type: str,
        signed_date: str,
        start_date: str = "",
        end_date: str = "",
        address: str = "",
        country: str = "",
        notes: str = "",
        verified_by: str = "manual"
    ):
        """Add or update a ground truth record."""
        record = GroundTruthRecord(
            filename=filename,
            party=party,
            contract_type=contract_type,
            signed_date=signed_date,
            start_date=start_date,
            end_date=end_date,
            address=address,
            country=country,
            notes=notes,
            created_at=datetime.now().isoformat(),
            verified_by=verified_by
        )
        self.dataset[filename] = record
        self.save_dataset()
        logger.info(f"Added ground truth record: {filename}")
    
    def get_record(self, filename: str) -> Optional[GroundTruthRecord]:
        """Get ground truth record for a file."""
        return self.dataset.get(filename)
    
    def get_all_records(self) -> List[GroundTruthRecord]:
        """Get all ground truth records."""
        return list(self.dataset.values())
    
    def delete_record(self, filename: str):
        """Delete a ground truth record."""
        if filename in self.dataset:
            del self.dataset[filename]
            self.save_dataset()
            logger.info(f"Deleted ground truth record: {filename}")
    
    def import_from_export(self, export_data: List[Dict], verified_by: str = "export"):
        """Import verified records from Excel export."""
        count = 0
        for row in export_data:
            if row.get('is_verified', False):
                self.add_record(
                    filename=row.get('dosya_adi', ''),
                    party=row.get('signing_party', ''),
                    contract_type=row.get('contract_name', ''),
                    signed_date=row.get('signed_date', ''),
                    start_date=row.get('start_date', ''),
                    end_date=row.get('end_date', ''),
                    address=row.get('address', ''),
                    country=row.get('country', ''),
                    notes="Imported from verified export",
                    verified_by=verified_by
                )
                count += 1
        logger.info(f"Imported {count} records from export")
        return count


class AccuracyTester:
    """Test extraction accuracy against ground truth."""
    
    # Field comparison strategies
    EXACT_MATCH_FIELDS = ['signed_date', 'start_date', 'end_date']
    FUZZY_MATCH_FIELDS = ['party', 'contract_type', 'address', 'country']
    
    # Thresholds
    FUZZY_THRESHOLD = 0.85  # 85% similarity for fuzzy match
    PASS_THRESHOLD = 0.80   # 80% accuracy to pass
    
    def __init__(self, ground_truth_manager: GroundTruthManager):
        self.gt_manager = ground_truth_manager
        self.logger = logger
    
    def test_single_file(
        self,
        filename: str,
        extracted_data: Dict
    ) -> TestResult:
        """Test extraction results against ground truth for one file."""
        gt_record = self.gt_manager.get_record(filename)
        
        if not gt_record:
            return TestResult(
                filename=filename,
                passed=False,
                accuracy_score=0.0,
                errors=[f"No ground truth record found for {filename}"]
            )
        
        result = TestResult(filename=filename, passed=False, accuracy_score=0.0)
        
        # Test each field
        fields_to_test = {
            'party': ('signing_party', gt_record.party),
            'contract_type': ('contract_name', gt_record.contract_type),
            'signed_date': ('signed_date', gt_record.signed_date),
            'start_date': ('start_date', gt_record.start_date),
            'end_date': ('end_date', gt_record.end_date),
            'address': ('address', gt_record.address),
            'country': ('country', gt_record.country),
        }
        
        total_score = 0.0
        field_count = 0
        
        for field_name, (extract_key, ground_truth_value) in fields_to_test.items():
            # Skip empty ground truth fields
            if not ground_truth_value or ground_truth_value.strip() == '':
                continue
            
            field_count += 1
            extracted_value = extracted_data.get(extract_key, '')
            
            # Compare
            if field_name in self.EXACT_MATCH_FIELDS:
                match_score, is_match = self._exact_match(extracted_value, ground_truth_value)
            else:
                match_score, is_match = self._fuzzy_match(extracted_value, ground_truth_value)
            
            total_score += match_score
            
            result.field_results[field_name] = {
                'expected': ground_truth_value,
                'extracted': extracted_value,
                'match_score': match_score,
                'passed': is_match
            }
            
            if not is_match:
                result.errors.append(
                    f"{field_name}: expected '{ground_truth_value}', got '{extracted_value}'"
                )
            elif match_score < 100:
                result.warnings.append(
                    f"{field_name}: partial match ({match_score:.1f}%)"
                )
        
        # Calculate overall accuracy
        if field_count > 0:
            result.accuracy_score = total_score / field_count
        else:
            result.accuracy_score = 0.0
        
        result.passed = result.accuracy_score >= (self.PASS_THRESHOLD * 100)
        
        return result
    
    def _exact_match(self, extracted: str, ground_truth: str) -> Tuple[float, bool]:
        """Check for exact match."""
        extracted = str(extracted).strip().lower()
        ground_truth = str(ground_truth).strip().lower()
        
        if extracted == ground_truth:
            return 100.0, True
        else:
            return 0.0, False
    
    def _fuzzy_match(self, extracted: str, ground_truth: str) -> Tuple[float, bool]:
        """Check for fuzzy match using string similarity."""
        extracted = str(extracted).strip().lower()
        ground_truth = str(ground_truth).strip().lower()
        
        if not extracted or not ground_truth:
            return 0.0, False
        
        # Use difflib for similarity
        similarity = difflib.SequenceMatcher(None, extracted, ground_truth).ratio()
        score = similarity * 100
        
        is_match = similarity >= self.FUZZY_THRESHOLD
        
        return score, is_match
    
    def run_regression_tests(
        self,
        extraction_results: List[Dict]
    ) -> TestSummary:
        """
        Run full regression test suite.
        
        Args:
            extraction_results: List of extraction results from pipeline
        
        Returns:
            TestSummary with detailed results
        """
        start_time = time.time()
        
        test_results = []
        for result in extraction_results:
            filename = result.get('dosya_adi', '')
            if self.gt_manager.get_record(filename):
                test_result = self.test_single_file(filename, result)
                test_results.append(test_result)
        
        # Calculate summary
        total = len(test_results)
        passed = sum(1 for r in test_results if r.passed)
        failed = total - passed
        
        avg_accuracy = sum(r.accuracy_score for r in test_results) / total if total > 0 else 0.0
        
        # Field-level accuracy
        field_accuracy = {}
        field_names = ['party', 'contract_type', 'signed_date', 'start_date', 'end_date', 'address', 'country']
        
        for field in field_names:
            field_scores = [
                r.field_results[field]['match_score']
                for r in test_results
                if field in r.field_results
            ]
            if field_scores:
                field_accuracy[field] = sum(field_scores) / len(field_scores)
        
        summary = TestSummary(
            total_files=total,
            passed=passed,
            failed=failed,
            average_accuracy=avg_accuracy,
            field_accuracy=field_accuracy,
            total_time=time.time() - start_time,
            timestamp=datetime.now().isoformat()
        )
        
        # Log results
        self.logger.info("=" * 60)
        self.logger.info("REGRESSION TEST RESULTS")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files tested: {total}")
        self.logger.info(f"Passed: {passed} ({passed/total*100:.1f}%)")
        self.logger.info(f"Failed: {failed} ({failed/total*100:.1f}%)")
        self.logger.info(f"Average accuracy: {avg_accuracy:.2f}%")
        self.logger.info("\nField-level accuracy:")
        for field, acc in field_accuracy.items():
            self.logger.info(f"  {field}: {acc:.2f}%")
        self.logger.info(f"Total time: {summary.total_time:.2f}s")
        self.logger.info("=" * 60)
        
        # Log failures
        if failed > 0:
            self.logger.warning("\nFailed tests:")
            for result in test_results:
                if not result.passed:
                    self.logger.warning(f"\n{result.filename} ({result.accuracy_score:.1f}%):")
                    for error in result.errors:
                        self.logger.warning(f"  - {error}")
        
        return summary
    
    def export_test_report(self, summary: TestSummary, output_path: str = "tests/test_report.json"):
        """Export test report to JSON."""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(summary), f, indent=2, ensure_ascii=False)
            self.logger.info(f"Test report exported to {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to export test report: {e}")


# Convenience functions
def create_ground_truth_from_verified_export(export_path: str) -> int:
    """
    Create ground truth dataset from verified Excel export.
    
    Args:
        export_path: Path to Excel file with verified data
    
    Returns:
        Number of records imported
    """
    import pandas as pd
    
    df = pd.read_excel(export_path)
    records = df.to_dict('records')
    
    gt_manager = GroundTruthManager()
    count = gt_manager.import_from_export(records)
    
    return count


def run_tests_from_results(results: List[Dict]) -> TestSummary:
    """
    Run automated tests on extraction results.
    
    Args:
        results: List of extraction results from pipeline
    
    Returns:
        TestSummary with detailed accuracy metrics
    """
    gt_manager = GroundTruthManager()
    tester = AccuracyTester(gt_manager)
    summary = tester.run_regression_tests(results)
    tester.export_test_report(summary)
    
    return summary
