import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ticket_service.application.service import TicketService
from ticket_service.config import Settings
from ticket_service.domain.errors import InvalidInput, TicketConflict, TicketError
from ticket_service.infrastructure.memory import InMemoryStore
from ticket_service.presentation.api import create_router
from ticket_service.presentation.schemas import (
    ErrorDescription,
    ErrorResponse,
    ValidationErrorResponse,
)

logger = logging.getLogger(__name__)


def create_app(service: TicketService | None = None) -> FastAPI:
    """Composition root. Tests may inject a use case backed by a separate store."""
    if service is None:
        store = InMemoryStore()
        service = TicketService(store.transaction)
    app = FastAPI(title="Ticket Service", version="0.1.0")
    app.include_router(create_router(service))

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception) -> JSONResponse:
        logger.error("Unhandled Ticket Service error", exc_info=error)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(message="Internal server error").model_dump(),
        )

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

    @app.exception_handler(TicketError)
    async def business_error(request: Request, error: TicketError) -> JSONResponse:
        if isinstance(error, InvalidInput):
            body = ValidationErrorResponse(
                message="Validation failed",
                errors=[ErrorDescription(field=error.field, error=str(error))],
            )
            return JSONResponse(status_code=400, content=body.model_dump())
        code = 409 if isinstance(error, TicketConflict) else 404
        return JSONResponse(
            status_code=code, content=ErrorResponse(message=str(error)).model_dump()
        )

    # FastAPI normally documents 422; our contract maps request validation to 400.
    schema = app.openapi()
    for path in schema["paths"].values():
        for operation in path.values():
            operation.get("responses", {}).pop("422", None)
    return app


def run() -> None:
    settings = Settings()
    # In-memory storage requires exactly one worker.
    uvicorn.run(create_app(), host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    run()
