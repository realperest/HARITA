"""Veritabani araci istek semalari."""

from pydantic import BaseModel, Field


class SqlIstegi(BaseModel):
    """Salt okunur SQL istegi (tek SELECT / WITH sorgusu)."""

    sorgu: str = Field(min_length=1, max_length=5000)
