# anysdk-mcp/mcp_sdk_bridge/core/streaming.py

"""
Streaming Module

Handles streaming responses from SDK methods.
"""

from typing import Any, AsyncIterator, Iterator, Optional, Callable, Dict, List
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from .serialize import ResponseSerializer


@dataclass
class StreamChunk:
    """Represents a chunk of streaming data"""
    data: Any
    chunk_id: str
    timestamp: datetime
    is_final: bool = False
    metadata: Optional[Dict[str, Any]] = None


class StreamHandler:
    """Handles streaming responses from SDK methods"""
    
    def __init__(self, serializer: Optional[ResponseSerializer] = None):
        self.serializer = serializer or ResponseSerializer()
        self.active_streams: Dict[str, bool] = {}
    
    async def handle_async_stream(self,
                                 stream_source: AsyncIterator[Any],
                                 stream_id: str = None) -> AsyncIterator[StreamChunk]:
        """Handle an async streaming source"""
        if stream_id is None:
            stream_id = self._generate_stream_id()
        
        self.active_streams[stream_id] = True
        
        try:
            chunk_counter = 0
            async for data in stream_source:
                if not self.active_streams.get(stream_id, False):
                    break
                
                chunk = StreamChunk(
                    data=data,
                    chunk_id=f"{stream_id}_{chunk_counter}",
                    timestamp=datetime.utcnow(),
                    is_final=False
                )
                
                yield chunk
                chunk_counter += 1
                
        except Exception as e:
            # Yield error chunk
            error_chunk = StreamChunk(
                data={"error": str(e), "type": type(e).__name__},
                chunk_id=f"{stream_id}_error",
                timestamp=datetime.utcnow(),
                is_final=True
            )
            yield error_chunk
        finally:
            # Yield final chunk
            final_chunk = StreamChunk(
                data={"message": "Stream ended"},
                chunk_id=f"{stream_id}_final",
                timestamp=datetime.utcnow(),
                is_final=True
            )
            yield final_chunk
            
            # Clean up
            if stream_id in self.active_streams:
                del self.active_streams[stream_id]
    
    def handle_sync_stream(self,
                          stream_source: Iterator[Any],
                          stream_id: str = None) -> Iterator[StreamChunk]:
        """Handle a sync streaming source"""
        if stream_id is None:
            stream_id = self._generate_stream_id()
        
        self.active_streams[stream_id] = True
        
        try:
            chunk_counter = 0
            for data in stream_source:
                if not self.active_streams.get(stream_id, False):
                    break
                
                chunk = StreamChunk(
                    data=data,
                    chunk_id=f"{stream_id}_{chunk_counter}",
                    timestamp=datetime.utcnow(),
                    is_final=False
                )
                
                yield chunk
                chunk_counter += 1
                
        except Exception as e:
            # Yield error chunk
            error_chunk = StreamChunk(
                data={"error": str(e), "type": type(e).__name__},
                chunk_id=f"{stream_id}_error",
                timestamp=datetime.utcnow(),
                is_final=True
            )
            yield error_chunk
        finally:
            # Yield final chunk
            final_chunk = StreamChunk(
                data={"message": "Stream ended"},
                chunk_id=f"{stream_id}_final",
                timestamp=datetime.utcnow(),
                is_final=True
            )
            yield final_chunk
            
            # Clean up
            if stream_id in self.active_streams:
                del self.active_streams[stream_id]
    
    def stop_stream(self, stream_id: str):
        """Stop an active stream"""
        if stream_id in self.active_streams:
            self.active_streams[stream_id] = False
    
    def _generate_stream_id(self) -> str:
        """Generate a unique stream ID"""
        return f"stream_{int(datetime.utcnow().timestamp() * 1000000)}"
    
    def serialize_chunk(self, chunk: StreamChunk) -> Dict[str, Any]:
        """Serialize a stream chunk for MCP"""
        return self.serializer.serialize_streaming_chunk(
            chunk.data,
            chunk.chunk_id
        )
    
    async def buffer_stream(self,
                           stream: AsyncIterator[StreamChunk],
                           buffer_size: int = 10) -> AsyncIterator[List[StreamChunk]]:
        """Buffer stream chunks"""
        buffer = []
        
        async for chunk in stream:
            buffer.append(chunk)
            
            if len(buffer) >= buffer_size or chunk.is_final:
                yield buffer.copy()
                buffer.clear()
                
                if chunk.is_final:
                    break
        
        # Yield any remaining buffered chunks
        if buffer:
            yield buffer


class SSEFormatter:
    """Formats streaming data as Server-Sent Events"""
    
    @staticmethod
    def format_chunk(chunk: StreamChunk) -> str:
        """Format a chunk as SSE"""
        lines = []
        
        # Add event type
        if chunk.is_final:
            lines.append("event: close")
        else:
            lines.append("event: data")
        
        # Add ID
        lines.append(f"id: {chunk.chunk_id}")
        
        # Add timestamp
        lines.append(f"timestamp: {chunk.timestamp.isoformat()}")
        
        # Add data
        data = json.dumps(chunk.data)
        lines.append(f"data: {data}")
        
        # Add empty line to separate events
        lines.append("")
        
        return "\n".join(lines)


class WebSocketFormatter:
    """Formats streaming data for WebSocket"""
    
    @staticmethod
    def format_chunk(chunk: StreamChunk) -> str:
        """Format a chunk for WebSocket"""
        message = {
            "id": chunk.chunk_id,
            "timestamp": chunk.timestamp.isoformat(),
            "data": chunk.data,
            "final": chunk.is_final
        }
        
        if chunk.metadata:
            message["metadata"] = chunk.metadata
        
        return json.dumps(message)
