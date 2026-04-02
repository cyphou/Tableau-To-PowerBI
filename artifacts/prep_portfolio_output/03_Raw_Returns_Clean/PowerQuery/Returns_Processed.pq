let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Return_ID", "Order_ID", "Return_Date", "Reason_Code", "Reason_Text", "Refund_Amount", "Restocking_Fee", "Return_Status"},
            {
                {"Sample 1", "Sample 2", 3, "Sample 4", "Sample 5", 6, 7, "Sample 8"},
                {"Sample 2", "Sample 3", 4, "Sample 5", "Sample 6", 7, 8, "Sample 9"}
            }
        )
    otherwise
        #table({"Return_ID", "Order_ID", "Return_Date", "Reason_Code", "Reason_Text", "Refund_Amount", "Restocking_Fee", "Return_Status"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"Return_ID", "ReturnID"}, {"Order_ID", "OrderID"}, {"Return_Date", "ReturnDate"}, {"Reason_Code", "ReasonCode"}, {"Refund_Amount", "RefundAmount"}}),
    #"Filtered Rows" = Table.SelectRows(#"Renamed Columns", each [Return_Status] <> "Voided"),
    #"Removed Columns" = Table.RemoveColumns(#"Filtered Rows", {"Return_Status"}),
    #"Trimmed Text" = Table.TransformColumns(#"Removed Columns", {{"Reason_Text", Text.Trim}}),
    #"Added NetRefund" = Table.AddColumn(#"Trimmed Text", "NetRefund", each [RefundAmount] - [Restocking_Fee]),
    Result = #"Added NetRefund"
in
    Result