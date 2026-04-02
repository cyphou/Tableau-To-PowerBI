let
    // TODO: Configure the data source for connector type: snowflake
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"SKU", "WAREHOUSE_ID", "QTY_ON_HAND", "QTY_RESERVED", "REORDER_POINT", "LAST_RECEIPT_DATE", "UNIT_COST"},
            {
                {"Sample 1", "Sample 2", 3, 4, 5, 6, 7},
                {"Sample 2", "Sample 3", 4, 5, 6, 7, 8}
            }
        )
    otherwise
        #table({"SKU", "WAREHOUSE_ID", "QTY_ON_HAND", "QTY_RESERVED", "REORDER_POINT", "LAST_RECEIPT_DATE", "UNIT_COST"}, {})  // Empty table on error
in
    Source