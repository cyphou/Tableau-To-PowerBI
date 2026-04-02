let
    // Source Oracle: mfg-oracle.corp.local:1521/MFGDB
    Source = try

        let

            _src = Oracle.Database("mfg-oracle.corp.local:1521/MFGDB"),

            _nav = _src{[Schema="DBO", Item="Machines"]}[Data]

        in _nav

    otherwise

        #table({"machine_id", "machine_name", "machine_type", "install_date", "location", "line_id", "rated_capacity"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"machine_id", "Machine ID"}, {"machine_name", "Machine Name"}, {"machine_type", "Machine Type"}, {"install_date", "Install Date"}, {"location", "Location"}, {"line_id", "Line ID"}, {"rated_capacity", "Rated Capacity"}}),
    Result = #"Renamed Columns"
in
    Result