"""
Bootstrap the standalone Text-to-SQL BigQuery hands-on.

This script creates three logical layers:

1. BUSINESS DATA
   - stores
   - products
   - sales
   - inventory
   - suppliers
   - product_suppliers

2. KNOWLEDGE CATALOG
   Metadata describing the physical data model:
   - tables
   - important columns
   - descriptions
   - synonyms
   - join hints

3. SEMANTIC CATALOG
   Governed business meaning:
   - metric names
   - business definitions
   - approved SQL expressions
   - grain
   - synonyms

HYBRID SEARCH ENHANCEMENT
-------------------------
The Knowledge Catalog and Semantic Catalog also contain embeddings.

Those embeddings are generated ONCE during bootstrap and stored in BigQuery.

At runtime:

    User Question
         |
         +---- Lexical Search
         |
         +---- Semantic Search using embeddings
         |
         +---- Hybrid Fusion

The embedding is therefore metadata infrastructure, not something we
recalculate for every catalog row whenever the user asks a question.
"""

import os
from datetime import date, timedelta
from typing import Any

from google import genai
from google.cloud import bigquery


# =============================================================================
# 1. Runtime configuration
# =============================================================================

PROJECT = os.getenv(
    "GOOGLE_CLOUD_PROJECT",
    "tredence-learning",
)

LOCATION = os.getenv(
    "GOOGLE_CLOUD_LOCATION",
    "us-central1",
)

DATASET = os.getenv(
    "TEXT2SQL_DATASET",
    "tredence_fde_text2sql",
)

EMBEDDING_MODEL = os.getenv(
    "TEXT2SQL_EMBEDDING_MODEL",
    "gemini-embedding-001",
)


# =============================================================================
# 2. Google Cloud clients
# =============================================================================

# BigQuery uses Application Default Credentials.
bq = bigquery.Client(project=PROJECT)

# Explicitly use Vertex AI.
gemini = genai.Client(
    vertexai=True,
    project=PROJECT,
    location=LOCATION,
)


# =============================================================================
# 3. Physical business table schemas
# =============================================================================
#
# These are the REAL warehouse tables.
#
# Gemini eventually generates SQL against these tables.
#
# Think:
#
#   Business tables = actual data
#
# The Knowledge Catalog and Semantic Catalog created later are metadata ABOUT
# this data. They are not substitutes for the actual business tables.
# =============================================================================


STORES_SCHEMA = [
    bigquery.SchemaField("store_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("store_name", "STRING"),
    bigquery.SchemaField("city", "STRING"),
    bigquery.SchemaField("region", "STRING"),
    bigquery.SchemaField("active", "BOOL"),
]


PRODUCTS_SCHEMA = [
    bigquery.SchemaField("product_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("product_name", "STRING"),
    bigquery.SchemaField("category", "STRING"),
    bigquery.SchemaField("brand", "STRING"),
    bigquery.SchemaField("unit_price", "FLOAT64"),
]


SALES_SCHEMA = [
    bigquery.SchemaField("sale_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("sale_date", "DATE"),
    bigquery.SchemaField("store_id", "STRING"),
    bigquery.SchemaField("product_id", "STRING"),
    bigquery.SchemaField("quantity", "INT64"),
    bigquery.SchemaField("gross_sales", "FLOAT64"),
    bigquery.SchemaField("discount_amount", "FLOAT64"),
    bigquery.SchemaField("return_amount", "FLOAT64"),
]


INVENTORY_SCHEMA = [
    bigquery.SchemaField("snapshot_date", "DATE"),
    bigquery.SchemaField("store_id", "STRING"),
    bigquery.SchemaField("product_id", "STRING"),
    bigquery.SchemaField("on_hand_qty", "INT64"),
    bigquery.SchemaField("reorder_point", "INT64"),
]


SUPPLIERS_SCHEMA = [
    bigquery.SchemaField("supplier_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("supplier_name", "STRING"),
    bigquery.SchemaField("country", "STRING"),
    bigquery.SchemaField("active", "BOOL"),
]


PRODUCT_SUPPLIERS_SCHEMA = [
    bigquery.SchemaField("product_id", "STRING"),
    bigquery.SchemaField("supplier_id", "STRING"),
    bigquery.SchemaField("preferred_supplier", "BOOL"),
]


# =============================================================================
# 4. Knowledge Catalog schema
# =============================================================================
#
# PURPOSE:
#
#     "What data exists and how does it relate?"
#
# This is OUR OWN BigQuery metadata table.
#
# It is NOT the managed Google Cloud Knowledge Catalog service.
#
# -----------------------------------------------------------------------------
#
# object_type
#     What kind of metadata object is represented?
#
#     Examples:
#         TABLE
#         COLUMN
#
#
# object_name
#     Physical BigQuery object being described.
#
#     Examples:
#         sales
#         inventory
#         gross_sales
#
#
# parent_object
#     Parent table for COLUMN metadata.
#
#     Example:
#
#         object_type   = COLUMN
#         object_name   = gross_sales
#         parent_object = sales
#
#     TABLE objects do not need a parent, so this is empty.
#
#
# description
#     Human/business description of the object.
#
#     This is important because physical database names do not always match
#     the language used by business users.
#
#
# synonyms
#     Alternative words users may use.
#
#     Example:
#
#         sales
#         revenue
#         transactions
#
#     Synonyms improve lexical retrieval and also contribute useful meaning
#     to the embedding.
#
#
# join_hint
#     Known relationship information.
#
#     Example:
#
#         sales.store_id = stores.store_id
#
#     This helps Gemini avoid inventing joins.
#
#
# status
#     Governance state.
#
#     Only APPROVED metadata should be used by the Text-to-SQL pipeline.
#
#
# embedding
#     Semantic vector generated from the metadata text.
#
#     This enables semantic retrieval when the user's vocabulary does not
#     exactly match our metadata vocabulary.
#
# =============================================================================


KNOWLEDGE_CATALOG_SCHEMA = [
    bigquery.SchemaField("object_type", "STRING"),
    bigquery.SchemaField("object_name", "STRING"),
    bigquery.SchemaField("parent_object", "STRING"),
    bigquery.SchemaField("description", "STRING"),
    bigquery.SchemaField("synonyms", "STRING"),
    bigquery.SchemaField("join_hint", "STRING"),
    bigquery.SchemaField("status", "STRING"),

    # NEW FOR HYBRID SEARCH
    bigquery.SchemaField(
        "embedding",
        "FLOAT64",
        mode="REPEATED",
    ),
]


# =============================================================================
# 5. Semantic Catalog schema
# =============================================================================
#
# PURPOSE:
#
#     "What does the business mean?"
#
# Example:
#
#     User asks:
#         "Show net revenue"
#
# There may be no column called net_revenue.
#
# Instead, the Semantic Catalog defines:
#
#     net_sales =
#         SUM(
#             gross_sales
#             - discount_amount
#             - return_amount
#         )
#
#
# metric_name
#     Canonical governed name of the business metric.
#
#
# business_definition
#     Human-readable business meaning.
#
#
# sql_expression
#     Approved SQL expression implementing that business definition.
#
#
# grain
#     Level at which the metric is meaningful.
#
#
# synonyms
#     Alternative business terminology.
#
#
# status
#     Governance lifecycle.
#
#
# embedding
#     Semantic representation of the metric metadata.
#
# =============================================================================


SEMANTIC_CATALOG_SCHEMA = [
    bigquery.SchemaField("metric_name", "STRING"),
    bigquery.SchemaField("business_definition", "STRING"),
    bigquery.SchemaField("sql_expression", "STRING"),
    bigquery.SchemaField("grain", "STRING"),
    bigquery.SchemaField("synonyms", "STRING"),
    bigquery.SchemaField("status", "STRING"),

    # NEW FOR HYBRID SEARCH
    bigquery.SchemaField(
        "embedding",
        "FLOAT64",
        mode="REPEATED",
    ),
]


# =============================================================================
# 6. Table creation helper
# =============================================================================


def create_table(
    table_name: str,
    schema: list[bigquery.SchemaField],
) -> None:
    """
    Create or replace a BigQuery table.

    CREATE OR REPLACE keeps the hands-on repeatable:
    the trainer can rerun bootstrap without manually deleting tables.
    """

    table_id = f"{PROJECT}.{DATASET}.{table_name}"

    column_definitions = []

    for field in schema:

        if field.mode == "REPEATED":
            sql_type = f"ARRAY<{field.field_type}>"
        else:
            sql_type = field.field_type

        column_definitions.append(
            f"`{field.name}` {sql_type}"
        )

    ddl = f"""
    CREATE OR REPLACE TABLE `{table_id}`
    (
        {", ".join(column_definitions)}
    )
    """

    bq.query(ddl).result()

    print(f"Created table: {table_id}")


# =============================================================================
# 7. Create all tables
# =============================================================================


def create_tables() -> None:
    """Create business tables and metadata catalogs."""

    create_table(
        "stores",
        STORES_SCHEMA,
    )

    create_table(
        "products",
        PRODUCTS_SCHEMA,
    )

    create_table(
        "sales",
        SALES_SCHEMA,
    )

    create_table(
        "inventory",
        INVENTORY_SCHEMA,
    )

    create_table(
        "suppliers",
        SUPPLIERS_SCHEMA,
    )

    create_table(
        "product_suppliers",
        PRODUCT_SUPPLIERS_SCHEMA,
    )

    create_table(
        "knowledge_catalog",
        KNOWLEDGE_CATALOG_SCHEMA,
    )

    create_table(
        "semantic_catalog",
        SEMANTIC_CATALOG_SCHEMA,
    )


# =============================================================================
# 8. Business data
# =============================================================================


def build_business_data() -> dict[str, list[dict[str, Any]]]:
    """Build deterministic retail data for the hands-on."""

    stores = [
        {
            "store_id": "S001",
            "store_name": "Chicago Downtown",
            "city": "Chicago",
            "region": "Midwest",
            "active": True,
        },
        {
            "store_id": "S002",
            "store_name": "Dallas Central",
            "city": "Dallas",
            "region": "South",
            "active": True,
        },
        {
            "store_id": "S003",
            "store_name": "Seattle Market",
            "city": "Seattle",
            "region": "West",
            "active": True,
        },
    ]

    products = [
        {
            "product_id": "P001",
            "product_name": "Wireless Headphones",
            "category": "Electronics",
            "brand": "Nova",
            "unit_price": 120.0,
        },
        {
            "product_id": "P002",
            "product_name": "Smart Speaker",
            "category": "Electronics",
            "brand": "Nova",
            "unit_price": 90.0,
        },
        {
            "product_id": "P003",
            "product_name": "Coffee Maker",
            "category": "Home",
            "brand": "UrbanHome",
            "unit_price": 75.0,
        },
        {
            "product_id": "P004",
            "product_name": "Desk Lamp",
            "category": "Home",
            "brand": "UrbanHome",
            "unit_price": 45.0,
        },
    ]

    suppliers = [
        {
            "supplier_id": "SUP001",
            "supplier_name": "NorthStar Electronics",
            "country": "USA",
            "active": True,
        },
        {
            "supplier_id": "SUP002",
            "supplier_name": "Global Home Supply",
            "country": "USA",
            "active": True,
        },
        {
            "supplier_id": "SUP003",
            "supplier_name": "Pacific Components",
            "country": "Canada",
            "active": True,
        },
    ]

    product_suppliers = [
        {
            "product_id": "P001",
            "supplier_id": "SUP001",
            "preferred_supplier": True,
        },
        {
            "product_id": "P002",
            "supplier_id": "SUP001",
            "preferred_supplier": True,
        },
        {
            "product_id": "P003",
            "supplier_id": "SUP002",
            "preferred_supplier": True,
        },
        {
            "product_id": "P004",
            "supplier_id": "SUP003",
            "preferred_supplier": True,
        },
    ]

    # -------------------------------------------------------------------------
    # Generate deterministic sales data.
    # -------------------------------------------------------------------------

    sales = []

    start_date = date.today() - timedelta(days=29)

    sale_number = 1

    for day_offset in range(30):

        sale_date = start_date + timedelta(days=day_offset)

        for store_index, store in enumerate(stores):

            for product_index, product in enumerate(products):

                quantity = (
                    (day_offset + store_index + product_index) % 5
                ) + 1

                gross_sales = round(
                    quantity * product["unit_price"],
                    2,
                )

                # Small deterministic discount pattern.
                discount_amount = round(
                    gross_sales * 0.05
                    if day_offset % 5 == 0
                    else 0.0,
                    2,
                )

                # Small deterministic return pattern.
                return_amount = round(
                    product["unit_price"]
                    if day_offset % 11 == 0
                    else 0.0,
                    2,
                )

                sales.append(
                    {
                        "sale_id": f"SALE{sale_number:05d}",
                        "sale_date": sale_date.isoformat(),
                        "store_id": store["store_id"],
                        "product_id": product["product_id"],
                        "quantity": quantity,
                        "gross_sales": gross_sales,
                        "discount_amount": discount_amount,
                        "return_amount": return_amount,
                    }
                )

                sale_number += 1

    # -------------------------------------------------------------------------
    # Current inventory snapshot.
    # -------------------------------------------------------------------------

    today = date.today().isoformat()

    inventory = [
        {
            "snapshot_date": today,
            "store_id": "S001",
            "product_id": "P001",
            "on_hand_qty": 3,
            "reorder_point": 10,
        },
        {
            "snapshot_date": today,
            "store_id": "S001",
            "product_id": "P002",
            "on_hand_qty": 0,
            "reorder_point": 8,
        },
        {
            "snapshot_date": today,
            "store_id": "S001",
            "product_id": "P003",
            "on_hand_qty": 18,
            "reorder_point": 7,
        },
        {
            "snapshot_date": today,
            "store_id": "S001",
            "product_id": "P004",
            "on_hand_qty": 5,
            "reorder_point": 6,
        },
        {
            "snapshot_date": today,
            "store_id": "S002",
            "product_id": "P001",
            "on_hand_qty": 15,
            "reorder_point": 10,
        },
        {
            "snapshot_date": today,
            "store_id": "S002",
            "product_id": "P002",
            "on_hand_qty": 4,
            "reorder_point": 8,
        },
        {
            "snapshot_date": today,
            "store_id": "S002",
            "product_id": "P003",
            "on_hand_qty": 0,
            "reorder_point": 7,
        },
        {
            "snapshot_date": today,
            "store_id": "S002",
            "product_id": "P004",
            "on_hand_qty": 12,
            "reorder_point": 6,
        },
        {
            "snapshot_date": today,
            "store_id": "S003",
            "product_id": "P001",
            "on_hand_qty": 7,
            "reorder_point": 10,
        },
        {
            "snapshot_date": today,
            "store_id": "S003",
            "product_id": "P002",
            "on_hand_qty": 13,
            "reorder_point": 8,
        },
        {
            "snapshot_date": today,
            "store_id": "S003",
            "product_id": "P003",
            "on_hand_qty": 6,
            "reorder_point": 7,
        },
        {
            "snapshot_date": today,
            "store_id": "S003",
            "product_id": "P004",
            "on_hand_qty": 0,
            "reorder_point": 6,
        },
    ]

    return {
        "stores": stores,
        "products": products,
        "sales": sales,
        "inventory": inventory,
        "suppliers": suppliers,
        "product_suppliers": product_suppliers,
    }


# =============================================================================
# 9. Metadata embedding helper
# =============================================================================


def generate_embedding(text: str) -> list[float]:
    """
    Convert metadata text into a semantic vector using Vertex AI.

    IMPORTANT DESIGN PATTERN
    ------------------------
    We embed metadata during bootstrap.

    We do NOT regenerate every catalog embedding whenever a user asks
    a question.

    Runtime only needs to embed the user's question.
    """

    response = gemini.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )

    if not response.embeddings:
        raise RuntimeError(
            f"No embedding returned for text: {text}"
        )

    return list(response.embeddings[0].values)


# =============================================================================
# 10. Knowledge Catalog metadata
# =============================================================================


def build_knowledge_catalog() -> list[dict[str, Any]]:
    """
    Build metadata describing the physical warehouse.

    Each metadata row gets an embedding generated from its useful
    searchable text.
    """

    rows = [
        {
            "object_type": "TABLE",
            "object_name": "sales",
            "parent_object": "",
            "description": (
                "Retail sales facts by date, store and product. "
                "Contains quantity, gross sales, discounts and returns."
            ),
            "synonyms": (
                "sales, revenue, transactions, purchases, turnover"
            ),
            "join_hint": (
                "sales.store_id = stores.store_id; "
                "sales.product_id = products.product_id"
            ),
            "status": "APPROVED",
        },
        {
            "object_type": "TABLE",
            "object_name": "inventory",
            "parent_object": "",
            "description": (
                "Current inventory position by store and product. "
                "Contains stock on hand and reorder thresholds."
            ),
            "synonyms": (
                "inventory, stock, stock level, merchandise, "
                "on hand, replenishment"
            ),
            "join_hint": (
                "inventory.store_id = stores.store_id; "
                "inventory.product_id = products.product_id"
            ),
            "status": "APPROVED",
        },
        {
            "object_type": "TABLE",
            "object_name": "stores",
            "parent_object": "",
            "description": (
                "Retail store master containing store name, city, "
                "region and active status."
            ),
            "synonyms": (
                "stores, store, outlet, location, branch, shop"
            ),
            "join_hint": (
                "stores.store_id joins sales.store_id and "
                "inventory.store_id"
            ),
            "status": "APPROVED",
        },
        {
            "object_type": "TABLE",
            "object_name": "products",
            "parent_object": "",
            "description": (
                "Product master containing product name, category, "
                "brand and unit price."
            ),
            "synonyms": (
                "products, product, item, merchandise, sku"
            ),
            "join_hint": (
                "products.product_id joins sales.product_id, "
                "inventory.product_id and product_suppliers.product_id"
            ),
            "status": "APPROVED",
        },
        {
            "object_type": "TABLE",
            "object_name": "suppliers",
            "parent_object": "",
            "description": (
                "Supplier master containing supplier name, country "
                "and active status."
            ),
            "synonyms": (
                "suppliers, supplier, vendor, vendors"
            ),
            "join_hint": (
                "Use product_suppliers as the bridge between "
                "suppliers and products"
            ),
            "status": "APPROVED",
        },
        {
            "object_type": "TABLE",
            "object_name": "product_suppliers",
            "parent_object": "",
            "description": (
                "Bridge table mapping products to suppliers and "
                "identifying the preferred supplier."
            ),
            "synonyms": (
                "product supplier mapping, supplier mapping, "
                "vendor mapping, preferred vendor"
            ),
            "join_hint": (
                "product_suppliers.product_id = products.product_id; "
                "product_suppliers.supplier_id = suppliers.supplier_id"
            ),
            "status": "APPROVED",
        },
        {
            "object_type": "COLUMN",
            "object_name": "gross_sales",
            "parent_object": "sales",
            "description": (
                "Sales value before discounts and returns."
            ),
            "synonyms": (
                "gross revenue, gross sales, sales before discount"
            ),
            "join_hint": "",
            "status": "APPROVED",
        },
        {
            "object_type": "COLUMN",
            "object_name": "on_hand_qty",
            "parent_object": "inventory",
            "description": (
                "Current quantity physically available in stock."
            ),
            "synonyms": (
                "stock on hand, available stock, inventory quantity"
            ),
            "join_hint": "",
            "status": "APPROVED",
        },
    ]

    # -------------------------------------------------------------------------
    # Create one embedding per metadata record.
    #
    # We intentionally combine the most useful searchable fields.
    # -------------------------------------------------------------------------

    for row in rows:

        embedding_text = " | ".join(
            [
                row["object_type"],
                row["object_name"],
                row["parent_object"],
                row["description"],
                row["synonyms"],
                row["join_hint"],
            ]
        )

        print(
            "Embedding Knowledge Catalog:",
            row["object_name"],
        )

        row["embedding"] = generate_embedding(
            embedding_text
        )

    return rows


# =============================================================================
# 11. Semantic Catalog metadata
# =============================================================================


def build_semantic_catalog() -> list[dict[str, Any]]:
    """
    Build governed business metric definitions.

    These definitions prevent Gemini from inventing what important
    business terms mean.
    """

    rows = [
        {
            "metric_name": "net_sales",
            "business_definition": (
                "Recognized sales after discounts and returns."
            ),
            "sql_expression": (
                "SUM("
                "gross_sales "
                "- discount_amount "
                "- return_amount"
                ")"
            ),
            "grain": (
                "Any requested grouping over sales facts"
            ),
            "synonyms": (
                "net revenue, revenue after discounts, "
                "recognized sales"
            ),
            "status": "APPROVED",
        },
        {
            "metric_name": "units_sold",
            "business_definition": (
                "Total number of product units sold."
            ),
            "sql_expression": "SUM(quantity)",
            "grain": (
                "Any requested grouping over sales facts"
            ),
            "synonyms": (
                "units sold, quantity sold, sales volume"
            ),
            "status": "APPROVED",
        },
        {
            "metric_name": "stockout",
            "business_definition": (
                "A store-product inventory position where "
                "no stock is currently available."
            ),
            "sql_expression": "on_hand_qty = 0",
            "grain": (
                "store_id, product_id, snapshot_date"
            ),
            "synonyms": (
                "out of stock, no stock, unavailable inventory"
            ),
            "status": "APPROVED",
        },
        {
            "metric_name": "below_reorder_point",
            "business_definition": (
                "Inventory position where current stock is below "
                "the configured replenishment threshold."
            ),
            "sql_expression": (
                "on_hand_qty < reorder_point"
            ),
            "grain": (
                "store_id, product_id, snapshot_date"
            ),
            "synonyms": (
                "low stock, needs replenishment, "
                "below reorder threshold"
            ),
            "status": "APPROVED",
        },
    ]

    for row in rows:

        embedding_text = " | ".join(
            [
                row["metric_name"],
                row["business_definition"],
                row["sql_expression"],
                row["grain"],
                row["synonyms"],
            ]
        )

        print(
            "Embedding Semantic Catalog:",
            row["metric_name"],
        )

        row["embedding"] = generate_embedding(
            embedding_text
        )

    return rows


# =============================================================================
# 12. BigQuery row loader
# =============================================================================


def load_rows(
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    """Insert JSON-compatible rows into BigQuery."""

    table_id = f"{PROJECT}.{DATASET}.{table_name}"

    errors = bq.insert_rows_json(
        table_id,
        rows,
    )

    if errors:
        raise RuntimeError(
            f"Failed loading {table_name}: {errors}"
        )

    print(
        f"Loaded {len(rows)} rows into {table_id}"
    )


# =============================================================================
# 13. Main bootstrap
# =============================================================================


def main() -> None:
    """Create and populate the complete hands-on dataset."""

    print()
    print("==============================================")
    print("Tredence FDE - Text-to-SQL Bootstrap")
    print("Hybrid Metadata RAG Version")
    print("==============================================")
    print()

    print(f"Project          : {PROJECT}")
    print(f"Dataset          : {DATASET}")
    print(f"Location         : {LOCATION}")
    print(f"Embedding model  : {EMBEDDING_MODEL}")
    print()

    # -------------------------------------------------------------------------
    # Step 1: Create all physical and metadata tables.
    # -------------------------------------------------------------------------

    print("STEP 1 - Creating tables")
    print("------------------------")

    create_tables()

    print()

    # -------------------------------------------------------------------------
    # Step 2: Populate business data.
    # -------------------------------------------------------------------------

    print("STEP 2 - Loading business data")
    print("------------------------------")

    business_data = build_business_data()

    for table_name, rows in business_data.items():
        load_rows(
            table_name,
            rows,
        )

    print()

    # -------------------------------------------------------------------------
    # Step 3: Build and embed Knowledge Catalog.
    # -------------------------------------------------------------------------

    print("STEP 3 - Building Knowledge Catalog")
    print("-----------------------------------")

    knowledge_catalog = build_knowledge_catalog()

    load_rows(
        "knowledge_catalog",
        knowledge_catalog,
    )

    print()

    # -------------------------------------------------------------------------
    # Step 4: Build and embed Semantic Catalog.
    # -------------------------------------------------------------------------

    print("STEP 4 - Building Semantic Catalog")
    print("----------------------------------")

    semantic_catalog = build_semantic_catalog()

    load_rows(
        "semantic_catalog",
        semantic_catalog,
    )

    print()

    print("==============================================")
    print("Bootstrap completed successfully.")
    print("==============================================")
    print()


if __name__ == "__main__":
    main()