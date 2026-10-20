from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models.user import User
from app.services import geocoding

router = APIRouter(prefix="/geocode", tags=["geocode"])


class ReverseGeocodeOut(BaseModel):
    address: str | None
    latitude: Decimal
    longitude: Decimal


@router.get("/reverse", response_model=ReverseGeocodeOut)
async def reverse_geocode(
    response: Response,
    lat: Decimal = Query(ge=-90, le=90),
    lon: Decimal = Query(ge=-180, le=180),
    lang: Literal["uz", "ru"] = Query(default="uz"),
    _user: User = Depends(get_current_user),
) -> ReverseGeocodeOut:
    """Written address for a shared delivery location (signed-in customers only).

    ``address`` is null when no address can be determined; the customer then types it, and
    the order still carries the coordinates for the courier's map link.
    """
    latitude = lat.quantize(Decimal("0.000001"))
    longitude = lon.quantize(Decimal("0.000001"))
    address = await geocoding.reverse_geocode(latitude, longitude, language=lang)
    response.headers["Cache-Control"] = "private, no-store"
    return ReverseGeocodeOut(address=address, latitude=latitude, longitude=longitude)
