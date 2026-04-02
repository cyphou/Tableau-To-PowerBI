let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Order_ID", "Order_Date", "Customer_ID", "Product_ID", "Region", "Sales", "Quantity", "Discount", "Profit", "Ship_Mode", "Status", "_temp_col"},
            {
                {"Sample 1", 2, "Sample 3", "Sample 4", "Sample 5", 6, 7, 8, 9, "Sample 10", "Sample 11", "Sample 12"},
                {"Sample 2", 3, "Sample 4", "Sample 5", "Sample 6", 7, 8, 9, 10, "Sample 11", "Sample 12", "Sample 13"}
            }
        )
    otherwise
        #table({"Order_ID", "Order_Date", "Customer_ID", "Product_ID", "Region", "Sales", "Quantity", "Discount", "Profit", "Ship_Mode", "Status", "_temp_col"}, {}),
    #"Removed Columns" = Table.RemoveColumns(Source, {"_temp_col"}),
    #"Renamed Columns" = Table.RenameColumns(#"Removed Columns", {{"Order_ID", "OrderID"}, {"Order_Date", "OrderDate"}, {"Customer_ID", "CustomerID"}, {"Product_ID", "ProductID"}}),
    #"Trimmed Text" = Table.TransformColumns(#"Renamed Columns", {{"Region", Text.Trim}}),
    #"Filtered Rows" = Table.SelectRows(#"Trimmed Text", each [Status] <> "Cancelled"),
    #"Removed Columns 2" = Table.RemoveColumns(#"Filtered Rows", {"Status"}),
    #"Replaced Nulls in Discount" = Table.ReplaceValue(#"Removed Columns 2", null, "0", Replacer.ReplaceValue, {"Discount"}),
    #"Added Revenue" = Table.AddColumn(#"Replaced Nulls in Discount", "Revenue", each [Sales] * (1 - [Discount])),
    #"Changed Type" = Table.TransformColumnTypes(#"Added Revenue", {{"OrderDate", type date}}),
    Result = #"Changed Type"
in
    Result