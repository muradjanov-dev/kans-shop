from pydantic import BaseModel


class FavoriteStateOut(BaseModel):
    is_favorite: bool
