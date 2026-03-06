"""
MCP Server that provides information about the system's CPU, memory, and disk usage.
"""
from fastmcp import FastMCP
import psutil


mcp = FastMCP("SystemInfo")

@mcp.tool
def get_cpu_usage(query: str) -> str:
    """
    Get the CPU usage of the system.
    """
    return f"CPU usage is {psutil.cpu_percent()}%"


@mcp.tool
def get_memory_usage(query: str) -> str:
    """
    Get the memory usage of the system.
    """
    return f"Memory usage is {psutil.virtual_memory().percent}%"


@mcp.tool
def get_disk_usage(query: str) -> str:
    """
    Get the disk usage of the system.
    """
    return f"Disk usage is {psutil.disk_usage('/').percent}%"


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)