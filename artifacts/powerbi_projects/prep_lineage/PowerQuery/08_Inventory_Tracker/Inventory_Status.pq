let
    // TODO: Configure the data source for connector type: postgres
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"customer_id", "first_name", "last_name", "email", "segment", "lifetime_value"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", 6},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", 7}
            }
        )
    otherwise
        #table({"customer_id", "first_name", "last_name", "email", "segment", "lifetime_value"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "customer_id", Inventory_Levels, "WAREHOUSE_ID", "Joined", JoinKind.FullOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"SKU", "QTY_ON_HAND", "QTY_RESERVED", "REORDER_POINT", "LAST_RECEIPT_DATE", "UNIT_COST"}),
    #"Added AvailableQty" = Table.AddColumn(#"Expanded Joined", "AvailableQty", each [QTY_ON_HAND] - [QTY_RESERVED]),
    #"Added NeedsReorder" = Table.AddColumn(#"Added AvailableQty", "NeedsReorder", each if [AvailableQty] < [REORDER_POINT] then 'Yes' else 'No' ),
    #"Added InventoryValue" = Table.AddColumn(#"Added NeedsReorder", "InventoryValue", each [QTY_ON_HAND] * [UNIT_COST]),
    Result = #"Added InventoryValue"
in
    Result