let
    // Source PostgreSQL
    Source = try

        let

            _src = PostgreSQL.Database("db.entreprise.fr:5432", "ventes_db"),

            _nav = _src{[Schema="public", Item="Commandes"]}[Data]

        in _nav

    otherwise

        #table({"commande_id", "date_commande", "date_livraison", "client_id", "produit_id", "region", "departement", "ville", "code_postal", "quantite", "prix_unitaire", "remise", "frais_port", "mode_paiement", "statut", "commercial"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"commande_id", "N° Commande"}, {"date_commande", "Date de Commande"}, {"date_livraison", "Date de Livraison"}, {"client_id", "ID Client"}, {"produit_id", "ID Produit"}, {"region", "Région"}, {"departement", "Département"}, {"ville", "Ville"}, {"code_postal", "Code Postal"}, {"quantite", "Quantité"}, {"prix_unitaire", "Prix Unitaire"}, {"remise", "Remise"}, {"frais_port", "Frais de Port"}, {"mode_paiement", "Mode de Paiement"}, {"statut", "Statut"}, {"commercial", "Commercial"}}),
    #"Added Délai de Livraison" = Table.AddColumn(#"Renamed Columns", "Délai de Livraison", each Duration.Days([date_livraison] - [date_commande]), Int64.Type),
    #"Added Localisation" = Table.AddColumn(#"Added Délai de Livraison", "Localisation", each [ville] & " (" & [departement] & ") - " & [region], type text),
    Result = #"Added Localisation"
in
    Result