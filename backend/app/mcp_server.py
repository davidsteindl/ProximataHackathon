import logging

from mcp.server.fastmcp import FastMCP

from app.api_client import check_api

server = FastMCP("SiteMind", host="0.0.0.0", port=8001)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    check_api("mcp")
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
