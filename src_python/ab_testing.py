"""
A/B Testing framework for prompt optimization.
Tests different prompt variations and tracks performance.
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from models import Contract, Correction
from logger import logger


@dataclass
class PromptVariant:
    """A prompt variation for A/B testing."""
    id: str
    name: str
    template: str
    description: str
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class TestMetrics:
    """Performance metrics for a prompt variant."""
    variant_id: str
    total_contracts: int = 0
    avg_confidence: float = 0.0
    avg_processing_time_ms: float = 0.0
    correction_rate: float = 0.0  # % of contracts that needed corrections
    field_accuracy: Dict[str, float] = field(default_factory=dict)
    error_count: int = 0
    review_rate: float = 0.0  # % flagged for review


@dataclass
class ABTestResult:
    """Result of A/B test comparison."""
    winner: str
    metrics: Dict[str, TestMetrics]
    confidence_level: float  # Statistical confidence
    recommendation: str
    test_duration_days: int


class ABTestManager:
    """Manage A/B testing for prompt optimization."""
    
    def __init__(self, db: Session, config_path: str = "data/ab_test_config.json"):
        self.db = db
        self.config_path = config_path
        self.variants = {}
        self.active_test = None
        self._load_config()
    
    def _load_config(self):
        """Load A/B test configuration."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.variants = {v['id']: PromptVariant(**v) for v in data.get('variants', [])}
                self.active_test = data.get('active_test')
                logger.info(f"Loaded {len(self.variants)} prompt variants")
        except FileNotFoundError:
            logger.warning(f"A/B test config not found: {self.config_path}")
            self._create_default_config()
    
    def _save_config(self):
        """Save A/B test configuration."""
        import os
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        data = {
            'variants': [asdict(v) for v in self.variants.values()],
            'active_test': self.active_test,
            'last_updated': datetime.utcnow().isoformat()
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _create_default_config(self):
        """Create default prompt variants."""
        variants = [
            PromptVariant(
                id="v1_standard",
                name="Standard Prompt",
                template="standard",
                description="Original prompt template with basic instructions"
            ),
            PromptVariant(
                id="v2_detailed",
                name="Detailed Prompt",
                template="detailed",
                description="More detailed instructions with examples"
            ),
            PromptVariant(
                id="v3_structured",
                name="Structured Prompt",
                template="structured",
                description="Highly structured with step-by-step guidance"
            ),
            PromptVariant(
                id="v4_concise",
                name="Concise Prompt",
                template="concise",
                description="Minimal, focused instructions"
            )
        ]
        
        self.variants = {v.id: v for v in variants}
        self._save_config()
        logger.info("Created default A/B test variants")
    
    def add_variant(
        self,
        variant_id: str,
        name: str,
        template: str,
        description: str
    ) -> PromptVariant:
        """Add a new prompt variant."""
        variant = PromptVariant(
            id=variant_id,
            name=name,
            template=template,
            description=description
        )
        
        self.variants[variant_id] = variant
        self._save_config()
        
        logger.info(f"Added variant: {variant_id}")
        return variant
    
    def get_variant_for_contract(self, contract_id: int) -> str:
        """
        Get which variant to use for a contract (round-robin or random).
        
        For A/B testing, we want even distribution.
        """
        if not self.active_test:
            return "v1_standard"  # Default
        
        # Get active variants
        active_variants = [v.id for v in self.variants.values() if v.is_active]
        
        if not active_variants:
            return "v1_standard"
        
        # Round-robin based on contract ID
        variant_index = contract_id % len(active_variants)
        return active_variants[variant_index]
    
    def track_contract_processing(
        self,
        contract_id: int,
        variant_id: str,
        confidence: float,
        processing_time_ms: int,
        needs_review: bool,
        had_errors: bool = False
    ):
        """
        Track which variant was used for a contract.
        
        In production, this would be stored in database.
        For now, we infer from existing data.
        """
        # This is a placeholder - in production, store variant_id in Contract model
        pass
    
    def calculate_metrics(
        self,
        variant_id: str,
        days: int = 7
    ) -> TestMetrics:
        """
        Calculate performance metrics for a variant.
        
        Note: Without variant tracking in DB, this uses overall stats.
        In production, filter by variant_id.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get contracts (in production, filter by variant_id)
        contracts = self.db.query(Contract).filter(
            Contract.islenme_zamani >= cutoff_date
        ).all()
        
        if not contracts:
            return TestMetrics(variant_id=variant_id)
        
        total = len(contracts)
        
        # Calculate metrics
        avg_confidence = sum(c.confidence_score or 0 for c in contracts) / total
        review_count = sum(1 for c in contracts if c.needs_review)
        review_rate = (review_count / total * 100) if total > 0 else 0
        
        # Get corrections
        contract_ids = [c.id for c in contracts]
        corrections = self.db.query(Correction).filter(
            Correction.contract_id.in_(contract_ids)
        ).all()
        
        corrected_contracts = set(c.contract_id for c in corrections)
        correction_rate = (len(corrected_contracts) / total * 100) if total > 0 else 0
        
        # Field accuracy (from corrections)
        field_corrections = defaultdict(int)
        for correction in corrections:
            field_corrections[correction.field_name] += 1
        
        field_accuracy = {}
        for field in ['signing_party', 'address', 'country', 'signed_date']:
            error_count = field_corrections.get(field, 0)
            accuracy = ((total - error_count) / total * 100) if total > 0 else 0
            field_accuracy[field] = accuracy
        
        return TestMetrics(
            variant_id=variant_id,
            total_contracts=total,
            avg_confidence=avg_confidence,
            correction_rate=correction_rate,
            review_rate=review_rate,
            field_accuracy=field_accuracy,
            error_count=len(corrections)
        )
    
    def run_ab_test(
        self,
        variant_ids: List[str],
        duration_days: int = 7,
        min_samples: int = 30
    ) -> ABTestResult:
        """
        Run A/B test and determine winner.
        
        Args:
            variant_ids: List of variant IDs to compare
            duration_days: How many days of data to analyze
            min_samples: Minimum contracts needed per variant
        
        Returns:
            ABTestResult with winner and metrics
        """
        logger.info(f"Running A/B test: {variant_ids} ({duration_days} days)")
        
        # Calculate metrics for each variant
        metrics = {}
        for variant_id in variant_ids:
            metrics[variant_id] = self.calculate_metrics(variant_id, duration_days)
        
        # Check if we have enough samples
        for variant_id, m in metrics.items():
            if m.total_contracts < min_samples:
                logger.warning(
                    f"Variant {variant_id} has only {m.total_contracts} contracts "
                    f"(min: {min_samples}). Results may not be statistically significant."
                )
        
        # Determine winner based on composite score
        scores = {}
        for variant_id, m in metrics.items():
            # Composite score (weighted)
            score = (
                m.avg_confidence * 0.4 +           # 40% weight on confidence
                (100 - m.correction_rate) * 0.3 +  # 30% weight on accuracy
                (100 - m.review_rate) * 0.2 +      # 20% weight on auto-approval
                (100 - m.error_count) * 0.1        # 10% weight on error reduction
            )
            scores[variant_id] = score
        
        winner = max(scores, key=scores.get)
        winner_score = scores[winner]
        
        # Calculate confidence level (simple heuristic)
        second_best = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
        confidence = min(100, (winner_score - second_best) * 2)
        
        # Generate recommendation
        winner_metrics = metrics[winner]
        recommendation = self._generate_recommendation(winner, winner_metrics, confidence)
        
        result = ABTestResult(
            winner=winner,
            metrics=metrics,
            confidence_level=confidence,
            recommendation=recommendation,
            test_duration_days=duration_days
        )
        
        # Log results
        logger.info("=" * 60)
        logger.info("A/B TEST RESULTS")
        logger.info("=" * 60)
        logger.info(f"Winner: {winner} (confidence: {confidence:.1f}%)")
        logger.info(f"\nMetrics Comparison:")
        for variant_id, m in metrics.items():
            indicator = "🏆" if variant_id == winner else "  "
            logger.info(f"{indicator} {variant_id}:")
            logger.info(f"    Avg Confidence: {m.avg_confidence:.1f}%")
            logger.info(f"    Correction Rate: {m.correction_rate:.1f}%")
            logger.info(f"    Review Rate: {m.review_rate:.1f}%")
            logger.info(f"    Total Contracts: {m.total_contracts}")
        logger.info(f"\nRecommendation: {recommendation}")
        logger.info("=" * 60)
        
        return result
    
    def _generate_recommendation(
        self,
        winner_id: str,
        metrics: TestMetrics,
        confidence: float
    ) -> str:
        """Generate recommendation based on test results."""
        variant = self.variants[winner_id]
        
        if confidence >= 80:
            return (
                f"STRONG: Deploy {variant.name} to production. "
                f"Significant improvement with {confidence:.1f}% confidence."
            )
        elif confidence >= 60:
            return (
                f"MODERATE: {variant.name} shows promise ({confidence:.1f}% confidence). "
                f"Consider extending test or increasing sample size."
            )
        elif confidence >= 40:
            return (
                f"WEAK: No clear winner ({confidence:.1f}% confidence). "
                f"Variants perform similarly. Consider testing new variations."
            )
        else:
            return (
                f"INCONCLUSIVE: Results are too close ({confidence:.1f}% confidence). "
                f"Need more data or different variants."
            )
    
    def get_active_variants(self) -> List[PromptVariant]:
        """Get list of active variants."""
        return [v for v in self.variants.values() if v.is_active]
    
    def set_variant_active(self, variant_id: str, active: bool):
        """Enable or disable a variant."""
        if variant_id in self.variants:
            self.variants[variant_id].is_active = active
            self._save_config()
            logger.info(f"Variant {variant_id} set to {'active' if active else 'inactive'}")


# Convenience functions
def run_prompt_ab_test(
    db: Session,
    variant_ids: Optional[List[str]] = None,
    days: int = 7
) -> ABTestResult:
    """
    Run A/B test on prompt variants.
    
    Args:
        db: Database session
        variant_ids: Variants to test (None = all active)
        days: Days of data to analyze
    
    Returns:
        ABTestResult with winner
    """
    manager = ABTestManager(db)
    
    if variant_ids is None:
        variant_ids = [v.id for v in manager.get_active_variants()]
    
    if len(variant_ids) < 2:
        logger.error("Need at least 2 variants for A/B test")
        return None
    
    return manager.run_ab_test(variant_ids, duration_days=days)


def get_best_prompt_variant(db: Session) -> str:
    """
    Get the best performing prompt variant based on recent data.
    
    Returns:
        Variant ID of best performer
    """
    manager = ABTestManager(db)
    active_variants = [v.id for v in manager.get_active_variants()]
    
    if len(active_variants) < 2:
        return "v1_standard"
    
    result = manager.run_ab_test(active_variants, duration_days=7)
    return result.winner if result else "v1_standard"


# Example usage
if __name__ == "__main__":
    from database import SessionLocal
    
    db = SessionLocal()
    
    # Run A/B test
    result = run_prompt_ab_test(
        db,
        variant_ids=["v1_standard", "v2_detailed", "v3_structured"],
        days=7
    )
    
    if result:
        print(f"\n🏆 Winner: {result.winner}")
        print(f"📊 Confidence: {result.confidence_level:.1f}%")
        print(f"💡 Recommendation: {result.recommendation}")
        
        print("\n📈 Metrics:")
        for variant_id, metrics in result.metrics.items():
            print(f"\n{variant_id}:")
            print(f"  Confidence: {metrics.avg_confidence:.1f}%")
            print(f"  Corrections: {metrics.correction_rate:.1f}%")
            print(f"  Review Rate: {metrics.review_rate:.1f}%")
    
    db.close()
