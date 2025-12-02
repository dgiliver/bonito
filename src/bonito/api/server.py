"""Server entry point for running the API."""

import uvicorn


def main() -> None:
    """Run the API server."""
    uvicorn.run(
        "bonito.api.main:app",
        host="0.0.0.0",  # nosec B104 - intentional for container/dev use
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
