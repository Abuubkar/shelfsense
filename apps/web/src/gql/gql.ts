/* eslint-disable */
import * as types from './graphql';



/**
 * Map of all GraphQL operations in the project.
 *
 * This map has several performance disadvantages:
 * 1. It is not tree-shakeable, so it will include all operations in the project.
 * 2. It is not minifiable, so the string of a GraphQL query will be multiple times inside the bundle.
 * 3. It does not support dead code elimination, so it will add unused operations.
 *
 * Therefore it is highly recommended to use the babel or swc plugin for production.
 * Learn more about it here: https://the-guild.dev/graphql/codegen/plugins/presets/preset-client#reducing-bundle-size
 */
type Documents = {
    "\n  query ProductDetail($id: UUID!) {\n    product(id: $id) {\n      id title description brand gtin supplier supplierSku\n      price { amountMinor currency }\n      attributes { name value }\n      colorBase material gender sizeSystem sizeValue\n      extractedAttributes { name value unit evidenceField evidenceStart evidenceEnd evidenceText }\n      category { fullPath nodeId confidence }\n    }\n  }\n": typeof types.ProductDetailDocument,
};
const documents: Documents = {
    "\n  query ProductDetail($id: UUID!) {\n    product(id: $id) {\n      id title description brand gtin supplier supplierSku\n      price { amountMinor currency }\n      attributes { name value }\n      colorBase material gender sizeSystem sizeValue\n      extractedAttributes { name value unit evidenceField evidenceStart evidenceEnd evidenceText }\n      category { fullPath nodeId confidence }\n    }\n  }\n": types.ProductDetailDocument,
};

/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query ProductDetail($id: UUID!) {\n    product(id: $id) {\n      id title description brand gtin supplier supplierSku\n      price { amountMinor currency }\n      attributes { name value }\n      colorBase material gender sizeSystem sizeValue\n      extractedAttributes { name value unit evidenceField evidenceStart evidenceEnd evidenceText }\n      category { fullPath nodeId confidence }\n    }\n  }\n"): typeof import('./graphql').ProductDetailDocument;


export function graphql(source: string) {
  return (documents as any)[source] ?? {};
}
