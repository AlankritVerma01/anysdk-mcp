# anysdk-mcp/mcp_sdk_bridge/core/paginate.py

"""
Pagination Module

Handles pagination for SDK methods that return large datasets.
"""

from typing import Any, Dict, List, Optional, AsyncIterator, Iterator, Callable
from dataclasses import dataclass
import asyncio
from .serialize import ResponseSerializer


@dataclass
class PaginationConfig:
    """Configuration for pagination"""
    page_size: int = 100
    max_pages: int = 10
    page_param: str = "page"
    size_param: str = "per_page"
    offset_param: Optional[str] = None
    cursor_param: Optional[str] = None


@dataclass
class PaginatedResult:
    """Result of a paginated operation"""
    items: List[Any]
    page: int
    per_page: int
    total: Optional[int] = None
    has_more: bool = False
    next_cursor: Optional[str] = None
    next_page: Optional[int] = None


class PaginationHandler:
    """Handles pagination for SDK methods"""
    
    def __init__(self, serializer: Optional[ResponseSerializer] = None):
        self.serializer = serializer or ResponseSerializer()
    
    def paginate_sync(self, 
                     method: Callable,
                     config: PaginationConfig,
                     **kwargs) -> Iterator[PaginatedResult]:
        """Paginate a synchronous method"""
        page = 1
        
        while page <= config.max_pages:
            # Prepare pagination parameters
            page_kwargs = self._prepare_page_kwargs(config, page, kwargs)
            
            try:
                result = method(**page_kwargs)
                paginated_result = self._process_result(result, page, config)
                
                yield paginated_result
                
                if not paginated_result.has_more:
                    break
                    
                page += 1
                
            except Exception as e:
                # Yield error result
                yield PaginatedResult(
                    items=[{"error": str(e)}],
                    page=page,
                    per_page=config.page_size,
                    has_more=False
                )
                break
    
    async def paginate_async(self,
                            method: Callable,
                            config: PaginationConfig,
                            **kwargs) -> AsyncIterator[PaginatedResult]:
        """Paginate an asynchronous method"""
        page = 1
        
        while page <= config.max_pages:
            # Prepare pagination parameters
            page_kwargs = self._prepare_page_kwargs(config, page, kwargs)
            
            try:
                result = await method(**page_kwargs)
                paginated_result = self._process_result(result, page, config)
                
                yield paginated_result
                
                if not paginated_result.has_more:
                    break
                    
                page += 1
                
            except Exception as e:
                # Yield error result
                yield PaginatedResult(
                    items=[{"error": str(e)}],
                    page=page,
                    per_page=config.page_size,
                    has_more=False
                )
                break
    
    def _prepare_page_kwargs(self, 
                           config: PaginationConfig, 
                           page: int, 
                           base_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare kwargs for a specific page"""
        kwargs = base_kwargs.copy()
        
        # Add page parameter
        kwargs[config.page_param] = page
        kwargs[config.size_param] = config.page_size
        
        # Handle offset-based pagination
        if config.offset_param:
            offset = (page - 1) * config.page_size
            kwargs[config.offset_param] = offset
        
        return kwargs
    
    def _process_result(self, 
                       result: Any, 
                       page: int, 
                       config: PaginationConfig) -> PaginatedResult:
        """Process the result from SDK method"""
        # Try to extract items from different result formats
        items = self._extract_items(result)
        
        # Try to determine if there are more pages
        has_more = self._determine_has_more(result, items, config)
        
        # Try to extract total count
        total = self._extract_total(result)
        
        return PaginatedResult(
            items=items,
            page=page,
            per_page=config.page_size,
            total=total,
            has_more=has_more,
            next_page=page + 1 if has_more else None
        )
    
    def _extract_items(self, result: Any) -> List[Any]:
        """Extract items from various result formats"""
        if isinstance(result, list):
            return result
        
        if isinstance(result, dict):
            # Common pagination response formats
            for key in ['items', 'data', 'results', 'content', 'records']:
                if key in result and isinstance(result[key], list):
                    return result[key]
        
        # If result has an iterator interface
        if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
            try:
                return list(result)
            except:
                pass
        
        # Fallback: wrap single result
        return [result] if result is not None else []
    
    def _determine_has_more(self, result: Any, items: List[Any], config: PaginationConfig) -> bool:
        """Determine if there are more pages"""
        # If we got fewer items than page size, likely no more pages
        if len(items) < config.page_size:
            return False
        
        # Check common pagination metadata fields
        if isinstance(result, dict):
            for key in ['has_more', 'has_next', 'hasMore', 'hasNext']:
                if key in result:
                    return bool(result[key])
            
            # Check for next page indicators
            for key in ['next_page', 'nextPage', 'next']:
                if key in result and result[key]:
                    return True
        
        # Default: assume more pages if we got a full page
        return len(items) == config.page_size
    
    def _extract_total(self, result: Any) -> Optional[int]:
        """Extract total count from result"""
        if isinstance(result, dict):
            for key in ['total', 'total_count', 'totalCount', 'count']:
                if key in result and isinstance(result[key], int):
                    return result[key]
        
        return None
    
    def collect_all_pages(self, 
                         method: Callable,
                         config: PaginationConfig,
                         **kwargs) -> List[Any]:
        """Collect all items from all pages (synchronous)"""
        all_items = []
        
        for page_result in self.paginate_sync(method, config, **kwargs):
            all_items.extend(page_result.items)
            
            # Stop if we hit an error
            if page_result.items and isinstance(page_result.items[0], dict) and "error" in page_result.items[0]:
                break
        
        return all_items
    
    async def collect_all_pages_async(self,
                                    method: Callable,
                                    config: PaginationConfig,
                                    **kwargs) -> List[Any]:
        """Collect all items from all pages (asynchronous)"""
        all_items = []
        
        async for page_result in self.paginate_async(method, config, **kwargs):
            all_items.extend(page_result.items)
            
            # Stop if we hit an error
            if page_result.items and isinstance(page_result.items[0], dict) and "error" in page_result.items[0]:
                break
        
        return all_items
