let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"CustomerID", "CustomerName", "segment", "loyalty_tier", "city", "state", "country"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", "Sample 7"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", "Sample 7", "Sample 8"}
            }
        )
    otherwise
        #table({"CustomerID", "CustomerName", "segment", "loyalty_tier", "city", "state", "country"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "CustomerID", Orders_+_Products, "CustomerID", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"OrderID", "OrderDate", "ProductID", "Region", "Sales", "Quantity", "Discount", "Profit", "Revenue"}),
    #"Grouped Rows" = Table.Group(#"Expanded Joined", {"Region", "Category", "segment", "loyalty_tier"}, {{"TotalRevenue", each List.Sum([Revenue]), type number}, {"TotalProfit", each List.Sum([Profit]), type number}, {"OrderCount", each List.Count(List.Distinct([OrderID])), Int64.Type}, {"TotalQuantity", each List.Sum([Quantity]), type number}, {"AvgDiscount", each List.Average([Discount]), type number}}),
    Result = #"Grouped Rows"
in
    Result