let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"OrderID", "OrderDate", "CustomerID", "ProductID", "Region", "Sales", "Quantity", "Discount", "Profit", "Revenue"},
            {
                {"Sample 1", 2, "Sample 3", "Sample 4", "Sample 5", 6, 7, 8, 9, 10},
                {"Sample 2", 3, "Sample 4", "Sample 5", "Sample 6", 7, 8, 9, 10, 11}
            }
        )
    otherwise
        #table({"OrderID", "OrderDate", "CustomerID", "ProductID", "Region", "Sales", "Quantity", "Discount", "Profit", "Revenue"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "ProductID", Products_Master, "ProductID", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"ProductName", "Category", "SubCategory", "UnitCost", "UnitPrice", "Margin"}),
    Result = #"Expanded Joined"
in
    Result