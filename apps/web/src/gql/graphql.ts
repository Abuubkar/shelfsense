/* eslint-disable */
/** Internal type. DO NOT USE DIRECTLY. */
type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
/** Internal type. DO NOT USE DIRECTLY. */
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
import { DocumentTypeDecoration } from '@graphql-typed-document-node/core';
export type ProductDetailQueryVariables = Exact<{
  id: string;
}>;


export type ProductDetailQuery = { product: { id: string, title: string, description: string | null, brand: string | null, gtin: string | null, supplier: string, supplierSku: string, colorBase: string | null, material: string | null, gender: string | null, sizeSystem: string | null, sizeValue: string | null, price: { amountMinor: number, currency: string }, attributes: Array<{ name: string, value: string }>, extractedAttributes: Array<{ name: string, value: string, unit: string | null, evidenceField: string, evidenceStart: number, evidenceEnd: number, evidenceText: string }>, category: { fullPath: string | null, nodeId: number | null, confidence: number } | null } | null };

export class TypedDocumentString<TResult, TVariables>
  extends String
  implements DocumentTypeDecoration<TResult, TVariables>
{
  __apiType?: NonNullable<DocumentTypeDecoration<TResult, TVariables>['__apiType']>;
  private value: string;
  public __meta__?: Record<string, any> | undefined;

  constructor(value: string, __meta__?: Record<string, any> | undefined) {
    super(value);
    this.value = value;
    this.__meta__ = __meta__;
  }

  override toString(): string & DocumentTypeDecoration<TResult, TVariables> {
    return this.value;
  }
}

export const ProductDetailDocument = new TypedDocumentString(`
    query ProductDetail($id: UUID!) {
  product(id: $id) {
    id
    title
    description
    brand
    gtin
    supplier
    supplierSku
    price {
      amountMinor
      currency
    }
    attributes {
      name
      value
    }
    colorBase
    material
    gender
    sizeSystem
    sizeValue
    extractedAttributes {
      name
      value
      unit
      evidenceField
      evidenceStart
      evidenceEnd
      evidenceText
    }
    category {
      fullPath
      nodeId
      confidence
    }
  }
}
    `) as unknown as TypedDocumentString<ProductDetailQuery, ProductDetailQueryVariables>;