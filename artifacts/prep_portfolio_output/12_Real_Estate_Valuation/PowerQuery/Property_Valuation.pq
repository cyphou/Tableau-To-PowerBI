let
    // TODO: Configure the data source for connector type: snowflake
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"listing_id", "address", "city", "state", "zip_code", "latitude", "longitude", "property_type", "bedrooms", "bathrooms", "sqft", "lot_size_sqft", "year_built", "list_price", "list_date", "status", "agent_id"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, "Sample 8", 9, 10, 11, 12, 13, 14, 15, "Sample 16", "Sample 17"},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", 7, 8, "Sample 9", 10, 11, 12, 13, 14, 15, 16, "Sample 17", "Sample 18"}
            }
        )
    otherwise
        #table({"listing_id", "address", "city", "state", "zip_code", "latitude", "longitude", "property_type", "bedrooms", "bathrooms", "sqft", "lot_size_sqft", "year_built", "list_price", "list_date", "status", "agent_id"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "listing_id", Sales_Transactions, "listing_id", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"transaction_id", "sale_price", "sale_date", "buyer_id", "financing_type", "closing_costs", "commission_pct"}),
    #"Joined Joined 2" = Table.NestedJoin(#"Expanded Joined", "zip_code", Census_+_Zillow, "zip_code", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined 2" = Table.ExpandTableColumn(#"Joined Joined 2", "Joined", {"median_household_income", "population", "poverty_rate", "education_bachelors_pct", "crime_index", "school_rating"}),
    #"Added PricePerSqft" = Table.AddColumn(#"Expanded Joined 2", "PricePerSqft", each [list_price] / [sqft]),
    #"Added SaleToListRatio" = Table.AddColumn(#"Added PricePerSqft", "SaleToListRatio", each if not (null = [sale_price]) then [sale_price] / [list_price] else NULL ),
    #"Added DaysOnMarket" = Table.AddColumn(#"Added SaleToListRatio", "DaysOnMarket", each if not (null = [sale_date]) then DATEDIFF('day', [list_date], [sale_date]) else DATEDIFF('day', [list_date], TODAY()) ),
    #"Added PropertyAge" = Table.AddColumn(#"Added DaysOnMarket", "PropertyAge", each YEAR(TODAY()) - [year_built]),
    #"Added PriceToIncome" = Table.AddColumn(#"Added PropertyAge", "PriceToIncome", each [list_price] / [median_household_income]),
    #"Added ZestimateGap" = Table.AddColumn(#"Added PriceToIncome", "ZestimateGap", each ([list_price] - [zestimate_median]) / [zestimate_median]),
    #"Added MarketSegment" = Table.AddColumn(#"Added ZestimateGap", "MarketSegment", each if [list_price] < 200000 then 'Starter' else if [list_price] < 500000 then 'Mid-Market' else if [list_price] < 1000000 then 'Upscale' else 'Luxury' ),
    #"Added CapRate" = Table.AddColumn(#"Added MarketSegment", "CapRate", each ([rent_zestimate] * 12) / [list_price]),
    #"Renamed Columns" = Table.RenameColumns(#"Added CapRate", {{"listing_id", "ListingID"}, {"zip_code", "ZipCode"}}),
    Result = #"Renamed Columns"
in
    Result