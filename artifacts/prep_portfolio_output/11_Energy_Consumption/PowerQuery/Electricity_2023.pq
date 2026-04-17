let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Country", "ISO_Code", "Coal_TWh", "Gas_TWh", "Nuclear_TWh", "Hydro_TWh", "Wind_TWh", "Solar_TWh", "Other_Renewables_TWh", "Year"},
            {
                {"Sample 1", "Sample 2", 3, 4, 5, 6, 7, 8, 9, 10},
                {"Sample 2", "Sample 3", 4, 5, 6, 7, 8, 9, 10, 11}
            }
        )
    otherwise
        #table({"Country", "ISO_Code", "Coal_TWh", "Gas_TWh", "Nuclear_TWh", "Hydro_TWh", "Wind_TWh", "Solar_TWh", "Other_Renewables_TWh", "Year"}, {})  // Empty table on error
in
    Source