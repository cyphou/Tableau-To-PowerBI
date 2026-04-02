let
    // Source SQL Server
    Source = try

        let

            _src = Sql.Database("localhost", "SalesDB"),

            _nav = _src{[Schema="dbo", Item="Regions"]}[Data]

        in _nav

    otherwise

        #table({"RegionName", "RegionManager"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"RegionName", "Region Name"}, {"RegionManager", "Region Manager"}}),
    Result = #"Renamed Columns"
in
    Result