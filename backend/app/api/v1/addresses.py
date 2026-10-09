from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas.customer import AddressCreate, AddressOut, AddressPatch
from app.core.exceptions import NotFoundError
from app.db.models.address import Address
from app.db.models.user import User
from app.services import address_service

router = APIRouter(prefix="/addresses", tags=["addresses"])


def _address_to_out(address: Address) -> AddressOut:
    return AddressOut.model_validate(address)


@router.get("", response_model=list[AddressOut])
async def list_addresses(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[AddressOut]:
    addresses = await address_service.list_addresses(session, user)
    return [_address_to_out(address) for address in addresses]


@router.post("", response_model=AddressOut, status_code=201)
async def create_address(
    payload: AddressCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AddressOut:
    address = await address_service.create_address(
        session, user, payload.model_dump(exclude_unset=True)
    )
    return _address_to_out(address)


@router.patch("/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: int,
    payload: AddressPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AddressOut:
    address = await address_service.update_address(
        session, user, address_id, payload.model_dump(exclude_unset=True)
    )
    if address is None:
        raise NotFoundError("Address not found")
    return _address_to_out(address)


@router.delete("/{address_id}", status_code=204)
async def delete_address(
    address_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Response:
    deleted = await address_service.delete_address(session, user, address_id)
    if not deleted:
        raise NotFoundError("Address not found")
    return Response(status_code=204)


@router.put("/{address_id}/default", response_model=AddressOut)
async def set_default_address(
    address_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AddressOut:
    address = await address_service.set_default_address(session, user, address_id)
    return _address_to_out(address)
