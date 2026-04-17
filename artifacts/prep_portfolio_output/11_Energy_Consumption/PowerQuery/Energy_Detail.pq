let
    // TODO: Configure the data source for connector type: excel-direct
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"ISO_Code", "Country_Name", "Population_M", "GDP_Billion_USD", "Region", "IncomeGroup", "Year"},
            {
                {"Sample 1", "Sample 2", 3, 4, "Sample 5", "Sample 6", 7},
                {"Sample 2", "Sample 3", 4, 5, "Sample 6", "Sample 7", 8}
            }
        )
    otherwise
        #table({"ISO_Code", "Country_Name", "Population_M", "GDP_Billion_USD", "Region", "IncomeGroup", "Year"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, {"ISO_Code", "Year"}, Classify_Energy_Type, {"ISO_Code", "Year"}, "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"Country", "Coal_TWh", "Gas_TWh", "Nuclear_TWh", "Hydro_TWh", "Wind_TWh", "Solar_TWh", "Other_Renewables_TWh"}),
    #"Added GenPerCapita_MWh" = Table.AddColumn(#"Expanded Joined", "GenPerCapita_MWh", each ([Generation_TWh] * 1000000) / ([Population_M] * 1000000)),
    #"Added GenPerGDP" = Table.AddColumn(#"Added GenPerCapita_MWh", "GenPerGDP", each [Generation_TWh] / [GDP_Billion_USD]),
    #"Removed Columns" = Table.RemoveColumns(#"Added GenPerGDP", {"Country_Name"}),
    Result = #"Removed Columns"
in
    Result