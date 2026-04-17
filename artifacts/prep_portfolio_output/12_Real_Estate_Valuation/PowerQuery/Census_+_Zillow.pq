let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"zip_code", "median_household_income", "population", "poverty_rate", "education_bachelors_pct", "crime_index", "school_rating"},
            {
                {"Sample 1", 2, 3, 4, 5, 6, 7},
                {"Sample 2", 3, 4, 5, 6, 7, 8}
            }
        )
    otherwise
        #table({"zip_code", "median_household_income", "population", "poverty_rate", "education_bachelors_pct", "crime_index", "school_rating"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "zip_code", Zillow_Estimates, "zip_code", "Joined", JoinKind.Inner),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"zestimate_median", "rent_zestimate", "price_change_yoy_pct", "days_on_market_median", "month"}),
    Result = #"Expanded Joined"
in
    Result