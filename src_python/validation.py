"""
Multi-stage validation and confidence scoring system.
Provides comprehensive quality checks for extracted contract data.
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from logger import logger


@dataclass
class ValidationResult:
    """Result of a validation check."""
    field_name: str
    is_valid: bool
    confidence: float  # 0-100
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    score_adjustments: Dict[str, float] = field(default_factory=dict)


@dataclass
class FieldValidation:
    """Complete validation result for all fields."""
    results: Dict[str, ValidationResult] = field(default_factory=dict)
    overall_confidence: float = 0.0
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str = ""


class ContractValidator:
    """Multi-stage validator for contract data."""
    
    # Confidence thresholds
    EXCELLENT_THRESHOLD = 90
    GOOD_THRESHOLD = 75
    ACCEPTABLE_THRESHOLD = 60
    REVIEW_THRESHOLD = 50
    
    # Known country list for validation
    VALID_COUNTRIES = {
        'Turkey', 'Türkiye', 'Germany', 'USA', 'United States', 'UK', 'United Kingdom',
        'France', 'Italy', 'Spain', 'Netherlands', 'Belgium', 'Switzerland', 'Austria',
        'Poland', 'Sweden', 'Norway', 'Denmark', 'Finland', 'Greece', 'Portugal',
        'China', 'Japan', 'South Korea', 'India', 'Singapore', 'Malaysia', 'Thailand',
        'UAE', 'Saudi Arabia', 'Qatar', 'Egypt', 'South Africa', 'Canada', 'Mexico',
        'Brazil', 'Argentina', 'Australia', 'New Zealand', 'Russia', 'Ukraine'
    }
    
    def __init__(self):
        self.logger = logger
    
    def validate_all_fields(
        self,
        party: str,
        contract_type: str,
        signed_date: str,
        start_date: str,
        end_date: str,
        address: str,
        country: str,
        initial_confidence: float,
        ocr_quality: float = 50.0,
        llm_confidence: float = 50.0
    ) -> FieldValidation:
        """
        Run all validation checks on extracted fields.
        
        Returns:
            FieldValidation with detailed results for each field
        """
        validation = FieldValidation()
        
        # Stage 1: Individual field validation
        validation.results['party'] = self._validate_party(party)
        validation.results['contract_type'] = self._validate_contract_type(contract_type)
        validation.results['signed_date'] = self._validate_date(signed_date, 'signed_date')
        validation.results['start_date'] = self._validate_date(start_date, 'start_date')
        validation.results['end_date'] = self._validate_date(end_date, 'end_date')
        validation.results['address'] = self._validate_address(address)
        validation.results['country'] = self._validate_country(country)
        
        # Stage 2: Cross-field validation
        cross_validation = self._validate_cross_fields(
            signed_date, start_date, end_date, address, country
        )
        validation.results['cross_validation'] = cross_validation
        
        # Stage 3: OCR quality check
        validation.results['ocr_quality'] = ValidationResult(
            field_name='ocr_quality',
            is_valid=ocr_quality >= 60,
            confidence=ocr_quality,
            issues=[] if ocr_quality >= 60 else ['Low OCR quality detected'],
            warnings=[] if ocr_quality >= 75 else ['OCR quality could be improved']
        )
        
        # Stage 4: LLM confidence check
        validation.results['llm_confidence'] = ValidationResult(
            field_name='llm_confidence',
            is_valid=llm_confidence >= 50,
            confidence=llm_confidence,
            issues=[] if llm_confidence >= 50 else ['Low LLM confidence'],
            warnings=[] if llm_confidence >= 70 else ['LLM confidence could be better']
        )
        
        # Stage 5: Anomaly detection
        anomalies = self._detect_anomalies(
            party, contract_type, signed_date, address, country
        )
        validation.results['anomaly_detection'] = anomalies
        
        # Calculate overall confidence
        validation.overall_confidence = self._calculate_overall_confidence(
            validation.results, initial_confidence, ocr_quality, llm_confidence
        )
        
        # Collect critical issues and warnings
        for result in validation.results.values():
            validation.critical_issues.extend(result.issues)
            validation.warnings.extend(result.warnings)
        
        # Determine if manual review is needed
        validation.needs_review = self._should_review(validation)
        if validation.needs_review:
            validation.review_reason = self._get_review_reason(validation)
        
        self.logger.info(
            f"Validation complete: confidence={validation.overall_confidence:.1f}%, "
            f"issues={len(validation.critical_issues)}, warnings={len(validation.warnings)}, "
            f"needs_review={validation.needs_review}"
        )
        
        return validation
    
    def _validate_party(self, party: str) -> ValidationResult:
        """Validate party/company name."""
        issues = []
        warnings = []
        confidence = 100.0
        
        if not party or len(party.strip()) < 2:
            issues.append("Party name is empty or too short")
            confidence = 0.0
        elif len(party) < 5:
            warnings.append("Party name seems very short")
            confidence = 50.0
        elif party.lower() in ['unknown', 'n/a', 'null', 'none']:
            issues.append("Party name is placeholder")
            confidence = 10.0
        elif re.search(r'\d{5,}', party):
            warnings.append("Party name contains long number sequence")
            confidence = 70.0
        
        return ValidationResult(
            field_name='party',
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _validate_contract_type(self, contract_type: str) -> ValidationResult:
        """Validate contract type."""
        issues = []
        warnings = []
        confidence = 100.0
        
        if not contract_type or len(contract_type.strip()) < 3:
            issues.append("Contract type is empty or too short")
            confidence = 0.0
        elif contract_type.lower() in ['unknown', 'n/a', 'null', 'other']:
            warnings.append("Contract type is generic/placeholder")
            confidence = 40.0
        
        return ValidationResult(
            field_name='contract_type',
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _validate_date(self, date_str: str, field_name: str) -> ValidationResult:
        """Validate date format and reasonableness."""
        issues = []
        warnings = []
        confidence = 100.0
        
        if not date_str or date_str.strip() == '':
            issues.append(f"{field_name} is empty")
            return ValidationResult(
                field_name=field_name,
                is_valid=False,
                confidence=0.0,
                issues=issues,
                warnings=warnings
            )
        
        # Check format
        try:
            parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            issues.append(f"{field_name} has invalid format (expected YYYY-MM-DD)")
            return ValidationResult(
                field_name=field_name,
                is_valid=False,
                confidence=0.0,
                issues=issues,
                warnings=warnings
            )
        
        # Check reasonableness
        current_year = datetime.now().year
        year = parsed_date.year
        
        if year < 1950:
            issues.append(f"{field_name} year is too old ({year})")
            confidence = 20.0
        elif year < 1990:
            warnings.append(f"{field_name} year seems old ({year})")
            confidence = 60.0
        elif year > current_year + 10:
            issues.append(f"{field_name} year is too far in future ({year})")
            confidence = 30.0
        elif year > current_year + 5:
            warnings.append(f"{field_name} year is far in future ({year})")
            confidence = 70.0
        
        # Check for default dates (01-01)
        if parsed_date.month == 1 and parsed_date.day == 1:
            warnings.append(f"{field_name} is Jan 1 (might be default/placeholder)")
            confidence = min(confidence, 80.0)
        
        return ValidationResult(
            field_name=field_name,
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _validate_address(self, address: str) -> ValidationResult:
        """Validate address field."""
        issues = []
        warnings = []
        confidence = 100.0
        
        if not address or len(address.strip()) < 5:
            issues.append("Address is empty or too short")
            confidence = 0.0
        elif len(address) < 15:
            warnings.append("Address seems incomplete")
            confidence = 60.0
        elif address.lower() in ['unknown', 'n/a', 'null']:
            issues.append("Address is placeholder")
            confidence = 10.0
        
        return ValidationResult(
            field_name='address',
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _validate_country(self, country: str) -> ValidationResult:
        """Validate country field."""
        issues = []
        warnings = []
        confidence = 100.0
        
        if not country or len(country.strip()) < 2:
            issues.append("Country is empty")
            confidence = 0.0
        elif country not in self.VALID_COUNTRIES:
            warnings.append(f"Country '{country}' not in known list")
            confidence = 70.0
        
        return ValidationResult(
            field_name='country',
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _validate_cross_fields(
        self,
        signed_date: str,
        start_date: str,
        end_date: str,
        address: str,
        country: str
    ) -> ValidationResult:
        """Validate logical consistency across fields."""
        issues = []
        warnings = []
        confidence = 100.0
        
        # Date order validation
        try:
            if signed_date and start_date:
                signed = datetime.strptime(signed_date, '%Y-%m-%d')
                start = datetime.strptime(start_date, '%Y-%m-%d')
                
                if signed > start:
                    warnings.append("Signed date is after start date")
                    confidence = min(confidence, 80.0)
                
                # Very large gap
                if (start - signed).days > 365:
                    warnings.append("Large gap between signed and start date")
                    confidence = min(confidence, 85.0)
            
            if start_date and end_date:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d')
                
                if end <= start:
                    issues.append("End date is before or equal to start date")
                    confidence = min(confidence, 40.0)
                
                # Check contract duration
                duration_days = (end - start).days
                if duration_days < 30:
                    warnings.append(f"Very short contract duration ({duration_days} days)")
                    confidence = min(confidence, 75.0)
                elif duration_days > 3650:  # 10 years
                    warnings.append(f"Very long contract duration ({duration_days // 365} years)")
                    confidence = min(confidence, 80.0)
        
        except ValueError:
            # Date parsing errors already caught in individual validation
            pass
        
        # Address-Country consistency
        if address and country:
            # Simple heuristic: check if country name appears in address
            if country.lower() not in address.lower():
                # Not an error, but worth noting
                pass
        
        return ValidationResult(
            field_name='cross_validation',
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _detect_anomalies(
        self,
        party: str,
        contract_type: str,
        signed_date: str,
        address: str,
        country: str
    ) -> ValidationResult:
        """Detect unusual patterns that might indicate errors."""
        issues = []
        warnings = []
        confidence = 100.0
        
        # Check for repeated characters
        if party and re.search(r'(.)\1{4,}', party):
            warnings.append("Party name has repeated characters")
            confidence = min(confidence, 70.0)
        
        # Check for all caps (might be OCR error)
        if party and len(party) > 10 and party.isupper():
            warnings.append("Party name is all uppercase (possible OCR issue)")
            confidence = min(confidence, 85.0)
        
        # Check for special characters
        if party and re.search(r'[^\w\s\-\.\,\&]', party):
            warnings.append("Party name contains unusual characters")
            confidence = min(confidence, 80.0)
        
        # Check for numbers in contract type (unusual)
        if contract_type and re.search(r'\d', contract_type):
            warnings.append("Contract type contains numbers")
            confidence = min(confidence, 85.0)
        
        # Check for very short address with country
        if address and country and len(address) < 20:
            warnings.append("Address is very short despite having country")
            confidence = min(confidence, 75.0)
        
        return ValidationResult(
            field_name='anomaly_detection',
            is_valid=len(issues) == 0,
            confidence=confidence,
            issues=issues,
            warnings=warnings
        )
    
    def _calculate_overall_confidence(
        self,
        results: Dict[str, ValidationResult],
        initial_confidence: float,
        ocr_quality: float,
        llm_confidence: float
    ) -> float:
        """Calculate weighted overall confidence score."""
        weights = {
            'party': 0.20,
            'contract_type': 0.15,
            'signed_date': 0.15,
            'start_date': 0.10,
            'end_date': 0.10,
            'address': 0.10,
            'country': 0.10,
            'cross_validation': 0.05,
            'ocr_quality': 0.025,
            'llm_confidence': 0.025
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for field, weight in weights.items():
            if field in results:
                weighted_sum += results[field].confidence * weight
                total_weight += weight
        
        if total_weight > 0:
            base_confidence = weighted_sum / total_weight
        else:
            base_confidence = initial_confidence
        
        # Apply penalties for issues
        issue_count = sum(len(r.issues) for r in results.values())
        warning_count = sum(len(r.warnings) for r in results.values())
        
        penalty = (issue_count * 5) + (warning_count * 2)
        final_confidence = max(0.0, base_confidence - penalty)
        
        return round(final_confidence, 2)
    
    def _should_review(self, validation: FieldValidation) -> bool:
        """Determine if this contract needs manual review."""
        # Low confidence
        if validation.overall_confidence < self.REVIEW_THRESHOLD:
            return True
        
        # Critical issues
        if len(validation.critical_issues) > 0:
            return True
        
        # Multiple warnings
        if len(validation.warnings) >= 5:
            return True
        
        # Specific field failures
        critical_fields = ['party', 'signed_date', 'contract_type']
        for field in critical_fields:
            if field in validation.results:
                result = validation.results[field]
                if not result.is_valid or result.confidence < 50:
                    return True
        
        return False
    
    def _get_review_reason(self, validation: FieldValidation) -> str:
        """Get human-readable reason for review requirement."""
        reasons = []
        
        if validation.overall_confidence < self.REVIEW_THRESHOLD:
            reasons.append(f"Low confidence ({validation.overall_confidence:.1f}%)")
        
        if len(validation.critical_issues) > 0:
            reasons.append(f"{len(validation.critical_issues)} critical issues")
        
        if len(validation.warnings) >= 5:
            reasons.append(f"{len(validation.warnings)} warnings")
        
        # Check critical fields
        for field in ['party', 'signed_date', 'contract_type']:
            if field in validation.results:
                result = validation.results[field]
                if not result.is_valid:
                    reasons.append(f"Invalid {field}")
        
        return "; ".join(reasons) if reasons else "Unknown"
    
    def get_confidence_label(self, confidence: float) -> str:
        """Get human-readable confidence label."""
        if confidence >= self.EXCELLENT_THRESHOLD:
            return "Excellent"
        elif confidence >= self.GOOD_THRESHOLD:
            return "Good"
        elif confidence >= self.ACCEPTABLE_THRESHOLD:
            return "Acceptable"
        elif confidence >= self.REVIEW_THRESHOLD:
            return "Low"
        else:
            return "Very Low"
    
    def get_confidence_color(self, confidence: float) -> str:
        """Get color code for confidence level (for UI)."""
        if confidence >= self.EXCELLENT_THRESHOLD:
            return "#10b981"  # green
        elif confidence >= self.GOOD_THRESHOLD:
            return "#3b82f6"  # blue
        elif confidence >= self.ACCEPTABLE_THRESHOLD:
            return "#f59e0b"  # orange
        else:
            return "#ef4444"  # red


# Convenience function
def validate_contract(
    party: str,
    contract_type: str,
    signed_date: str,
    start_date: str,
    end_date: str,
    address: str,
    country: str,
    initial_confidence: float = 50.0,
    ocr_quality: float = 50.0,
    llm_confidence: float = 50.0
) -> FieldValidation:
    """
    Validate all contract fields and return comprehensive results.
    
    This is the main entry point for validation.
    """
    validator = ContractValidator()
    return validator.validate_all_fields(
        party=party,
        contract_type=contract_type,
        signed_date=signed_date,
        start_date=start_date,
        end_date=end_date,
        address=address,
        country=country,
        initial_confidence=initial_confidence,
        ocr_quality=ocr_quality,
        llm_confidence=llm_confidence
    )
