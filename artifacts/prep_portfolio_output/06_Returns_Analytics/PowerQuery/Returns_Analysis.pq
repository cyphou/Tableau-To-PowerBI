let
    // TODO: Configure the data source for connector type: sqlserver
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"ReturnID", "OrderID", "ReturnDate", "ReasonCode", "Reason_Text", "RefundAmount", "NetRefund"},
            {
                {"Sample 1", "Sample 2", 3, "Sample 4", "Sample 5", 6, 7},
                {"Sample 2", "Sample 3", 4, "Sample 5", "Sample 6", 7, 8}
            }
        )
    otherwise
        #table({"ReturnID", "OrderID", "ReturnDate", "ReasonCode", "Reason_Text", "RefundAmount", "NetRefund"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "OrderID", Orders_Clean, "OrderID", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"OrderDate", "CustomerID", "ProductID", "Region", "Sales", "Revenue"}),
    #"Added ReturnRate" = Table.AddColumn(#"Expanded Joined", "ReturnRate", each [NetRefund] / [Revenue]),
    #"Added DaysToReturn" = Table.AddColumn(#"Added ReturnRate", "DaysToReturn", each DATEDIFF('day', [OrderDate], [ReturnDate])),
    #"Script Warning" = Table.AddColumn(#"Added DaysToReturn", "__script_warning", each "/* Python script step not auto-converted — manual migration required */", type text),
    Result = #"Script Warning"
in
    Result