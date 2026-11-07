"""
insert_to_neo4j.py
------------------
Reads all 65 tables from the AdventureWorks SQLite database and populates Neo4j.

Strategy
--------
- Every table row  →  Node  (label = table name, all columns as properties)
- Every FK column  →  Relationship between the two referenced nodes
- BLOB columns are dropped (Neo4j cannot store binary data)
- Uses MERGE so the script is safe to re-run (idempotent)
- Batched with UNWIND for performance

Usage
-----
    NEO4J_PASSWORD=... python insert_to_neo4j.py /path/to/works_cycles.sqlite

Release copy of the converter that built the experimental Works-Cycles graph (G0). Only the configuration block differs
from the original: connection settings come from the environment and the SQLite path from the command line. The
TABLE_PKS and FOREIGN_KEYS mapping and all load logic are unchanged.
"""

import sqlite3
from neo4j import GraphDatabase
from tqdm import tqdm

# ── Config (release version: no credentials in code) ───────────────────────
# SQLite path: first command-line argument, else $WORKS_CYCLES_SQLITE, else ./works_cycles.sqlite
# Neo4j: $NEO4J_URI (default bolt://localhost:7687), $NEO4J_USERNAME (default neo4j), $NEO4J_PASSWORD (unset = no auth)
import os, sys
SQLITE_PATH    = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WORKS_CYCLES_SQLITE", "works_cycles.sqlite")
NEO4J_URI      = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
BATCH_SIZE    = 500


# ── Primary-key mapping  (str = single col, list = composite) ───────────────
TABLE_PKS = {
    "AddressType":           "AddressTypeID",
    "BusinessEntity":        "BusinessEntityID",
    "ContactType":           "ContactTypeID",
    "CountryRegion":         "CountryRegionCode",
    "CreditCard":            "CreditCardID",
    "Culture":               "CultureID",
    "Currency":              "CurrencyCode",
    "CountryRegionCurrency": ["CountryRegionCode", "CurrencyCode"],
    "CurrencyRate":          "CurrencyRateID",
    "Department":            "DepartmentID",
    "Location":              "LocationID",
    "Person":                "BusinessEntityID",
    "BusinessEntityContact": ["BusinessEntityID", "PersonID", "ContactTypeID"],
    "EmailAddress":          ["EmailAddressID", "BusinessEntityID"],
    "Employee":              "BusinessEntityID",
    "Document":              "DocumentNode",
    "EmployeePayHistory":    ["BusinessEntityID", "RateChangeDate"],
    "JobCandidate":          "JobCandidateID",
    "Password":              "BusinessEntityID",
    "PersonCreditCard":      ["BusinessEntityID", "CreditCardID"],
    "PhoneNumberType":       "PhoneNumberTypeID",
    "ProductCategory":       "ProductCategoryID",
    "ProductDescription":    "ProductDescriptionID",
    "ProductModel":          "ProductModelID",
    "ProductModelProductDescriptionCulture": ["ProductModelID", "ProductDescriptionID", "CultureID"],
    "ProductPhoto":          "ProductPhotoID",
    "ProductSubcategory":    "ProductSubcategoryID",
    "SalesReason":           "SalesReasonID",
    "SalesTerritory":        "TerritoryID",
    "SalesPerson":           "BusinessEntityID",
    "SalesPersonQuotaHistory": ["BusinessEntityID", "QuotaDate"],
    "SalesTerritoryHistory": ["BusinessEntityID", "StartDate", "TerritoryID"],
    "ScrapReason":           "ScrapReasonID",
    "Shift":                 "ShiftID",
    "EmployeeDepartmentHistory": ["BusinessEntityID", "StartDate", "DepartmentID", "ShiftID"],
    "ShipMethod":            "ShipMethodID",
    "SpecialOffer":          "SpecialOfferID",
    "StateProvince":         "StateProvinceID",
    "Address":               "AddressID",
    "BusinessEntityAddress": ["BusinessEntityID", "AddressID", "AddressTypeID"],
    "SalesTaxRate":          "SalesTaxRateID",
    "Store":                 "BusinessEntityID",
    "Customer":              "CustomerID",
    "SalesOrderHeader":      "SalesOrderID",
    "SalesOrderHeaderSalesReason": ["SalesOrderID", "SalesReasonID"],
    "TransactionHistoryArchive": "TransactionID",
    "UnitMeasure":           "UnitMeasureCode",
    "Product":               "ProductID",
    "BillOfMaterials":       "BillOfMaterialsID",
    "ProductCostHistory":    ["ProductID", "StartDate"],
    "ProductDocument":       ["ProductID", "DocumentNode"],
    "ProductInventory":      ["ProductID", "LocationID"],
    "ProductListPriceHistory": ["ProductID", "StartDate"],
    "ProductProductPhoto":   ["ProductID", "ProductPhotoID"],
    "ProductReview":         "ProductReviewID",
    "ShoppingCartItem":      "ShoppingCartItemID",
    "SpecialOfferProduct":   ["SpecialOfferID", "ProductID"],
    "SalesOrderDetail":      "SalesOrderDetailID",
    "TransactionHistory":    "TransactionID",
    "Vendor":                "BusinessEntityID",
    "ProductVendor":         ["ProductID", "BusinessEntityID"],
    "PurchaseOrderHeader":   "PurchaseOrderID",
    "PurchaseOrderDetail":   "PurchaseOrderDetailID",
    "WorkOrder":             "WorkOrderID",
    "WorkOrderRouting":      ["WorkOrderID", "ProductID", "OperationSequence"],
}

# ── Foreign-key relationships ───────────────────────────────────────────────
# (from_table, fk_col, to_table, to_pk_col, relationship_label)
# NULL FK values are skipped automatically.
FOREIGN_KEYS = [
    # Person / Employee / Store / Vendor hierarchy
    ("Person",              "BusinessEntityID",  "BusinessEntity",  "BusinessEntityID", "HAS_ENTITY"),
    ("Employee",            "BusinessEntityID",  "Person",          "BusinessEntityID", "IS_PERSON"),
    ("SalesPerson",         "BusinessEntityID",  "Employee",        "BusinessEntityID", "IS_EMPLOYEE"),
    ("SalesPerson",         "TerritoryID",       "SalesTerritory",  "TerritoryID",      "IN_TERRITORY"),
    ("Store",               "BusinessEntityID",  "BusinessEntity",  "BusinessEntityID", "HAS_ENTITY"),
    ("Store",               "SalesPersonID",     "SalesPerson",     "BusinessEntityID", "MANAGED_BY"),
    ("Vendor",              "BusinessEntityID",  "BusinessEntity",  "BusinessEntityID", "HAS_ENTITY"),
    # Contact / Email / Password / CreditCard
    ("BusinessEntityContact", "BusinessEntityID", "BusinessEntity", "BusinessEntityID", "HAS_ENTITY"),
    ("BusinessEntityContact", "PersonID",         "Person",         "BusinessEntityID", "CONTACT_IS"),
    ("BusinessEntityContact", "ContactTypeID",    "ContactType",    "ContactTypeID",    "HAS_CONTACT_TYPE"),
    ("EmailAddress",        "BusinessEntityID",  "Person",          "BusinessEntityID", "HAS_EMAIL"),
    ("Password",            "BusinessEntityID",  "Person",          "BusinessEntityID", "HAS_PASSWORD"),
    ("PersonCreditCard",    "BusinessEntityID",  "Person",          "BusinessEntityID", "CARD_OWNER"),
    ("PersonCreditCard",    "CreditCardID",      "CreditCard",      "CreditCardID",     "USES_CARD"),
    # Document
    ("Document",            "Owner",             "Employee",        "BusinessEntityID", "OWNED_BY"),
    ("ProductDocument",     "ProductID",         "Product",         "ProductID",        "DOCUMENT_FOR"),
    ("ProductDocument",     "DocumentNode",      "Document",        "DocumentNode",     "HAS_DOCUMENT"),
    # Employee HR
    ("EmployeePayHistory",  "BusinessEntityID",  "Employee",        "BusinessEntityID", "PAY_HISTORY_OF"),
    ("JobCandidate",        "BusinessEntityID",  "Employee",        "BusinessEntityID", "CANDIDATE_FOR"),
    ("EmployeeDepartmentHistory", "BusinessEntityID", "Employee",   "BusinessEntityID", "DEPT_HISTORY_OF"),
    ("EmployeeDepartmentHistory", "DepartmentID",     "Department", "DepartmentID",     "IN_DEPARTMENT"),
    ("EmployeeDepartmentHistory", "ShiftID",          "Shift",      "ShiftID",          "HAS_SHIFT"),
    # Currency / Geography
    ("CountryRegionCurrency", "CountryRegionCode", "CountryRegion", "CountryRegionCode", "IN_COUNTRY"),
    ("CountryRegionCurrency", "CurrencyCode",      "Currency",      "CurrencyCode",      "USES_CURRENCY"),
    ("CurrencyRate",        "FromCurrencyCode",  "Currency",        "CurrencyCode",     "FROM_CURRENCY"),
    ("CurrencyRate",        "ToCurrencyCode",    "Currency",        "CurrencyCode",     "TO_CURRENCY"),
    ("SalesTerritory",      "CountryRegionCode", "CountryRegion",   "CountryRegionCode","IN_COUNTRY"),
    ("StateProvince",       "CountryRegionCode", "CountryRegion",   "CountryRegionCode","IN_COUNTRY"),
    ("StateProvince",       "TerritoryID",       "SalesTerritory",  "TerritoryID",      "IN_TERRITORY"),
    ("Address",             "StateProvinceID",   "StateProvince",   "StateProvinceID",  "IN_STATE"),
    ("SalesTaxRate",        "StateProvinceID",   "StateProvince",   "StateProvinceID",  "IN_STATE"),
    # Business Entity Addresses
    ("BusinessEntityAddress", "BusinessEntityID","BusinessEntity",  "BusinessEntityID", "HAS_ENTITY"),
    ("BusinessEntityAddress", "AddressID",       "Address",         "AddressID",        "HAS_ADDRESS"),
    ("BusinessEntityAddress", "AddressTypeID",   "AddressType",     "AddressTypeID",    "OF_TYPE"),
    # Sales Territory History
    ("SalesPersonQuotaHistory", "BusinessEntityID","SalesPerson",   "BusinessEntityID", "QUOTA_FOR"),
    ("SalesTerritoryHistory", "BusinessEntityID", "SalesPerson",    "BusinessEntityID", "TERRITORY_HISTORY_OF"),
    ("SalesTerritoryHistory", "TerritoryID",      "SalesTerritory", "TerritoryID",      "IN_TERRITORY"),
    # Customer & Orders
    ("Customer",            "PersonID",          "Person",          "BusinessEntityID", "IS_PERSON"),
    ("Customer",            "StoreID",           "Store",           "BusinessEntityID", "IN_STORE"),
    ("Customer",            "TerritoryID",       "SalesTerritory",  "TerritoryID",      "IN_TERRITORY"),
    ("SalesOrderHeader",    "CustomerID",        "Customer",        "CustomerID",       "ORDERED_BY"),
    ("SalesOrderHeader",    "SalesPersonID",     "SalesPerson",     "BusinessEntityID", "HANDLED_BY"),
    ("SalesOrderHeader",    "TerritoryID",       "SalesTerritory",  "TerritoryID",      "IN_TERRITORY"),
    ("SalesOrderHeader",    "BillToAddressID",   "Address",         "AddressID",        "BILL_TO"),
    ("SalesOrderHeader",    "ShipToAddressID",   "Address",         "AddressID",        "SHIP_TO"),
    ("SalesOrderHeader",    "ShipMethodID",      "ShipMethod",      "ShipMethodID",     "VIA_SHIP_METHOD"),
    ("SalesOrderHeader",    "CreditCardID",      "CreditCard",      "CreditCardID",     "PAID_BY"),
    ("SalesOrderHeader",    "CurrencyRateID",    "CurrencyRate",    "CurrencyRateID",   "AT_CURRENCY_RATE"),
    ("SalesOrderHeaderSalesReason", "SalesOrderID",  "SalesOrderHeader","SalesOrderID", "FOR_ORDER"),
    ("SalesOrderHeaderSalesReason", "SalesReasonID", "SalesReason",  "SalesReasonID",   "HAS_REASON"),
    ("SalesOrderDetail",    "SalesOrderID",      "SalesOrderHeader","SalesOrderID",     "PART_OF_ORDER"),
    ("SalesOrderDetail",    "SpecialOfferID",    "SpecialOffer",    "SpecialOfferID",   "WITH_OFFER"),
    ("SalesOrderDetail",    "ProductID",         "Product",         "ProductID",        "FOR_PRODUCT"),
    # Product hierarchy
    ("ProductSubcategory",  "ProductCategoryID", "ProductCategory", "ProductCategoryID","IN_CATEGORY"),
    ("Product",             "ProductSubcategoryID","ProductSubcategory","ProductSubcategoryID","IN_SUBCATEGORY"),
    ("Product",             "ProductModelID",    "ProductModel",    "ProductModelID",   "HAS_MODEL"),
    ("Product",             "SizeUnitMeasureCode","UnitMeasure",    "UnitMeasureCode",  "SIZE_UNIT"),
    ("Product",             "WeightUnitMeasureCode","UnitMeasure",  "UnitMeasureCode",  "WEIGHT_UNIT"),
    ("ProductModelProductDescriptionCulture","ProductModelID","ProductModel","ProductModelID","FOR_MODEL"),
    ("ProductModelProductDescriptionCulture","ProductDescriptionID","ProductDescription","ProductDescriptionID","HAS_DESCRIPTION"),
    ("ProductModelProductDescriptionCulture","CultureID","Culture", "CultureID",        "IN_CULTURE"),
    ("BillOfMaterials",     "ProductAssemblyID", "Product",         "ProductID",        "ASSEMBLY_OF"),
    ("BillOfMaterials",     "ComponentID",       "Product",         "ProductID",        "HAS_COMPONENT"),
    ("BillOfMaterials",     "UnitMeasureCode",   "UnitMeasure",     "UnitMeasureCode",  "MEASURED_IN"),
    ("ProductCostHistory",  "ProductID",         "Product",         "ProductID",        "COST_HISTORY_OF"),
    ("ProductInventory",    "ProductID",         "Product",         "ProductID",        "INVENTORY_OF"),
    ("ProductInventory",    "LocationID",        "Location",        "LocationID",       "AT_LOCATION"),
    ("ProductListPriceHistory","ProductID",      "Product",         "ProductID",        "PRICE_HISTORY_OF"),
    ("ProductProductPhoto", "ProductID",         "Product",         "ProductID",        "PHOTO_FOR"),
    ("ProductProductPhoto", "ProductPhotoID",    "ProductPhoto",    "ProductPhotoID",   "HAS_PHOTO"),
    ("ProductReview",       "ProductID",         "Product",         "ProductID",        "REVIEW_OF"),
    ("ShoppingCartItem",    "ProductID",         "Product",         "ProductID",        "ITEM_IS"),
    ("SpecialOfferProduct", "SpecialOfferID",    "SpecialOffer",    "SpecialOfferID",   "FOR_OFFER"),
    ("SpecialOfferProduct", "ProductID",         "Product",         "ProductID",        "APPLIES_TO"),
    ("TransactionHistory",  "ProductID",         "Product",         "ProductID",        "TXN_FOR"),
    ("TransactionHistoryArchive","ProductID",    "Product",         "ProductID",        "TXN_ARCHIVE_FOR"),
    # Vendor & Purchasing
    ("ProductVendor",       "ProductID",         "Product",         "ProductID",        "PRODUCT_FROM"),
    ("ProductVendor",       "BusinessEntityID",  "Vendor",          "BusinessEntityID", "SUPPLIED_BY"),
    ("ProductVendor",       "UnitMeasureCode",   "UnitMeasure",     "UnitMeasureCode",  "MEASURED_IN"),
    ("PurchaseOrderHeader", "EmployeeID",        "Employee",        "BusinessEntityID", "ORDERED_BY"),
    ("PurchaseOrderHeader", "VendorID",          "Vendor",          "BusinessEntityID", "FROM_VENDOR"),
    ("PurchaseOrderHeader", "ShipMethodID",      "ShipMethod",      "ShipMethodID",     "VIA_SHIP_METHOD"),
    ("PurchaseOrderDetail", "PurchaseOrderID",   "PurchaseOrderHeader","PurchaseOrderID","PART_OF_PO"),
    ("PurchaseOrderDetail", "ProductID",         "Product",         "ProductID",        "FOR_PRODUCT"),
    # Work Orders
    ("WorkOrder",           "ProductID",         "Product",         "ProductID",        "PRODUCES"),
    ("WorkOrder",           "ScrapReasonID",     "ScrapReason",     "ScrapReasonID",    "SCRAPPED_BECAUSE"),
    ("WorkOrderRouting",    "WorkOrderID",       "WorkOrder",       "WorkOrderID",      "ROUTING_FOR"),
    ("WorkOrderRouting",    "LocationID",        "Location",        "LocationID",       "AT_LOCATION"),
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def clean_row(row: dict) -> dict:
    """Drop BLOB bytes values (Neo4j cannot store binary)."""
    return {k: (None if isinstance(v, bytes) else v) for k, v in row.items()}


def pk_cols(table: str) -> list[str]:
    pk = TABLE_PKS[table]
    return pk if isinstance(pk, list) else [pk]


def build_merge_map(cols: list[str]) -> str:
    """Build the Cypher map literal for MERGE, e.g. {col1: row.col1, col2: row.col2}"""
    return "{" + ", ".join(f"`{c}`: row.`{c}`" for c in cols) + "}"


def batched_run(session, cypher: str, rows: list[dict]):
    """Run a batched UNWIND Cypher with the given rows."""
    for i in range(0, len(rows), BATCH_SIZE):
        session.run(cypher, batch=rows[i : i + BATCH_SIZE])


# ── Step 1: Indexes ──────────────────────────────────────────────────────────

def create_indexes(session):
    print("Creating indexes …")
    for table, pk in TABLE_PKS.items():
        cols = pk if isinstance(pk, list) else [pk]
        for col in cols:
            idx_name = f"idx_{table}_{col}"
            cypher = (
                f"CREATE INDEX {idx_name} IF NOT EXISTS "
                f"FOR (n:`{table}`) ON (n.`{col}`)"
            )
            try:
                session.run(cypher)
            except Exception as e:
                print(f"  Index warning ({table}.{col}): {e}")
    print("  Done.\n")


# ── Step 2: Insert nodes ─────────────────────────────────────────────────────

def insert_all_nodes(sqlite_conn, session):
    print("Inserting nodes …")
    for table, pk in tqdm(TABLE_PKS.items(), desc="Tables"):
        cursor = sqlite_conn.cursor()
        try:
            cursor.execute(f'SELECT * FROM "{table}"')
        except Exception as e:
            tqdm.write(f"  Skipped table {table}: {e}")
            continue

        cols = [d[0] for d in cursor.description]
        pk_list = pk if isinstance(pk, list) else [pk]
        merge_map = build_merge_map(pk_list)

        rows_fetched = cursor.fetchmany(BATCH_SIZE)
        total = 0
        while rows_fetched:
            batch = [clean_row(dict(zip(cols, r))) for r in rows_fetched]
            session.run(
                f"""
                UNWIND $batch AS row
                MERGE (n:`{table}` {merge_map})
                SET n += row
                """,
                batch=batch,
            )
            total += len(batch)
            rows_fetched = cursor.fetchmany(BATCH_SIZE)

        tqdm.write(f"  {table}: {total:,} nodes")
    print()


# ── Step 3: Create FK relationships ─────────────────────────────────────────

def create_fk_relationships(sqlite_conn, session):
    print("Creating relationships …")
    cursor = sqlite_conn.cursor()

    for from_table, fk_col, to_table, to_pk_col, rel_label in tqdm(
        FOREIGN_KEYS, desc="FK relationships"
    ):
        from_pk = pk_cols(from_table)

        # Build SELECT: all PK cols + the FK col
        select_cols = list(from_pk) + ([fk_col] if fk_col not in from_pk else [])
        select_sql = ", ".join(f'"{c}"' for c in select_cols)

        try:
            cursor.execute(
                f'SELECT {select_sql} FROM "{from_table}" '
                f'WHERE "{fk_col}" IS NOT NULL'
            )
        except Exception as e:
            tqdm.write(f"  Skipped {from_table}.{fk_col} → {to_table}: {e}")
            continue

        from_merge_map = build_merge_map(from_pk)

        total = 0
        rows_fetched = cursor.fetchmany(BATCH_SIZE)
        while rows_fetched:
            batch = []
            for row in rows_fetched:
                d = dict(zip(select_cols, row))
                batch.append({"src": {c: d[c] for c in from_pk}, "tgt_pk": d[fk_col]})

            session.run(
                f"""
                UNWIND $batch AS row
                MATCH (a:`{from_table}` {from_merge_map.replace("row.", "row.src.")})
                MATCH (b:`{to_table}` {{`{to_pk_col}`: row.tgt_pk}})
                MERGE (a)-[:`{rel_label}`]->(b)
                """,
                batch=batch,
            )
            total += len(batch)
            rows_fetched = cursor.fetchmany(BATCH_SIZE)

        tqdm.write(f"  [{rel_label}] {from_table} → {to_table}: {total:,}")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    auth = None if NEO4J_PASSWORD is None else (NEO4J_USERNAME, NEO4J_PASSWORD)  # unset: auth-disabled throwaway container
    if not os.path.exists(SQLITE_PATH):
        sys.exit(f"SQLite database not found: {SQLITE_PATH}")
    print(f"Connecting to Neo4j: {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=auth)

    print(f"Connecting to SQLite: {SQLITE_PATH}\n")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)

    with driver.session() as session:
        create_indexes(session)
        insert_all_nodes(sqlite_conn, session)
        create_fk_relationships(sqlite_conn, session)

    sqlite_conn.close()
    driver.close()

    print("=" * 60)
    print("Done! Verification queries:")
    print("  MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY label")
    print("  MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt ORDER BY rel")
    print("=" * 60)


if __name__ == "__main__":
    main()
