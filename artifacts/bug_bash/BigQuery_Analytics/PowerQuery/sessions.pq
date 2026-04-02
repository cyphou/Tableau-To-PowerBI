let
    // Source Google BigQuery: my-analytics-project.web_data
    Source = try

        let

            _src = GoogleBigQuery.Database([BillingProject="my-analytics-project"]),

            _nav = _src{[Name="web_data"]}[Data]

        in _nav

    otherwise

        #table({"session_id", "session_date", "user_id", "channel", "device_type", "country", "page_views", "session_duration", "converted", "revenue"}, {}),
    #"sessions Table" = Source{[Name="sessions"]}[Data],
    #"Added Channel Category" = Table.AddColumn(#"sessions Table", "Channel Category", each if [channel] = "Organic Search"  or  [channel] = "Paid Search" then "Search" else if [channel] = "Social"  or  [channel] = "Referral" then "Social/Referral" else if [channel] = "Direct" then "Direct" else "Other", type text),
    #"Added Engagement Level" = Table.AddColumn(#"Added Channel Category", "Engagement Level", each if [page_views] >= 10 then "High" else if [page_views] >= 5 then "Medium" else "Low", type text),
    Result = #"Added Engagement Level"
in
    Result