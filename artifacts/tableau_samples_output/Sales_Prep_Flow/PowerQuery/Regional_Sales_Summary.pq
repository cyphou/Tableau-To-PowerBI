let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Order_ID", "Order_Date", "Customer_ID", "Region", "Category", "Product_Name", "Sales", "Quantity", "Discount", "Profit", "Status", "TempCol"},
            {
                {"Sample 1", 2, "Sample 3", "Sample 4", "Sample 5", "Sample 6", 7, 8, 9, 10, "Sample 11", "Sample 12"},
                {"Sample 2", 3, "Sample 4", "Sample 5", "Sample 6", "Sample 7", 8, 9, 10, 11, "Sample 12", "Sample 13"}
            }
        )
    otherwise
        #table({"Order_ID", "Order_Date", "Customer_ID", "Region", "Category", "Product_Name", "Sales", "Quantity", "Discount", "Profit", "Status", "TempCol"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"Order_ID", "Order ID"}, {"Order_Date", "Order Date"}, {"Customer_ID", "Customer ID"}, {"Product_Name", "Product Name"}}),
    #"Removed Columns" = Table.RemoveColumns(#"Renamed Columns", {"TempCol"}),
    #"Filtered Rows" = Table.SelectRows(#"Removed Columns", each [Status] <> "Cancelled"),
    #"Trimmed Text" = Table.TransformColumns(#"Filtered Rows", {{"Region", Text.Trim}}),
    #"Proper Cased" = Table.TransformColumns(#"Trimmed Text", {{"Category", Text.Proper}}),
    #"Replaced Nulls in Discount" = Table.ReplaceValue(#"Proper Cased", null, "0", Replacer.ReplaceValue, {"Discount"}),
    #"Added Revenue" = Table.AddColumn(#"Replaced Nulls in Discount", "Revenue", each [Sales] * [Quantity] * (1 - [Discount])),
    #"Changed Type" = Table.TransformColumnTypes(#"Added Revenue", {{"Order Date", type date}}),
    #"Joined Joined" = Table.NestedJoin(#"Changed Type", "Customer ID", Customers, "Customer_ID", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"Customer_Name", "Segment", "City", "State", "Country"}),
    #"Grouped Rows" = Table.Group(#"Expanded Joined", {"Region", "Category", "Segment"}, {{"Total Revenue", each List.Sum([Revenue]), type number}, {"Total Profit", each List.Sum([Profit]), type number}, {"Distinct Orders", each List.Count(List.Distinct([Order ID])), Int64.Type}, {"Avg Quantity", each List.Average([Quantity]), type number}}),
    Result = #"Grouped Rows"
in
    Result