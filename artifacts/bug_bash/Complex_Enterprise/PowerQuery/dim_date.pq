let
    // Source Snowflake: analytics.snowflakecomputing.com
    Source = try

        let

            _src = Snowflake.Databases("analytics.snowflakecomputing.com", "ANALYTICS_WH"),

            _nav = _src{[Name="ENTERPRISE_DW"]}[Data]

        in _nav

    otherwise

        #table({"date_key", "full_date", "year", "quarter", "month_num", "month_name", "week_num", "day_name", "is_weekend", "is_holiday", "fiscal_quarter", "fiscal_year"}, {}),
    #"SALES" = Source{[Name="SALES"]}[Data],
    #"dim_date Table" = #"SALES"{[Name="dim_date"]}[Data],
    #"Renamed Columns" = Table.RenameColumns(#"dim_date Table", {{"full_date", "Full Date"}, {"year", "Year"}, {"quarter", "Quarter"}, {"month_num", "Month"}, {"month_name", "Month Name"}, {"week_num", "Week"}, {"day_name", "Day Name"}, {"is_weekend", "Weekend?"}, {"is_holiday", "Holiday?"}, {"fiscal_quarter", "Fiscal Quarter"}, {"fiscal_year", "Fiscal Year"}}),
    Result = #"Renamed Columns"
in
    Result