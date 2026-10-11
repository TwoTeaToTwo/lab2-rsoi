import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from flight_service.application.service import FlightService
from flight_service.config import Settings
from flight_service.domain.errors import FlightNotFound, InvalidInput
from flight_service.infrastructure.memory import create_seeded_repository
from flight_service.presentation.api import create_router
from flight_service.presentation.schemas import (
    ErrorDescription,
    ErrorResponse,
    ValidationErrorResponse,
)

logger = logging.getLogger(__name__)


def create_app(service: FlightService | None = None) -> FastAPI:
    if service is None:
        service = FlightService(create_seeded_repository())
    app = FastAPI(title="Flight Service", version="0.1.0")
    app.include_router(create_router(service))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        body = ValidationErrorResponse(
            message="Validation failed",
            errors=[
                ErrorDescription(
                    field=".".join(str(part) for part in item["loc"][1:]), error=str(item["msg"])
                )
                for item in error.errors()
            ],
        )
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(InvalidInput)
    async def invalid_input(request: Request, error: InvalidInput) -> JSONResponse:
        body = ValidationErrorResponse(
            message="Validation failed",
            errors=[ErrorDescription(field=error.field, error=str(error))],
        )
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(FlightNotFound)
    async def not_found(request: Request, error: FlightNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content=ErrorResponse(message=str(error)).model_dump())

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception) -> JSONResponse:
        logger.error("Unhandled Flight Service error", exc_info=error)
        return JSONResponse(
            status_code=500, content=ErrorResponse(message="Internal server error").model_dump()
        )

    schema = app.openapi()
    for path in schema["paths"].values():
        for operation in path.values():
            operation.get("responses", {}).pop("422", None)
    return app


def run() -> None:
    settings = Settings()
    uvicorn.run(create_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
