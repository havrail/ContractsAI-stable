import redis
import json
import hashlib
from typing import Optional, Any
from logger import logger
import os

# Redis connection
REDIS_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


class RedisCache:
    """Multi-level caching for OCR and LLM results."""
    
    def __init__(self):
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            self.enabled = True
            logger.info(f"Redis cache initialized: {REDIS_URL}")
        except Exception as e:
            self.enabled = False
            logger.warning(f"Redis cache disabled: {e}")
    
    def _make_key(self, prefix: str, data: str) -> str:
        """Create cache key from data hash."""
        hash_obj = hashlib.sha256(data.encode('utf-8'))
        return f"{prefix}:{hash_obj.hexdigest()[:16]}"
    
    def get_ocr_result(self, cache_key: str) -> Optional[str]:
        """Get cached OCR result for file (hash or path)."""
        if not self.enabled:
            return None
        
        try:
            key = self._make_key("ocr", cache_key)
            result = self.redis_client.get(key)
            if result:
                logger.info("OCR cache HIT")
                return result
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        
        return None
    
    def set_ocr_result(self, cache_key: str, ocr_text: str):
        """Cache OCR result."""
        if not self.enabled or not ocr_text:
            return
        
        try:
            key = self._make_key("ocr", cache_key)
            self.redis_client.setex(key, CACHE_TTL, ocr_text)
            logger.info("OCR cached")
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    def get_llm_result(self, cache_key: str) -> Optional[dict]:
        """Get cached LLM analysis result."""
        if not self.enabled:
            return None
        
        try:
            key = self._make_key("llm", cache_key)
            result = self.redis_client.get(key)
            if result:
                logger.info("LLM cache HIT")
                return json.loads(result)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        
        return None
    
    def set_llm_result(self, cache_key: str, analysis: dict):
        """Cache LLM analysis result."""
        if not self.enabled or not analysis:
            return
        
        try:
            key = self._make_key("llm", cache_key)
            self.redis_client.setex(key, CACHE_TTL, json.dumps(analysis))
            logger.info("LLM result cached")
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        if not self.enabled:
            return {"enabled": False}
        
        try:
            info = self.redis_client.info('stats')
            ocr_keys = len(self.redis_client.keys("ocr:*"))
            llm_keys = len(self.redis_client.keys("llm:*"))
            
            return {
                "enabled": True,
                "ocr_keys": ocr_keys,
                "llm_keys": llm_keys,
                "total_keys": ocr_keys + llm_keys,
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
            }
        except Exception as e:
            logger.error(f"Redis stats error: {e}")
            return {"enabled": True, "error": str(e)}
    
    def clear_all(self):
        """Clear all cache (use with caution)."""
        if not self.enabled:
            return
        
        try:
            ocr_deleted = len(self.redis_client.keys("ocr:*"))
            llm_deleted = len(self.redis_client.keys("llm:*"))
            
            for key in self.redis_client.keys("ocr:*"):
                self.redis_client.delete(key)
            for key in self.redis_client.keys("llm:*"):
                self.redis_client.delete(key)
            
            logger.info(f"Cache cleared: {ocr_deleted} OCR + {llm_deleted} LLM keys")
            return {"ocr_deleted": ocr_deleted, "llm_deleted": llm_deleted}
        except Exception as e:
            logger.error(f"Redis clear error: {e}")
            return {"error": str(e)}


# Global cache instance
cache = RedisCache()
