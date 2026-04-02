let
    // Source Oracle: mfg-oracle.corp.local:1521/MFGDB
    Source = try

        let

            _src = Oracle.Database("mfg-oracle.corp.local:1521/MFGDB"),

            _nav = _src{[Schema="DBO", Item="Sensors"]}[Data]

        in _nav

    otherwise

        #table({"reading_id", "reading_time", "machine_id", "sensor_type", "value", "threshold_min", "threshold_max", "unit", "quality_score", "plant_id", "delta_value", "angle_degrees", "power_watts"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"reading_id", "Reading ID"}, {"reading_time", "Reading Time"}, {"machine_id", "Machine ID"}, {"sensor_type", "Sensor Type"}, {"value", "Sensor Value"}, {"threshold_min", "Min Threshold"}, {"threshold_max", "Max Threshold"}, {"unit", "Unit"}, {"quality_score", "Quality Score"}, {"plant_id", "Plant ID"}, {"delta_value", "Delta Value"}, {"angle_degrees", "Angle (Degrees)"}, {"power_watts", "Power (Watts)"}}),
    #"Added Abs Deviation" = Table.AddColumn(#"Renamed Columns", "Abs Deviation", each Number.Abs([value] - ([threshold_min] + [threshold_max]) / 2), type number),
    #"Added Floor Value" = Table.AddColumn(#"Added Abs Deviation", "Floor Value", each Number.RoundDown([value] / 1) * 1, type number),
    #"Added Rounded Value" = Table.AddColumn(#"Added Floor Value", "Rounded Value", each Number.Round([value], 2), type number),
    #"Added Reading Month" = Table.AddColumn(#"Added Rounded Value", "Reading Month", each #date(Date.Year([reading_time]), Date.Month([reading_time]), 1), type datetime),
    Result = #"Added Reading Month"
in
    Result