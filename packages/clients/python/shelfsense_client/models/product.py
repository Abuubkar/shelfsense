from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.category import Category
    from ..models.money import Money
    from ..models.product_attributes import ProductAttributes


T = TypeVar("T", bound="Product")


@_attrs_define
class Product:
    """
    Attributes:
        id (UUID):
        supplier (str):
        supplier_sku (str):
        title (str):
        description (None | str):
        brand (None | str):
        gtin (None | str):
        price (Money):
        attributes (ProductAttributes): Supplier-provided extra columns, as given.
        category (Category | None):
    """

    id: UUID
    supplier: str
    supplier_sku: str
    title: str
    description: None | str
    brand: None | str
    gtin: None | str
    price: Money
    attributes: ProductAttributes
    category: Category | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.category import Category  # noqa: PLC0415

        id = str(self.id)

        supplier = self.supplier

        supplier_sku = self.supplier_sku

        title = self.title

        description: None | str
        description = self.description

        brand: None | str
        brand = self.brand

        gtin: None | str
        gtin = self.gtin

        price = self.price.to_dict()

        attributes = self.attributes.to_dict()

        category: dict[str, Any] | None
        if isinstance(self.category, Category):
            category = self.category.to_dict()
        else:
            category = self.category

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "supplier": supplier,
                "supplier_sku": supplier_sku,
                "title": title,
                "description": description,
                "brand": brand,
                "gtin": gtin,
                "price": price,
                "attributes": attributes,
                "category": category,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.category import Category  # noqa: PLC0415
        from ..models.money import Money  # noqa: PLC0415
        from ..models.product_attributes import ProductAttributes  # noqa: PLC0415

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        supplier = d.pop("supplier")

        supplier_sku = d.pop("supplier_sku")

        title = d.pop("title")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        def _parse_brand(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        brand = _parse_brand(d.pop("brand"))

        def _parse_gtin(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        gtin = _parse_gtin(d.pop("gtin"))

        price = Money.from_dict(d.pop("price"))

        attributes = ProductAttributes.from_dict(d.pop("attributes"))

        def _parse_category(data: object) -> Category | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                category_type_0 = Category.from_dict(data)

                return category_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Category | None, data)

        category = _parse_category(d.pop("category"))

        product = cls(
            id=id,
            supplier=supplier,
            supplier_sku=supplier_sku,
            title=title,
            description=description,
            brand=brand,
            gtin=gtin,
            price=price,
            attributes=attributes,
            category=category,
        )

        product.additional_properties = d
        return product

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
