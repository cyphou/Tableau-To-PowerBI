let
    // Source Snowflake: analytics.snowflakecomputing.com
    Source = try

        let

            _src = Snowflake.Databases("analytics.snowflakecomputing.com", "ANALYTICS_WH"),

            _nav = _src{[Name="ENTERPRISE_DW"]}[Data]

        in _nav

    otherwise

        #table({"product_key", "product_id", "product_name", "category", "subcategory", "brand", "supplier", "weight_kg", "is_perishable", "launch_date"}, {}),
    #"SALES" = Source{[Name="SALES"]}[Data],
    #"dim_product Table" = #"SALES"{[Name="dim_product"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(#"dim_product Table", {{"product_id", "Product ID"}, {"product_name", "Product Name"}, {"category", "Category"}, {"subcategory", "Subcategory"}, {"brand", "Brand"}, {"supplier", "Supplier"}, {"weight_kg", "Weight (kg)"}, {"is_perishable", "Perishable?"}, {"launch_date", "Launch Date"}}),
    Result = #"Renamed Columns"
in
    Result