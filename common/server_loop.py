import asyncio


def postgres_event_loop() -> asyncio.AbstractEventLoop:
    """Create an event loop that supports psycopg async connections on Windows."""
    return asyncio.SelectorEventLoop()
