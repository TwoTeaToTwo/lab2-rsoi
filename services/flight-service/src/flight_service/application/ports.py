from typing import Protocol

from flight_service.domain.models import Flight, FlightPage


class FlightRepository(Protocol):
    async def list_flights(self, page: int, size: int) -> FlightPage: ...

    async def get_flight(self, flight_number: str) -> Flight | None: ...
