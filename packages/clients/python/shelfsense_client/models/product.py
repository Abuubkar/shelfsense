from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.category import Category
    from ..models.extracted_attribute import ExtractedAttribute
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
        color_base (None | str): The supplier's colour in a 16-colour base palette (black, white, gray, brown, beige,
            red, pink, orange, yellow, green, blue, navy, purple, gold, silver, multicolor).
        material (None | str):
        gender (None | str): men, women, unisex or kids.
        size_system (None | str): US, UK, EU (shoe sizes) or alpha (XS-XXXL, ONE SIZE).
        size_value (None | str):
        extracted_attributes (list[ExtractedAttribute]): Attributes the model read from the listing, each with the exact
            quote that states it.
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
    color_base: None | str
    material: None | str
    gender: None | str
    size_system: None | str
    size_value: None | str
    extracted_attributes: list[ExtractedAttribute]
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

        color_base: None | str
        color_base = self.color_base

        material: None | str
        material = self.material

        gender: None | str
        gender = self.gender

        size_system: None | str
        size_system = self.size_system

        size_value: None | str
        size_value = self.size_value

        extracted_attributes = []
        for extracted_attributes_item_data in self.extracted_attributes:
            extracted_attributes_item = extracted_attributes_item_data.to_dict()
            extracted_attributes.append(extracted_attributes_item)

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
                "color_base": color_base,
                "material": material,
                "gender": gender,
                "size_system": size_system,
                "size_value": size_value,
                "extracted_attributes": extracted_attributes,
                "category": category,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.category import Category  # noqa: PLC0415
        from ..models.extracted_attribute import ExtractedAttribute  # noqa: PLC0415
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

        def _parse_color_base(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        color_base = _parse_color_base(d.pop("color_base"))

        def _parse_material(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        material = _parse_material(d.pop("material"))

        def _parse_gender(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        gender = _parse_gender(d.pop("gender"))

        def _parse_size_system(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        size_system = _parse_size_system(d.pop("size_system"))

        def _parse_size_value(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        size_value = _parse_size_value(d.pop("size_value"))

        extracted_attributes = []
        _extracted_attributes = d.pop("extracted_attributes")
        for extracted_attributes_item_data in _extracted_attributes:
            extracted_attributes_item = ExtractedAttribute.from_dict(extracted_attributes_item_data)

            extracted_attributes.append(extracted_attributes_item)

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
            color_base=color_base,
            material=material,
            gender=gender,
            size_system=size_system,
            size_value=size_value,
            extracted_attributes=extracted_attributes,
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
