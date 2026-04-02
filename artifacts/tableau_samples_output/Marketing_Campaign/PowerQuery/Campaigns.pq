let
    // Source MySQL: analytics-mysql.corp.local:3306
    Source = try

        let

            _src = MySQL.Database("analytics-mysql.corp.local:3306", "marketing_db"),

            _nav = _src{[Schema="marketing_db", Item="Campaigns"]}[Data]

        in _nav

    otherwise

        #table({"campaign_id", "campaign_name", "channel", "start_date", "end_date", "budget", "spend", "target_audience", "creative_url", "utm_source", "utm_medium", "utm_campaign", "region", "status"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"campaign_id", "Campaign ID"}, {"campaign_name", "Campaign Name"}, {"channel", "Channel"}, {"start_date", "Start Date"}, {"end_date", "End Date"}, {"budget", "Budget"}, {"spend", "Spend"}, {"target_audience", "Target Audience"}, {"creative_url", "Creative URL"}, {"utm_source", "UTM Source"}, {"utm_medium", "UTM Medium"}, {"utm_campaign", "UTM Campaign"}, {"region", "Region"}, {"status", "Status"}}),
    #"Added Is Enterprise" = Table.AddColumn(#"Renamed Columns", "Is Enterprise", each Text.Contains([target_audience], "Enterprise"), type logical),
    #"Added Campaign Year" = Table.AddColumn(#"Added Is Enterprise", "Campaign Year", each #date(Date.Year([start_date]), 1, 1), type datetime),
    #"Added Start Month" = Table.AddColumn(#"Added Campaign Year", "Start Month", each Date.Month([start_date]), Int64.Type),
    #"Added Campaign Days" = Table.AddColumn(#"Added Start Month", "Campaign Days", each Duration.Days([end_date] - [start_date]), Int64.Type),
    Result = #"Added Campaign Days"
in
    Result