let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Product_ID", "Product_Name", "Category", "Sub_Category", "Unit_Cost", "Unit_Price", "Supplier", "Weight_kg"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5, 6, "Sample 7", 8},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, "Sample 8", 9}
            }
        )
    otherwise
        #table({"Product_ID", "Product_Name", "Category", "Sub_Category", "Unit_Cost", "Unit_Price", "Supplier", "Weight_kg"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"Product_ID", "ProductID"}, {"Product_Name", "ProductName"}, {"Sub_Category", "SubCategory"}, {"Unit_Cost", "UnitCost"}, {"Unit_Price", "UnitPrice"}}),
    #"Proper Cased" = Table.TransformColumns(#"Renamed Columns", {{"ProductName", Text.Proper}}),
    #"Trimmed Text" = Table.TransformColumns(#"Proper Cased", {{"Category", Text.Trim}}),
    #"Replaced Nulls in Weight_kg" = Table.ReplaceValue(#"Trimmed Text", null, "0", Replacer.ReplaceValue, {"Weight_kg"}),
    #"Added Margin" = Table.AddColumn(#"Replaced Nulls in Weight_kg", "Margin", each ([UnitPrice] - [UnitCost]) / [UnitPrice]),
    Result = #"Added Margin"
in
    Result