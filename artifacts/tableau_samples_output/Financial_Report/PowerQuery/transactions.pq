let
    // Source PostgreSQL
    Source = try

        let

            _src = PostgreSQL.Database("db.company.com:5432", "finance"),

            _nav = _src{[Schema="public", Item="transactions"]}[Data]

        in _nav

    otherwise

        #table({"transaction_id", "transaction_date", "account", "category", "amount", "type", "business_unit", "cost_center"}, {}),
    Result = Source
in
    Result