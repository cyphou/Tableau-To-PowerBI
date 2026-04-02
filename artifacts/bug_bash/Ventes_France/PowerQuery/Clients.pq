let
    // Source PostgreSQL
    Source = try

        let

            _src = PostgreSQL.Database("db.entreprise.fr:5432", "ventes_db"),

            _nav = _src{[Schema="public", Item="Clients"]}[Data]

        in _nav

    otherwise

        #table({"client_id", "nom_client", "prenom_client", "email", "segment", "type_client", "date_inscription"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"client_id", "ID Client"}, {"nom_client", "Nom du Client"}, {"prenom_client", "Prénom du Client"}, {"email", "Email"}, {"segment", "Segment"}, {"type_client", "Type de Client"}, {"date_inscription", "Date d'Inscription"}}),
    Result = #"Renamed Columns"
in
    Result