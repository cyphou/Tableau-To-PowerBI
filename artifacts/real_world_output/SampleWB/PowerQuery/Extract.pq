let
    // TODO: Configure the data source for connector type: DATAENGINE
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"Country / Region", "Date", "F: Deposit interest rate (%)", "F: GDP (curr $)", "F: GDP per capita (curr $)", "F: Lending interest rate (%)", "H: Health exp (% GDP)", "H: Health exp/cap (curr $)", "H: Life exp (years)", "Number of Records", "P: Population (count)", "Region", "Subregion"},
            {
                {"Sample 1", 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, "Sample 12", "Sample 13"},
                {"Sample 2", 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "Sample 13", "Sample 14"}
            }
        )
    otherwise
        #table({"Country / Region", "Date", "F: Deposit interest rate (%)", "F: GDP (curr $)", "F: GDP per capita (curr $)", "F: Lending interest rate (%)", "H: Health exp (% GDP)", "H: Health exp/cap (curr $)", "H: Life exp (years)", "Number of Records", "P: Population (count)", "Region", "Subregion"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"Date", "Date (year)"}, {"F: Deposit interest rate (%)", "Deposit interest rate (%)"}, {"F: GDP (curr $)", "GDP (curr $)"}, {"F: GDP per capita (curr $)", "GDP per capita (curr $)"}, {"F: Lending interest rate (%)", "Lending interest rate (%)"}, {"H: Health exp (% GDP)", "Health exp (% GDP)"}, {"H: Health exp/cap (curr $)", "Health exp/cap (curr $)"}, {"H: Life exp (years)", "Life exp (years)"}, {"P: Population (count)", "Population (count)"}}),
    #"Added Action (Country Name)" = Table.AddColumn(#"Renamed Columns", "Action (Country Name)", each Text.From([#"Country / Region"]), type text),
    #"Added Action (Date (year))" = Table.AddColumn(#"Added Action (Country Name)", "Action (Date (year))", each Text.From([#"Date"]), type text),
    #"Added Action (Region)" = Table.AddColumn(#"Added Action (Date (year))", "Action (Region)", each Text.From([#"Region"]), type text),
    #"Added Action (YEAR(Date (year)))" = Table.AddColumn(#"Added Action (Region)", "Action (YEAR(Date (year)))", each Text.From(Date.Year([#"Date"])), type text),
    #"Added Exclusions (Country Name,YEAR(Date (year)))" = Table.AddColumn(#"Added Action (YEAR(Date (year)))", "Exclusions (Country Name,YEAR(Date (year)))", each Text.From([#"Country / Region"]) & " | " & Text.From(Date.Year([#"Date"])), type text),
    Result = #"Added Exclusions (Country Name,YEAR(Date (year)))"
in
    Result