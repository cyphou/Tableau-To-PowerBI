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
        #table({"Country", "ISO_Code", "Coal_TWh", "Gas_TWh", "Nuclear_TWh", "Hydro_TWh", "Wind_TWh", "Solar_TWh", "Other_Renewables_TWh", "Year"}, {}),
    #"Combined Tables" = Table.Combine({Electricity_2023, Electricity_2024}),
    #"Added EnergyCategory" = Table.AddColumn(#"Combined Tables", "EnergyCategory", each if [EnergySource] = 'Coal' or [EnergySource] = 'Gas' then 'Fossil' else if [EnergySource] = 'Nuclear' then 'Nuclear' else 'Renewable' ),
    #"Added IsRenewable" = Table.AddColumn(#"Added EnergyCategory", "IsRenewable", each if [EnergyCategory] = 'Renewable' then 1 else 0 ),
    #"Filtered Rows" = Table.SelectRows(#"Added IsRenewable", each [Generation_TWh] > 0),
    Result = #"Filtered Rows"
in
    Result