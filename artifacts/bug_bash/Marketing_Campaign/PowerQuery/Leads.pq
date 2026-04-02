let
    // Source MySQL: analytics-mysql.corp.local:3306
    Source = try

        let

            _src = MySQL.Database("analytics-mysql.corp.local:3306", "marketing_db"),

            _nav = _src{[Schema="marketing_db", Item="Leads"]}[Data]

        in _nav

    otherwise

        #table({"lead_id", "campaign_id", "lead_name", "email", "phone", "company", "job_title", "created_date", "deal_value", "lead_source", "lead_status", "engagement_score"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"lead_id", "Lead ID"}, {"campaign_id", "Campaign ID"}, {"lead_name", "Lead Name"}, {"email", "Email"}, {"phone", "Phone"}, {"company", "Company"}, {"job_title", "Job Title"}, {"created_date", "Created Date"}, {"deal_value", "Deal Value"}, {"lead_source", "Lead Source"}, {"lead_status", "Lead Status"}, {"engagement_score", "Engagement Score"}}),
    Result = #"Renamed Columns"
in
    Result