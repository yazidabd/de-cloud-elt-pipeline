from typing import List

from pydantic import BaseModel


# skema ini merepresentasikan struktur yang KITA HARAPKAN dari FakeStoreAPI
# kalau API berubah struktur (misal price jadi string), validasi ini akan
# gagal cepat dengan pesan error yang jelas, bukan lolos dan bikin data
# korup di tahap loader/dbt yang lebih sulit di-debug
class ProductRating(BaseModel):
    rate: float
    count: int


class Product(BaseModel):
    id: int
    title: str
    price: float
    description: str
    category: str
    image: str
    rating: ProductRating


def validate_products(raw_products: list) -> List[Product]:
    return [Product.model_validate(p) for p in raw_products]
