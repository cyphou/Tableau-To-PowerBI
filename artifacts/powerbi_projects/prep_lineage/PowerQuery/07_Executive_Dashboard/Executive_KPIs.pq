let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Region", "Category", "segment", "TotalRevenue", "TotalProfit", "OrderCount"},
            {
                {"Sample 1", "Sample 2", "Sample 3", 4, 5, 6},
                {"Sample 2", "Sample 3", "Sample 4", 5, 6, 7}
            }
        )
    otherwise
        #table({"Region", "Category", "segment", "TotalRevenue", "TotalProfit", "OrderCount"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "Region", Returns_Analysis, "Region", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"ReasonCode", "NetRefund", "ReturnRate", "anomaly_score"}),
    #"Grouped Rows" = Table.Group(#"Expanded Joined", {"Region"}, {{"GrandRevenue", each List.Sum([TotalRevenue]), type number}, {"GrandProfit", each List.Sum([TotalProfit]), type number}, {"TotalOrders", each List.Sum([OrderCount]), type number}, {"TotalRefunds", each List.Sum([NetRefund]), type number}, {"AvgReturnRate", each List.Average([ReturnRate]), type number}}),
    #"Added ProfitMargin" = Table.AddColumn(#"Grouped Rows", "ProfitMargin", each [GrandProfit] / [GrandRevenue]),
    #"Added NetRevenue" = Table.AddColumn(#"Added ProfitMargin", "NetRevenue", each [GrandRevenue] - [TotalRefunds]),
    #"Added AvgOrderValue" = Table.AddColumn(#"Added NetRevenue", "AvgOrderValue", each [GrandRevenue] / [TotalOrders]),
    Result = #"Added AvgOrderValue"
in
    Result